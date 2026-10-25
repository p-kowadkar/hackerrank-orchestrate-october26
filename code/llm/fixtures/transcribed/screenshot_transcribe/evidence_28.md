---
step: screenshot_transcribe
key: evidence_28
origin: transcribed
source: dataset/evidence/images/support_ticket_console_20260524.png
reader: Claude Code session (model claude-sonnet-5-5) reading the image by eye; not an API call
---

```json
{
 "screen": "Helpline Console > Inbox",
 "rows": [
  {
   "record_type": "SUPPORT_TICKET",
   "resource_id": "support_1034",
   "label": "Where is my delivery?",
   "selected": true,
   "identifiers": [
    "Kofi Agyeman",
    "kagyeman8947@fastmail.com"
   ],
   "facts": {
    "enabled": null,
    "restore_blocked": null,
    "identifiable": true,
    "status": null,
    "expires_at": null
   }
  },
  {
   "record_type": "OTHER",
   "resource_id": null,
   "label": "Kofi Agyeman 09:12",
   "selected": false,
   "identifiers": [],
   "facts": {
    "enabled": null,
    "restore_blocked": null,
    "identifiable": null,
    "status": null,
    "expires_at": null
   }
  },
  {
   "record_type": "OTHER",
   "resource_id": null,
   "label": "Northstar Bot 09:13",
   "selected": false,
   "identifiers": [],
   "facts": {
    "enabled": null,
    "restore_blocked": null,
    "identifiable": null,
    "status": null,
    "expires_at": null
   }
  },
  {
   "record_type": "OTHER",
   "resource_id": null,
   "label": "Maya Chen 09:28",
   "selected": false,
   "identifiers": [],
   "facts": {
    "enabled": null,
    "restore_blocked": null,
    "identifiable": null,
    "status": null,
    "expires_at": null
   }
  },
  {
   "record_type": "OTHER",
   "resource_id": null,
   "label": "Kofi Agyeman 09:35",
   "selected": false,
   "identifiers": [],
   "facts": {
    "enabled": null,
    "restore_blocked": null,
    "identifiable": null,
    "status": null,
    "expires_at": null
   }
  }
 ]
}
```

Reading notes: the ticket header 'CS-5034 . Where is my delivery?' carries the id support_1034 and the customer's name; the customer card shows the e-mail address. Maya Chen is the assigned agent (staff), so she is not listed as an identifier.
