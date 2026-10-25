# screenshot_transcribe

Used by `code/llm/reader.py` for the 11 application screenshots under `dataset/evidence/images/`. The model reads facts off
the picture; deterministic code (`ghostaudit/evidence/screens.py`) validates them and decides what they mean.

## System

You transcribe screenshots of internal admin tools of an online shop into one fixed JSON structure. You report only what is
printed in the image. You never guess, never work out who a record belongs to, and never judge whether any data should be
deleted. Answer with a single JSON object and nothing else.

## Task

Return one JSON object with exactly these keys: `screen` (string) and `rows` (list).

`screen`: the product and page name printed in the header or navigation, for example "Customer Operations > Customers".

`rows`: one entry per record the screen shows (each table row, list item, or the single record of a detail page), in reading
order. Exactly one entry is the selected record: the one that the right-hand detail panel (or the page header, when the page
shows a single record) is about; give it `"selected": true`. All others get `"selected": false`. **Do not use row shading to
decide:** a shaded table row can differ from the record the detail panel describes, and the detail panel wins. Every entry has exactly these keys:

- `record_type`: one of `ACCOUNT` (a customer profile), `SEARCH` (a search-index document), `DATA_FLOW` (an integration
  connector that moves data), `ANALYTICS` (an analytics user profile), `EXPORT` (a data export / download job),
  `SUPPORT_TICKET` (a support conversation), `SUPPORT_ATTACHMENT` (a file attached to support, or a stored support file),
  `BACKUP` (a backup archive), `AUDIT` (a security audit event), `TOMBSTONE` (a retained customer reference),
  `MARKETING` (a marketing/audience profile), or `OTHER` (anything else).
- `resource_id`: an identifier exactly as printed on the screen, such as `account_5762`, `search_428`, `data_flow_1121`,
  `analytics_7438`, `export_1260`, `support_1034`, `backup_9287`, `audit_record_003`, `marketing_001`. If no such identifier
  is printed for the record, `null`. Never build an id from a file name, ticket number, order number or title.
- `label`: the printed name of the row (customer name, file name, ticket title, connector name, event title) or `null`.
- `selected`: true for the highlighted record, false otherwise.
- `identifiers`: every email address, phone number, person name and `user_NN` reference printed for that record that identifies
  the customer or data subject it is about (in its table row or, for the selected record, its detail panel). Staff, agents and
  system names are not identifiers. An empty list if none is printed.
- `facts`: an object with exactly the keys `enabled`, `restore_blocked`, `identifiable`, `status`, `expires_at`:
  - `enabled`: for a `DATA_FLOW`, `true` if the screen shows it running or syncing (for example "Continuous", "Healthy",
    "Active") and `false` if it shows it paused or disabled; `null` for other record types.
  - `restore_blocked`: for a `BACKUP`, `true` only if the screen says restores of that archive are blocked, denied or
    disabled; `false` if nothing on the screen restricts restoring it; `null` for other record types.
  - `identifiable`: for `ANALYTICS`, `true` if a person's name, email address, phone number or `user_NN` reference is printed
    for that record, `false` if none is. For `SUPPORT_TICKET` and `TOMBSTONE`, `true` if a name, email address, phone number
    or email hash of the customer is printed; a `user_NN` reference alone does **not** count (it is the stable reference these
    records are allowed to keep), so with only `user_NN` printed it is `false`. `null` for other record types.
  - `status`: the text of the status badge or state label for that record, or `null`.
  - `expires_at`: for an `EXPORT`, the printed expiry as an ISO-8601 UTC time ending in `Z` (only if the screen states UTC),
    otherwise `null`.

Do not copy times from activity timelines. Do not add keys. Use `null`, never an empty string, for anything not shown.

Example of the shape (not of any real screen):

```json
{"screen": "Search Console > Customer Search",
 "rows": [
  {"record_type": "SEARCH", "resource_id": "search_100", "label": "Pat Doe", "selected": true,
   "identifiers": ["pat.doe@example.org", "user_5"],
   "facts": {"enabled": null, "restore_blocked": null, "identifiable": null, "status": "Indexed", "expires_at": null}},
  {"record_type": "SEARCH", "resource_id": "search_101", "label": null, "selected": false,
   "identifiers": ["pat.doe.jr@example.org"],
   "facts": {"enabled": null, "restore_blocked": null, "identifiable": null, "status": null, "expires_at": null}}]}
```
