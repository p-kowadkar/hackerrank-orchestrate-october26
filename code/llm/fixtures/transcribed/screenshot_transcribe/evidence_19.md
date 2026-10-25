---
step: screenshot_transcribe
key: evidence_19
origin: transcribed
source: dataset/evidence/images/analytics_profile_view_20260713.png
reader: Claude Code session (model claude-sonnet-5-5) reading the image by eye; not an API call
---

```json
{
 "screen": "Pulse Analytics > Users",
 "rows": [
  {
   "record_type": "ANALYTICS",
   "resource_id": "analytics_7438",
   "label": "Omar Darwish",
   "selected": true,
   "identifiers": [
    "Omar Darwish",
    "user_20",
    "darwish.omar@icloud.com"
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
   "label": "Order completed",
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
   "label": "Checkout started",
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
   "label": "Product viewed",
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
   "label": "Added to cart",
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
   "label": "Product viewed",
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

Reading notes: the header names the user with user_20, analytics_7438 and an e-mail address, so the profile is attributable; the 'Last 90 days' badge is a reporting window, not a status. The rows of the table are events, not records.
