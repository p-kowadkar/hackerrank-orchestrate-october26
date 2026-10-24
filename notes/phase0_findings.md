# Phase 0 findings (investigation only, no solution code)

Everything here was measured against `dataset/` only. Probe scripts were throwaway and lived in the
session scratchpad. Counts are exact unless marked "approx".

## Dataset shape
- 32 sample cases (`case_01`..`case_32`) and 518 eval cases (`case_33`..`case_550`). Disjoint.
- 850 users. Every one of the 550 request emails resolves to exactly one user: 447 via the current
  email, 103 via a historical `old_value` in `user_audit_log.csv`. 20 emails are upper-case, so matching
  must be case-insensitive.
- Eval cases come in batches that share one `audit_at` and one evidence snapshot (72 distinct
  `audit_at` values; 46 batches of 10). Inside a batch, cases share `reported_at` in groups of up to 3.
- Only 2 eval emails reuse a sample user (case_46, case_61), both at an earlier `audit_at`.

## Output contract, verified on all 32 samples (0 violations)
- Steps sorted by (phase, operation in the problem-statement table order, `system_id`, `resource_id`).
  `step_no` is 1..n. `state` is fixed per operation.
- `evidence_id` is empty for every REMEDIATION step, and for VERIFICATION steps of INCOMPLETE cases.
  It is non-empty for FINDING steps and for VERIFICATION steps of COMPLETE cases.
- Untested: whether `resource_id` ties sort as strings or numbers (no sample has the case).

## Verdict logic
- `reported_status` is not predictive. Crosstab on samples: COMPLETE reported -> 11/17 are INCOMPLETE;
  NOT_STARTED -> 3/10 are COMPLETE.
- Claims in `system_activity.csv` are not truth. Case_25: log says DELETE FAILED, JSON readback shows
  404, answer COMPLETE. Case_24: log says DELETE SUCCESS, readback shows a live profile, answer
  INCOMPLETE.
- Ghost mechanism (case_05, case_16): in SQL snapshots, a row present in the replica table but not in
  primary is a remaining record. Rows in both are plain remaining copies.
- INCOMPLETE verification = account ABSENT (always) + audit record PRESENT + the target state of every
  remediated resource. COMPLETE verification = the compliant state of every relevant resource.
- Absence is proven by a snapshot that covers the owning system and lacks the record.
- Ledger/readback record types map straight onto policy: SEARCH_INDEX_ENTRY FOUND -> DELETE;
  SUPPORT_ATTACHMENT FOUND -> DELETE; SUPPORT_MESSAGE IDENTIFIABLE -> REDACT; ANALYTICS_PROFILE
  IDENTIFIABLE -> ANONYMIZE; DATA_FLOW ACTIVE -> DISABLE; BACKUP_ARCHIVE ACTIVE/restore_allowed ->
  BLOCK_RESTORE (backup is retained, restore is blocked); USER_EXPORT FOUND -> DELETE; tombstone with
  name/email/phone/hash present -> REDACT; SECURITY_AUDIT_LOG -> RETAIN (verify present).

## NOT_APPLICABLE
- Exactly 10 cases: `case_533`..`case_542` (users 531..540). Request texts are plainly non-deletion.
- Corroboration: 10 `CLASSIFY_REQUEST` events ("non-deletion") keyed by account id, and
  `security_audit_ledger_20261001.json`, which maps each of those account ids to the request email.
- All 508 other eval texts are templated deletion language in 6 languages (67 distinct sentences).

## Evidence formats
- Logs: 7 dialects (key=value, JSON lines, syslog, bracketed, `requestId/message`, pipe, ledger).
  Lines group by trace id; `lookup_key`/`subject_key`/`correlation_key` carry the identifier.
- SQL: 4 layouts (typed accounts, generic primary+replicas with `record_json`, typed inventory with
  `snapshot_scope`, search primary). Loads cleanly into in-memory SQLite.
- JSON: readback exports, snapshot bundles, ledgers, export jobs. TXT: handover ledger.
- PDFs (4): text extracts with `pdftotext`; no LLM needed.
- Images (11): clean UI renders; need vision or OCR. No `tesseract` installed.

