---
step: screenshot_transcribe
key: evidence_42
origin: transcribed
source: dataset/evidence/images/deleted_account_reference_20260310.png
reader: Claude Code session (model claude-sonnet-5-5) reading the image by eye; not an API call
---

```json
{
 "screen": "Customer Reference Registry > Customer references",
 "rows": [
  {
   "record_type": "TOMBSTONE",
   "resource_id": null,
   "label": "user_17",
   "selected": true,
   "identifiers": [
    "user_17"
   ],
   "facts": {
    "enabled": null,
    "restore_blocked": null,
    "identifiable": false,
    "status": "Retained reference",
    "expires_at": null
   }
  },
  {
   "record_type": "OTHER",
   "resource_id": null,
   "label": "ORD-20263245",
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
   "label": "CS-3245",
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
   "label": "CS-3378",
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
   "label": "FIN-7742",
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

Reading notes: the page is a retained customer key, 'Customer key . Account Platform . eu-west', created 11 Jan 2024 08:42 UTC, most recent update 10 Mar 2026 07:18 UTC. No name, e-mail address, phone number or e-mail hash is printed anywhere; the only identifier is the stable reference user_17, which a tombstone is supposed to keep. No tombstone id is printed.
