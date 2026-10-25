---
step: screenshot_transcribe
key: evidence_09
origin: transcribed
source: dataset/evidence/images/search_index_inspector_20260901.png
reader: Claude Code session (model claude-sonnet-5-5) reading the image by eye; not an API call
---

```json
{
 "screen": "Search Console > Customer Search",
 "rows": [
  {
   "record_type": "SEARCH",
   "resource_id": "search_428",
   "label": "Gabriel Silva",
   "selected": true,
   "identifiers": [
    "Gabriel Silva",
    "g.silva76@gmail.com",
    "user_13"
   ],
   "facts": {
    "enabled": null,
    "restore_blocked": null,
    "identifiable": null,
    "status": "Indexed",
    "expires_at": null
   }
  },
  {
   "record_type": "SEARCH",
   "resource_id": "search_1874",
   "label": null,
   "selected": false,
   "identifiers": [
    "g.silva76.jr@gmail.com"
   ],
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

Reading notes: status 'Indexed' is inferred from the Last indexed column and the raw document panel; the second hit is a different address (g.silva76.jr), with no name and no customer reference.
