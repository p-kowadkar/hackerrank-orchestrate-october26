---
step: screenshot_transcribe
key: evidence_32
origin: transcribed
source: dataset/evidence/images/backup_restore_console_20260429.png
reader: Claude Code session (model claude-sonnet-5-5) reading the image by eye; not an API call
---

```json
{
 "screen": "Vault Recovery Manager > Recovery Manager",
 "rows": [
  {
   "record_type": "BACKUP",
   "resource_id": "backup_9291",
   "label": null,
   "selected": false,
   "identifiers": [
    "bluepeakco@outlook.com"
   ],
   "facts": {
    "enabled": null,
    "restore_blocked": false,
    "identifiable": null,
    "status": null,
    "expires_at": null
   }
  },
  {
   "record_type": "BACKUP",
   "resource_id": "backup_9288",
   "label": null,
   "selected": false,
   "identifiers": [
    "miller.logistics@company.com"
   ],
   "facts": {
    "enabled": null,
    "restore_blocked": false,
    "identifiable": null,
    "status": null,
    "expires_at": null
   }
  },
  {
   "record_type": "BACKUP",
   "resource_id": "backup_9287",
   "label": null,
   "selected": true,
   "identifiers": [
    "areed1433@gmail.com"
   ],
   "facts": {
    "enabled": null,
    "restore_blocked": false,
    "identifiable": null,
    "status": null,
    "expires_at": null
   }
  },
  {
   "record_type": "BACKUP",
   "resource_id": "backup_9286",
   "label": null,
   "selected": false,
   "identifiers": [
    "summit-retail@company.com"
   ],
   "facts": {
    "enabled": null,
    "restore_blocked": false,
    "identifiable": null,
    "status": null,
    "expires_at": null
   }
  }
 ]
}
```

Reading notes: the shaded table row is backup_9291 but the detail panel is titled backup_9287 (account areed1433@gmail.com, eu-west-1, created 26 Apr 2026 02:00 UTC, AES-256, checksum Verified, last drill 29 Mar 2026, retention end 26 Jul 2026). Nothing on the screen blocks, denies or disables restoring any archive; the activity list shows other archives being restored on 24 and 25 Apr.
