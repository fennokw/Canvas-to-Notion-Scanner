# Calendar importers and BestNDS

For [Kaden’s BestNDS dashboard](https://github.com/fennokw/BestNDS), use the maintained [Notion Calendar Automation Hub](https://github.com/fennokw/Notion-Calendar-Automation-Hub). It supports Canvas assignments and Google Calendar/iCalendar feeds in the same Schedule & Tasks database.

The code retained in `ICS-Link-to-Notion-Sync-Public` is a **legacy ICS importer**, despite this repository's Canvas name. It expects Due Date / Event Date, Status, Project Domain and Class relations. It is not compatible with BestNDS without adapting those mappings. Do not run both importers against the same calendar: their external-ID schemes differ and may duplicate records.

BestNDS uses Date for calendar placement, Type Event/Task, and Completed for check-offs. Homework/Test are optional Task kind values. Commitment is only for events. The Hub compatibility update preserves imported identifiers and personal completion choices. See its setup instructions before switching an existing scheduled workflow.

[Legacy importer documentation](ICS-Link-to-Notion-Sync-Public/README.md)
