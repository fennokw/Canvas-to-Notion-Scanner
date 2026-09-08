"""Public configuration for ICS Link -> Notion Sync.

Personal URLs and credentials are intentionally NOT stored here.
Set them in GitHub repository Variables/Secrets as described in README.md.

Edit the mappings below to teach the sync how to classify events.
"""

# Exact property names expected in the target Notion To-Do database.
TODO_PROPS = {
    "status": "Status",
    "project_domain": "Project Domain",
    "class_relation": "Class",
    "name": "Name",
    "event_date": "Due Date / Event Date",
    "type": "Type",
    "ics_event_id": "ICS Event ID",
}

# Title-property names in the related Notion databases.
PROJECT_DOMAIN_TITLE_PROP = "Name"
CLASSES_TITLE_PROP = "Name"

# Exact option names expected in the To-Do database.
DEFAULT_STATUS = "Not Started"
TYPE_MEETING = "meeting/event"

# Import behavior.
SKIP_CANCELLED = True
IGNORE_PAST_EVENTS_OLDER_THAN_DAYS = 5
IMPORT_LOOKAHEAD_DAYS = 180
UPDATE_CHANGED_EVENTS = True

# Optional class matching.
# Key = lowercase text expected in the ICS event title.
# Value = exact page title in the Notion Classes database.
#
# Example:
# CLASS_TITLE_KEYWORDS = {
#     "18.03": "MIT 18.03 Class",
#     "8.011 rec": "MIT 8.011 Class",
# }
CLASS_TITLE_KEYWORDS = {}

# Optional Project Domain inference.
# Key = exact page title in the Notion Project Domains database.
# Value = keywords that identify that domain in an ICS event title.
#
# Events that do not match any keyword are assigned to the repository variable
# DEFAULT_PROJECT_DOMAIN_TITLE.
#
# Example:
# PROJECT_DOMAIN_KEYWORDS = {
#     "Athletics": ["practice", "game", "lift"],
#     "Music": ["rehearsal", "studio", "gig"],
# }
PROJECT_DOMAIN_KEYWORDS = {}
