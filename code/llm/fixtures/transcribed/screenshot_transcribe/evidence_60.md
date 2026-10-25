---
step: screenshot_transcribe
key: evidence_60
origin: transcribed
source: dataset/evidence/images/marketing_profile_console.png
reader: Claude Code session (model claude-sonnet-5-5) reading the image by eye; not an API call
---

```json
{
 "screen": "Audience Operations > Audience Operations",
 "rows": [
  {
   "record_type": "MARKETING",
   "resource_id": "marketing_001",
   "label": "Soo-jin Park",
   "selected": true,
   "identifiers": [
    "Soo-jin Park",
    "sj.park@naver.com",
    "+82 10-5837-9451"
   ],
   "facts": {
    "enabled": null,
    "restore_blocked": null,
    "identifiable": null,
    "status": "Live",
    "expires_at": null
   }
  },
  {
   "record_type": "OTHER",
   "resource_id": null,
   "label": "Product-category update",
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
   "label": "Campaign eligibility check",
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
   "label": "Profile refresh",
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
   "label": "Audience evaluation",
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

Reading notes: the person on screen (Soo-jin Park, an @naver.com address, a Korean phone number) is whoever the profile belongs to; who the case's user is comes from the data catalog, not from this picture. Market South Korea, e-mail opt-in Yes, SMS opt-in No, last refreshed 15 Sep 2026 23:40 UTC.
