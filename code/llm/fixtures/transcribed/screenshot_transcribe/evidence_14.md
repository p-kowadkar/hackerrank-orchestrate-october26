---
step: screenshot_transcribe
key: evidence_14
origin: transcribed
source: dataset/evidence/images/connector_management_console_20260807.png
reader: Claude Code session (model claude-sonnet-5-5) reading the image by eye; not an API call
---

```json
{
 "screen": "BridgeOps > Connections",
 "rows": [
  {
   "record_type": "DATA_FLOW",
   "resource_id": "data_flow_1121",
   "label": null,
   "selected": true,
   "identifiers": [
    "jain.aditi@gmail.com"
   ],
   "facts": {
    "enabled": true,
    "restore_blocked": null,
    "identifiable": null,
    "status": "Healthy",
    "expires_at": null
   }
  },
  {
   "record_type": "DATA_FLOW",
   "resource_id": "data_flow_9846",
   "label": null,
   "selected": false,
   "identifiers": [
    "lucia-torres@gmail.com"
   ],
   "facts": {
    "enabled": true,
    "restore_blocked": null,
    "identifiable": null,
    "status": null,
    "expires_at": null
   }
  },
  {
   "record_type": "DATA_FLOW",
   "resource_id": null,
   "label": "Order notifications",
   "selected": false,
   "identifiers": [],
   "facts": {
    "enabled": true,
    "restore_blocked": null,
    "identifiable": null,
    "status": null,
    "expires_at": null
   }
  },
  {
   "record_type": "DATA_FLOW",
   "resource_id": null,
   "label": "Delivery tracking",
   "selected": false,
   "identifiers": [],
   "facts": {
    "enabled": true,
    "restore_blocked": null,
    "identifiable": null,
    "status": null,
    "expires_at": null
   }
  }
 ]
}
```

Reading notes: mode column says Continuous for all four rows; the selected row's detail panel says Status Healthy, Sync mode Continuous sync, last response 200 OK.
