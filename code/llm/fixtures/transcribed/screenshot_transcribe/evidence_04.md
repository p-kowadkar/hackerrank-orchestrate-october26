---
step: screenshot_transcribe
key: evidence_04
origin: transcribed
source: dataset/evidence/images/account_admin_console_20260926.png
reader: Claude Code session (model claude-sonnet-5-5) reading the image by eye; not an API call
---

```json
{
 "screen": "Customer Operations > Customers",
 "rows": [
  {
   "record_type": "ACCOUNT",
   "resource_id": "account_5762",
   "label": "Haruka Sato",
   "selected": true,
   "identifiers": [
    "Haruka Sato",
    "user_11",
    "haruka.s1838@zoho.com",
    "+81 90 7610 2507"
   ],
   "facts": {
    "enabled": null,
    "restore_blocked": null,
    "identifiable": null,
    "status": "Silver",
    "expires_at": null
   }
  },
  {
   "record_type": "SUPPORT_TICKET",
   "resource_id": "support_9538",
   "label": "CS-8538",
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
   "label": "ORD-20265762",
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
   "label": "ORD-20265518",
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

Reading notes: the page describes one customer; the first order row is shaded but the detail panel is the customer's. The support ticket appears only as a reference in the detail panel and shows no personal identifier of its own.
