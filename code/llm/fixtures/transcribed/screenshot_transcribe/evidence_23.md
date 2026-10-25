---
step: screenshot_transcribe
key: evidence_23
origin: transcribed
source: dataset/evidence/images/customer_export_console_20260618.png
reader: Claude Code session (model claude-sonnet-5-5) reading the image by eye; not an API call
---

```json
{
 "screen": "Customer Download Center > Data exports",
 "rows": [
  {
   "record_type": "EXPORT",
   "resource_id": "export_1261",
   "label": "customer_export_1261.zip",
   "selected": false,
   "identifiers": [
    "marcus.lee@northstar.shop"
   ],
   "facts": {
    "enabled": null,
    "restore_blocked": null,
    "identifiable": null,
    "status": "Collecting",
    "expires_at": null
   }
  },
  {
   "record_type": "EXPORT",
   "resource_id": "export_1260",
   "label": "customer_export_1260.zip",
   "selected": true,
   "identifiers": [
    "ingrid.dahl@outlook.com"
   ],
   "facts": {
    "enabled": null,
    "restore_blocked": null,
    "identifiable": null,
    "status": "Ready",
    "expires_at": "2026-06-25T06:42:00Z"
   }
  },
  {
   "record_type": "EXPORT",
   "resource_id": "export_1259",
   "label": "customer_export_1259.zip",
   "selected": false,
   "identifiers": [
    "sara.kim@northstar.shop"
   ],
   "facts": {
    "enabled": null,
    "restore_blocked": null,
    "identifiable": null,
    "status": "Packaging",
    "expires_at": null
   }
  },
  {
   "record_type": "EXPORT",
   "resource_id": "export_1258",
   "label": "customer_export_1258.zip",
   "selected": false,
   "identifiers": [
    "daniel.park@northstar.shop"
   ],
   "facts": {
    "enabled": null,
    "restore_blocked": null,
    "identifiable": null,
    "status": "Ready",
    "expires_at": null
   }
  }
 ]
}
```

Reading notes: the shaded table row is export_1261 but the right-hand detail panel is titled export_1260 (owner ingrid.dahl@outlook.com, created 18 Jun 2026 06:42 UTC, expires 25 Jun 2026 06:42 UTC, size 18.4 MB, download count 0). The detail panel decides which record is selected.
