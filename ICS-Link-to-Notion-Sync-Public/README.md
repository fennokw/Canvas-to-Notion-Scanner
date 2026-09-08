# ICS Link → Notion Sync

A reusable Python + GitHub Actions project that reads a live `.ics` calendar feed and syncs its events into a Notion To-Do database.

It is designed for shared calendars such as classes, clubs, teams, organizations, work schedules, and personal calendars. The repository contains no personal calendar URLs, Notion links, or credentials; each user supplies their own values in GitHub Settings.

## What it does

On each run, the project:

1. Downloads a public/direct ICS feed.
2. Expands recurring calendar events into real occurrences.
3. Ignores cancelled events.
4. Imports events from a configurable window (default: 5 days in the past through 180 days in the future).
5. Preserves both the **start and end time**, so Notion calendar views show a full time block.
6. Creates new events in a Notion To-Do database as `meeting/event`.
7. Uses a hidden `ICS Event ID` property to prevent duplicates.
8. Updates already-imported events when their source data changes.
9. Assigns a Project Domain relation and, optionally, a Class relation based on configurable title keywords.
10. Runs daily in GitHub Actions and can also be run manually.

## Repository structure

```text
ics-link-to-notion-sync/
├── .github/
│   └── workflows/
│       └── daily-sync.yml
├── .gitignore
├── config.py
├── LICENSE
├── README.md
├── requirements.txt
└── sync_ics_to_notion.py
```

## Required Notion structure

### To-Do database

Create or use a source database with these exact properties by default:

| Property | Notion type | Purpose |
| --- | --- | --- |
| `Name` | Title | Event title |
| `Status` | Status | Task/event state |
| `Project Domain` | Relation | Links to Project Domains |
| `Class` | Relation | Optional class/course relation |
| `Due Date / Event Date` | Date | Stores the event start and end time |
| `Type` | Select | Imported calendar events use `meeting/event` |
| `ICS Event ID` | Text | Hidden stable identifier used for sync/deduplication |

The default code expects the Status option `Not Started` and the Type option `meeting/event` to exist. You can change those names in `config.py`.

### Project Domains database

The Project Domains database needs a title property named `Name` by default. It must contain at least the page whose exact title you configure in `DEFAULT_PROJECT_DOMAIN_TITLE`.

### Classes database — optional for matching, but the To-Do relation still exists

The Classes database also uses a title property named `Name` by default. If you configure `CLASS_TITLE_KEYWORDS`, the script can identify a course from an ICS event title and set the matching `Class` relation.

## Notion integration setup

1. Create an internal Notion integration.
2. Copy its integration token.
3. Share the **source** To-Do database with that integration.
4. Share the **source** Project Domains database with it.
5. If using class matching, share the **source** Classes database too.

Use original source databases, not linked views.

## GitHub setup

Fork or clone this repository, then open:

**Repository → Settings → Secrets and variables → Actions**

### Add one repository Secret

| Secret | Value |
| --- | --- |
| `NOTION_TOKEN` | Your Notion integration token |

Never commit the Notion token into the repository.

### Add repository Variables

| Variable | Example | Required? |
| --- | --- | --- |
| `ICS_URL` | `https://calendar.example.com/public/calendar.ics` | Yes |
| `TODO_DATABASE_URL` | Full Notion source database URL | Yes |
| `PROJECT_DOMAIN_DATABASE_URL` | Full Project Domains source database URL | Yes |
| `CLASSES_DATABASE_URL` | Full Classes source database URL | Only for class relation matching |
| `DEFAULT_PROJECT_DOMAIN_TITLE` | `Fraternity`, `Athletics`, `Personal`, etc. | Yes |

Using GitHub Variables keeps personal URLs out of the committed source code while keeping setup simple.

## Configure event classification

Open `config.py`.

### Project Domain keyword routing

You can route certain event titles to specific Project Domain pages:

```python
PROJECT_DOMAIN_KEYWORDS = {
    "Athletics": ["practice", "game", "lift"],
    "Music": ["rehearsal", "studio", "gig"],
}
```

The dictionary key must be the **exact title of a page in your Project Domains database**.

If an event does not match any configured keyword, it is assigned to the Project Domain named by the GitHub variable `DEFAULT_PROJECT_DOMAIN_TITLE`.