## User -> resource linkage
1. Direct tokens in the same record: email (current or historical, case-insensitive), `user_id`
   (`customer_reference` / `subject_reference` / `lookup_key`), `email_hash` (current or historical),
   phone, name. Case_12's analytics record is matched by the *old* email's hash only.
2. Images and the account-history PDF: 12 `LINK_RESOURCE_IDENTITY` events. Each is the capture time +
   7m01s of exactly one image/PDF and names the subject's resource, email and user. Screenshots also
   contain decoys. The marketing screenshot shows a person who exists nowhere in `user_identities`, so
   the LINK event, not the picture, decides identity.
3. Identity links may use evidence captured after `audit_at` (case_29's audit record, +2 days; hero
   cases up to +188 days). State and citations may not. Each user has at most one visible audit record
   (`subject_reference`); 446 of 540 deletion cases have a discoverable one and 94 have none. Resource sets
   are per case, not per user (users 07, 17, 18 each have two cases at different dates), so identity links
   must be filtered by time compatibility with the case.
4. Residual: accounts that are gone and anonymized analytics have no identifier. Account ids come from
   `DELETE_RECORD -> account_service` worker events (539 of them, ~1:1 with deletion cases). For
   generated families the true event is 45-74 min before `reported_at`. The worker result also tracks
   `reported_status` (SUCCESS=COMPLETE, PARTIAL=PARTIALLY_COMPLETE, FAILED=NOT_STARTED; 255/260 on
   directly linked cases, 5 exceptions). With window + exclusion of accounts owned by others + that
   mapping + propagation: 422/540 accounts resolved; 118 stay ambiguous or unresolved (82 with 2
   candidates, 26 with 3, 3 with 5, 7 with none because an exception case was filtered out). On the
   samples every assignment made was correct (26/26); the rest were left ambiguous.
5. Not derivable at all in the samples: `audit_record_6645` (case_18), `audit_record_5569` (case_20),
   `account_004` (case_04). They appear in no participant file.

## Evidence citation
- 71/75 cited sample steps equal the latest file by manifest `captured_at` that is <= `audit_at`
  and mentions the resource. File-level `captured_at` governs, not per-line log timestamps.
- The other 4 are absence proofs: 3 follow "latest snapshot of the owning system <= audit_at".
  Case_04 cites `evidence_54` although the later scope-only snapshot `evidence_90` also proves absence.

## Time traps found (full rules in `evidence_state_catalog.md`)
- Files gate on manifest `captured_at`; records inside a usable file gate on their own timestamp. Planted
  later records exist (case_383, case_135). Stale older snapshots sit next to fresh ones in bundles.
- Case_34: older log says 404, newer screenshot shows the account live, so the newest direct evidence wins.
- Case_26/27: a bundle holds a stale 09-09 snapshot (account_5684 ACTIVE) and a post-audit 09-17 snapshot
  (account_3866 ACTIVE); the golden answers ignore both and follow the 09-15 readbacks.

## Batch structure
Eval cases come in 46 batches of 10 (about 5 days apart), each served by one home evidence file in one of
about nine rotating formats, plus late bundles. Six families have sample truth. Eight variants have none:
three replica layouts (reporting, regional, failover-generic) and five log dialects (pipe, bracket, syslog,
JSON lines, cloud-runtime). Ledger-style logs/manifests are covered only by the handover text.
Details and the coverage table are in `evidence_state_catalog.md`. Image/PDF cases are in
`evidence_artifacts.md`.

## Unknown / not testable from samples
- Legal-hold handling (no sample has `legal_service`; appears only in eval-only evidence). The legal
  register PDF lists six sample users yet no sample answer has a legal step.
- State rules for regional/reporting/failover-generic replicas and the non-key=value log dialects.
- `system_id` for object storage, marketing and legal records; DELETION_PENDING; expired exports.
- Grader weighting and tie-break order for `resource_id`.
- The challenge end time is not configured in the repo.

## Environment
No OpenRouter key until tomorrow. An earlier test showed `openrouter.ai` returning 403 on CONNECT from the
sandbox proxy and no `OPENROUTER_API_KEY` in the environment; it was deliberately not retested. All Phase 0
work was done without any LLM call. When the key exists, the network policy must also allow the host.
