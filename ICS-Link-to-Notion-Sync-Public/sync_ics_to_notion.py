import json
import os
import re
import sys
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests
from icalendar import Calendar
import recurring_ical_events

from config import (
    TODO_PROPS,
    PROJECT_DOMAIN_TITLE_PROP,
    CLASSES_TITLE_PROP,
    DEFAULT_STATUS,
    TYPE_MEETING,
    SKIP_CANCELLED,
    IGNORE_PAST_EVENTS_OLDER_THAN_DAYS,
    IMPORT_LOOKAHEAD_DAYS,
    UPDATE_CHANGED_EVENTS,
    CLASS_TITLE_KEYWORDS,
    PROJECT_DOMAIN_KEYWORDS,
)

NOTION_TOKEN = os.environ["NOTION_TOKEN"]
ICS_URL = os.environ["ICS_URL"]
TODO_DATABASE_URL = os.environ["TODO_DATABASE_URL"]
PROJECT_DOMAIN_DATABASE_URL = os.environ["PROJECT_DOMAIN_DATABASE_URL"]
CLASSES_DATABASE_URL = os.environ.get("CLASSES_DATABASE_URL", "").strip()
DEFAULT_PROJECT_DOMAIN_TITLE = os.environ["DEFAULT_PROJECT_DOMAIN_TITLE"]

NOTION_VERSION = "2025-09-03"
HTTP_TIMEOUT = 30


def notion_headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def raise_for_status_with_body(resp: requests.Response) -> None:
    try:
        resp.raise_for_status()
    except requests.HTTPError as exc:
        body = resp.text[:3000]
        raise RuntimeError(
            f"HTTP {resp.status_code} for {resp.request.method} {resp.url}\n{body}"
        ) from exc


def extract_notion_id_from_url(url: str) -> str:
    match = re.search(r"notion\.so/([0-9a-fA-F]{32})", url)
    if not match:
        raise ValueError(f"Could not extract Notion database ID from URL: {url}")
    raw = match.group(1)
    return f"{raw[0:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:32]}"


def fetch_ics_bytes(url: str) -> bytes:
    print("Downloading ICS feed...")
    resp = requests.get(url, timeout=HTTP_TIMEOUT, allow_redirects=True)
    raise_for_status_with_body(resp)
    content = resp.content

    if b"BEGIN:VCALENDAR" not in content:
        preview = content[:500].decode("utf-8", errors="ignore")
        raise RuntimeError(
            "The configured ICS_URL did not return raw ICS data. "
            "Use a direct/public .ics feed URL.\n"
            f"Response preview:\n{preview}"
        )

    return content


def notion_get_database(database_id: str) -> Dict[str, Any]:
    resp = requests.get(
        f"https://api.notion.com/v1/databases/{database_id}",
        headers=notion_headers(),
        timeout=HTTP_TIMEOUT,
    )
    raise_for_status_with_body(resp)
    return resp.json()


def notion_get_data_source(data_source_id: str) -> Dict[str, Any]:
    resp = requests.get(
        f"https://api.notion.com/v1/data_sources/{data_source_id}",
        headers=notion_headers(),
        timeout=HTTP_TIMEOUT,
    )
    raise_for_status_with_body(resp)
    return resp.json()