### Class matching

To populate the `Class` relation, map text found in ICS event titles to exact page titles in the Classes database:

```python
CLASS_TITLE_KEYWORDS = {
    "18.03": "MIT 18.03 Class",
    "8.011 rec": "MIT 8.011 Class",
}
```

If no mapping matches, the Class relation is left empty.

## How duplicate prevention works

Every imported occurrence receives an `ICS Event ID`.

For recurring events, the script prefers the ICS `RECURRENCE-ID` so each occurrence can be tracked separately. For feeds that do not expose a recurrence ID after expansion, it uses the event UID plus that occurrence's start time.

Before creating a Notion row, the script searches for the same `ICS Event ID`:

- not found → create a new row;
- found → update the existing row if `UPDATE_CHANGED_EVENTS = True`.

The script deliberately preserves an existing row's Status when updating it so a calendar refresh does not reset something you marked manually.

## Full calendar time blocks

The script reads both `DTSTART` and `DTEND` from the ICS occurrence and writes them as the `start` and `end` of the Notion `Due Date / Event Date` property.

That is what makes events display as full blocks in Notion calendar/timeline views instead of single timestamps.

## Recurring events

ICS feeds usually store repeating events as one `VEVENT` plus an `RRULE`. Importing only the raw `DTSTART` would miss the future occurrences.

This project uses `recurring-ical-events` to expand recurring events within the configured import window before syncing them to Notion.

Change the window in `config.py`:

```python
IGNORE_PAST_EVENTS_OLDER_THAN_DAYS = 5
IMPORT_LOOKAHEAD_DAYS = 180
```

## Automatic and manual runs

The included workflow runs daily at:

```yaml
cron: "0 11 * * *"
```

GitHub cron schedules use UTC.

You can change the cron expression in `.github/workflows/daily-sync.yml`.

The workflow also includes `workflow_dispatch`, so you can run it manually:

**Actions → Daily ICS → Notion Sync → Run workflow**

## Using a Google Calendar ICS feed

Google Calendar public calendars can provide direct ICS feeds. Use the URL that returns actual calendar text beginning with:

```text
BEGIN:VCALENDAR
```

Do not use a normal Google Calendar webpage URL.

The sync validates the response and fails with a useful message if `ICS_URL` returns HTML or another non-ICS document.

## Common errors

### `API token is invalid`

The `NOTION_TOKEN` GitHub Secret is missing or incorrect in this repository.

Secrets are repository-scoped unless configured at a broader scope, so a token working in another GitHub repo does not mean it exists in this one.

### `no data source found`

One of your URLs points to a linked Notion view rather than the original source database.

### `missing properties`

Your To-Do property names do not match `config.py`, or the integration is looking at the wrong database.

### `wrong property types`

The property exists but has the wrong Notion type. For example, `Due Date / Event Date` must be a Date property, not Text.

### ICS downloads but imports zero events

Check whether the events are outside the configured date window. Recurring events are expanded automatically, so a normal repeating schedule should import correctly.

### Class is blank

The event title did not match any `CLASS_TITLE_KEYWORDS` value, or the resulting page title does not exist in the Classes database.

## Privacy and public repositories

This repository is designed so no personal integration token or private Notion/calendar URL needs to be committed.

- Keep `NOTION_TOKEN` in GitHub Secrets.
- Put personal URLs in GitHub Variables.
- Avoid hard-coding private calendar feeds into `config.py`.

Be aware that a truly public ICS feed can be accessed by anyone who has its URL. Treat private ICS URLs as sensitive even if the calendar provider calls them "secret" or "private" links.

## Development / local testing

You can also run the script locally:

```bash
python -m pip install -r requirements.txt
```

Then set the required environment variables and run:

```bash
export NOTION_TOKEN="..."
export ICS_URL="https://.../calendar.ics"
export TODO_DATABASE_URL="https://www.notion.so/..."
export PROJECT_DOMAIN_DATABASE_URL="https://www.notion.so/..."
export CLASSES_DATABASE_URL="https://www.notion.so/..."
export DEFAULT_PROJECT_DOMAIN_TITLE="Personal"

python sync_ics_to_notion.py
```

On Windows PowerShell, use `$env:VARIABLE_NAME = "value"` instead of `export`.

## License

MIT. See `LICENSE`.