def notion_query_data_source(
    data_source_id: str,
    filter_obj: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    url = f"https://api.notion.com/v1/data_sources/{data_source_id}/query"
    results: List[Dict[str, Any]] = []
    cursor: Optional[str] = None

    while True:
        payload: Dict[str, Any] = {"page_size": 100}
        if filter_obj:
            payload["filter"] = filter_obj
        if cursor:
            payload["start_cursor"] = cursor

        resp = requests.post(
            url,
            headers=notion_headers(),
            data=json.dumps(payload),
            timeout=HTTP_TIMEOUT,
        )
        raise_for_status_with_body(resp)
        data = resp.json()
        results.extend(data.get("results", []))

        if not data.get("has_more"):
            return results
        cursor = data.get("next_cursor")


def notion_create_page(data_source_id: str, properties: Dict[str, Any]) -> None:
    payload = {
        "parent": {"type": "data_source_id", "data_source_id": data_source_id},
        "properties": properties,
    }
    resp = requests.post(
        "https://api.notion.com/v1/pages",
        headers=notion_headers(),
        data=json.dumps(payload),
        timeout=HTTP_TIMEOUT,
    )
    raise_for_status_with_body(resp)


def notion_update_page(page_id: str, properties: Dict[str, Any]) -> None:
    resp = requests.patch(
        f"https://api.notion.com/v1/pages/{page_id}",
        headers=notion_headers(),
        data=json.dumps({"properties": properties}),
        timeout=HTTP_TIMEOUT,
    )
    raise_for_status_with_body(resp)


def notion_title(value: str) -> Dict[str, Any]:
    return {"title": [{"type": "text", "text": {"content": value}}]}


def notion_date(start_value: str, end_value: Optional[str]) -> Dict[str, Any]:
    value: Dict[str, Any] = {"start": start_value}
    if end_value:
        value["end"] = end_value
    return {"date": value}


def notion_status(value: str) -> Dict[str, Any]:
    return {"status": {"name": value}}


def notion_select(value: str) -> Dict[str, Any]:
    return {"select": {"name": value}}


def notion_rich_text(value: str) -> Dict[str, Any]:
    return {"rich_text": [{"type": "text", "text": {"content": value}}]}


def notion_relation(page_id: str) -> Dict[str, Any]:
    return {"relation": [{"id": page_id}]}


class DataSourceTarget:
    def __init__(self, database_url: str, label: str):
        self.label = label
        self.database_id = extract_notion_id_from_url(database_url)
        self.data_source_id: Optional[str] = None
        self.schema: Dict[str, Any] = {}

    def load(self) -> None:
        database = notion_get_database(self.database_id)
        data_sources = database.get("data_sources") or []
        if not data_sources:
            raise RuntimeError(
                f"{self.label}: no data source found. "
                "Use the original Notion database URL, not a linked view."
            )
        self.data_source_id = data_sources[0]["id"]
        self.schema = notion_get_data_source(self.data_source_id).get("properties", {})

    def require_props(self, expected: Dict[str, str]) -> None:
        missing = [name for name in expected if name not in self.schema]
        if missing:
            raise RuntimeError(f"{self.label}: missing properties: {missing}")

        wrong = []
        for name, expected_type in expected.items():
            actual_type = self.schema[name].get("type")
            if actual_type != expected_type:
                wrong.append(f"{name}: expected {expected_type}, got {actual_type}")

        if wrong:
            raise RuntimeError(f"{self.label}: wrong property types:\n- " + "\n- ".join(wrong))


def get_plain_title(page: Dict[str, Any], title_prop: str) -> str:
    title_items = page.get("properties", {}).get(title_prop, {}).get("title", [])
    return "".join(item.get("plain_text", "") for item in title_items).strip()


def build_title_lookup(target: DataSourceTarget, title_prop: str) -> Dict[str, str]:
    assert target.data_source_id is not None
    pages = notion_query_data_source(target.data_source_id)
    lookup: Dict[str, str] = {}
    for page in pages:
        title = get_plain_title(page, title_prop)
        if title:
            lookup[title] = page["id"]
    return lookup


def find_existing_event(todo_target: DataSourceTarget, event_id: str) -> Optional[Dict[str, Any]]:
    assert todo_target.data_source_id is not None
    results = notion_query_data_source(
        todo_target.data_source_id,
        {
            "property": TODO_PROPS["ics_event_id"],
            "rich_text": {"equals": event_id},
        },
    )
    return results[0] if results else None


def normalize_title(value: str) -> str:
    return " ".join((value or "").strip().split())


def normalize_dt(raw_dt: Any) -> datetime:
    if isinstance(raw_dt, datetime):
        if raw_dt.tzinfo is None:
            raw_dt = raw_dt.replace(tzinfo=timezone.utc)
        return raw_dt.astimezone(timezone.utc)
    if isinstance(raw_dt, date):
        return datetime.combine(raw_dt, time.min, tzinfo=timezone.utc)
    raise ValueError(f"Unsupported date type: {type(raw_dt)}")


def expanded_event_id(component: Any, uid: str, start_dt: datetime) -> str:
    """Return a stable-enough ID for a single ICS occurrence.

    RECURRENCE-ID is preferred for recurring instances. Non-recurring events use
    the UID. A start-time fallback is used only when the feed does not provide
    a useful UID.
    """
    recurrence_id = component.get("RECURRENCE-ID")
    if recurrence_id:
        try:
            recurrence_value = normalize_dt(recurrence_id.dt).isoformat()
        except Exception:
            recurrence_value = str(recurrence_id.dt)
        return f"ics:{uid}:recurrence:{recurrence_value}"

    if uid:
        # recurring-ical-events may expand an occurrence without exposing a
        # RECURRENCE-ID. Include the occurrence start so each instance is unique.
        if component.get("RRULE"):
            return f"ics:{uid}:start:{start_dt.isoformat()}"
        return f"ics:{uid}"

    return f"ics:no-uid:{start_dt.isoformat()}"


def parse_ics_events(ics_bytes: bytes) -> List[Dict[str, Any]]:
    calendar = Calendar.from_ical(ics_bytes)
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=IGNORE_PAST_EVENTS_OLDER_THAN_DAYS)
    window_end = now + timedelta(days=IMPORT_LOOKAHEAD_DAYS)

    expanded = recurring_ical_events.of(calendar).between(window_start, window_end)
    events: List[Dict[str, Any]] = []

    for component in expanded:
        status = str(component.get("STATUS", "")).strip().upper()
        if SKIP_CANCELLED and status == "CANCELLED":
            continue

        dtstart = component.get("DTSTART")
        if not dtstart:
            continue

        try:
            start_dt = normalize_dt(dtstart.dt)
        except Exception:
            continue

        end_dt: Optional[datetime] = None
        dtend = component.get("DTEND")
        if dtend:
            try:
                end_dt = normalize_dt(dtend.dt)
            except Exception:
                end_dt = None

        summary = normalize_title(str(component.get("SUMMARY", "") or "Untitled Event"))
        uid = str(component.get("UID", "") or "").strip()

        events.append(
            {
                "summary": summary,
                "start": start_dt.isoformat(),
                "end": end_dt.isoformat() if end_dt else None,
                "ics_event_id": expanded_event_id(component, uid, start_dt),
            }
        )

    return events


def infer_class_page_title(summary: str) -> Optional[str]:
    text = summary.lower()
    # Longest keys first so a specific key beats a short generic key.
    for keyword in sorted(CLASS_TITLE_KEYWORDS, key=len, reverse=True):
        if keyword.lower() in text:
            return CLASS_TITLE_KEYWORDS[keyword]
    return None


def infer_project_domain_title(summary: str) -> str:
    text = summary.lower()
    for page_title, keywords in PROJECT_DOMAIN_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in text:
                return page_title
    return DEFAULT_PROJECT_DOMAIN_TITLE


def build_todo_properties(
    event: Dict[str, Any],
    project_domain_page_id: str,
    class_page_id: Optional[str],
    preserve_status: bool,
) -> Dict[str, Any]:
    props: Dict[str, Any] = {
        TODO_PROPS["name"]: notion_title(event["summary"]),
        TODO_PROPS["project_domain"]: notion_relation(project_domain_page_id),
        TODO_PROPS["event_date"]: notion_date(event["start"], event.get("end")),
        TODO_PROPS["type"]: notion_select(TYPE_MEETING),
        TODO_PROPS["ics_event_id"]: notion_rich_text(event["ics_event_id"]),
    }

    if not preserve_status:
        props[TODO_PROPS["status"]] = notion_status(DEFAULT_STATUS)

    if class_page_id:
        props[TODO_PROPS["class_relation"]] = notion_relation(class_page_id)

    return props


def main() -> int:
    print("Starting ICS -> Notion sync...")

    todo = DataSourceTarget(TODO_DATABASE_URL, "To-Do database")
    domains = DataSourceTarget(PROJECT_DOMAIN_DATABASE_URL, "Project Domains database")
    classes = DataSourceTarget(CLASSES_DATABASE_URL, "Classes database") if CLASSES_DATABASE_URL else None

    todo.load()
    domains.load()
    if classes:
        classes.load()

    todo.require_props(
        {
            TODO_PROPS["status"]: "status",
            TODO_PROPS["project_domain"]: "relation",
            TODO_PROPS["class_relation"]: "relation",
            TODO_PROPS["name"]: "title",
            TODO_PROPS["event_date"]: "date",
            TODO_PROPS["type"]: "select",
            TODO_PROPS["ics_event_id"]: "rich_text",
        }
    )

    domain_lookup = build_title_lookup(domains, PROJECT_DOMAIN_TITLE_PROP)
    if DEFAULT_PROJECT_DOMAIN_TITLE not in domain_lookup:
        raise RuntimeError(
            f'Project Domains database has no page titled "{DEFAULT_PROJECT_DOMAIN_TITLE}".'
        )

    class_lookup: Dict[str, str] = {}
    if classes:
        class_lookup = build_title_lookup(classes, CLASSES_TITLE_PROP)

    events = parse_ics_events(fetch_ics_bytes(ICS_URL))
    print(f"Parsed {len(events)} event occurrences in the import window.")

    created = 0
    updated = 0
    failed = 0

    for event in events:
        domain_title = infer_project_domain_title(event["summary"])
        domain_page_id = domain_lookup.get(domain_title)
        if not domain_page_id:
            print(
                f'  ERROR: "{event["summary"]}" mapped to missing Project Domain "{domain_title}".',
                file=sys.stderr,
            )
            failed += 1
            continue

        class_page_id: Optional[str] = None
        class_title = infer_class_page_title(event["summary"])
        if class_title:
            class_page_id = class_lookup.get(class_title)
            if not class_page_id:
                print(
                    f'  WARNING: class mapping "{class_title}" was not found; leaving Class blank.'
                )

        existing = find_existing_event(todo, event["ics_event_id"])

        try:
            props = build_todo_properties(
                event,
                domain_page_id,
                class_page_id,
                preserve_status=bool(existing),
            )

            if existing:
                if UPDATE_CHANGED_EVENTS:
                    notion_update_page(existing["id"], props)
                    updated += 1
                    print(f'  UPDATED: {event["summary"]} @ {event["start"]}')
            else:
                assert todo.data_source_id is not None
                notion_create_page(todo.data_source_id, props)
                created += 1
                print(f'  CREATED: {event["summary"]} @ {event["start"]}')
        except Exception as exc:
            failed += 1
            print(f'  ERROR: {event["summary"]} -> {exc}', file=sys.stderr)

    print("Done.")
    print(f"Created: {created}")
    print(f"Updated: {updated}")
    print(f"Failed: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
