# Evidence state catalog (how each format says present / absent / active)

Everything below was measured on `dataset/` only. "Sample truth" means at least one of the 32 sample
answers exercises that format; otherwise the semantics are inferred and need a test case of our own.

## 1. Clock rules (what counts as evidence at `audit_at`)

1. **File gate.** A file is usable for state and for citation only if the manifest `captured_at` is
   <= `audit_at`. Verified: 75/75 cited sample steps cite such a file; 71 are the latest one that
   mentions the resource, the other 4 are absence proofs.
2. **Record gate.** Inside a usable file, a record dated after `audit_at` is ignored. The dates are
   `recorded_at`, `observed_at`, `updated_at`, log-line timestamps. Planted examples (all
   COMPLETE-reported cases): case_383 `account_5043` NOT_FOUND at 04-09T12:00 then FOUND at 04-11 (ignore the
   later one), case_135 `account_1417` NOT_FOUND 08-12T09:00 then FOUND 08-14, case_86 `account_8473`
   FOUND 08-31 then NOT_FOUND 09-06T07:00 (= audit, gone).
3. **Latest wins.** When a resource has several admissible observations, the newest decides, in both
   directions (FOUND -> NOT_FOUND = it was removed; NOT_FOUND -> FOUND = it came back).
   Case_34: a 09-15 log says 404, a 09-26 screenshot shows the account live, so it is present.
4. **Claims never decide.** `system_activity.csv` results and `reported_status` are hints. They are
   used to find resource ids, not to establish state.
5. **Identity is not state.** Evidence captured after `audit_at` may still be used to learn that a resource
   id belongs to the user (audit records, accounts). Examples: case_29's `audit_record_3954` (+2 days),
   case_09's `audit_record_4902` (+2 days), hero cases whose ids appear only in `evidence_01` (09-15) or
   `evidence_02` (09-17), up to +188 days. It must never supply state or a citation.
6. **Absent by default.** Accounts that no admissible observation shows as present are verified as
   ABSENT (they are always listed in verification). Non-account resources get a finding only when an
   admissible observation shows a violation.
7. **Multi-case users.** Three users have two cases at different dates (07, 17, 18). Resource sets are
   per case, so link by identity and then keep only resources compatible with that case's date
   (e.g. `support_001` was submitted 18 Jun 2026, after case_61's audit of 02-14).

## 2. Batch structure (explains where evidence comes from)

- Eval cases form 46 batches of 10 (plus ~25 singletons: the 12 image/PDF cases, the 10
  non-deletion cases, a few stragglers). Batch `audit_at` values are about 5 days apart.
- Each batch has one **home file** captured 0-60 minutes before `audit_at` that holds the 10 cases'
  resources. Formats rotate through about nine families over the year.
- A **late bundle** or log (+2 days) is exported after each batch. It contains the same cases'
  at-audit state plus older, stale snapshots. Per the clock rules it is identity-only.
- The 09-15T12:00 batch is made of 15 *sample* cases only, so `evidence_01/02/51/92` serve samples.
  Sample truth therefore covers the formats below, and nothing else.

| family | home files (eval) | sample truth |
|---|---|---|
| JSON readback `service_resource_export_*` | 62, 65, 68, 71, 74, 77, 80, 83, 86, 89 | yes, `evidence_92` (9 samples) |
| typed inventory SQL `customer_data_inventory_*` | 63, 66, 69, 72, 75, 78, 81, 84, 87, 93 | yes, `evidence_93` (case_09) |
| lookup-trace log `resource_lookup_trace_*` | 64, 67, 70, 73, 76, 79, 82, 85, 88, 91, 94 | yes, `evidence_94` (3) |
| read-replica SQL | 10, 15, 20, 24, 05 | yes, `evidence_05` (2) |
| handover/ledger text | 03 | yes (3) |
| bundles (JSON snapshots) | 07, 12, 17, 22, 26, 31, 35, 40, 45, 49 (+02, 51) | partly, `evidence_51` (2) |
| reporting-replica SQL | 43, 47 | no |
| regional-replicas SQL | 29, 33, 38 | no |
| failover generic SQL (`record_json`) | 52 | no (sample case_05 uses the typed accounts failover `evidence_54`) |
| ledger-style logs / JSON manifests | 08, 41, 13, 36, 50 | `evidence_03` only |
| free logs, other dialects (pipe, bracket, syslog, JSON lines, cloud-runtime) | 06, 11, 16, 21, 25, 34, 39, 44, 48, 53 | no (only key=value: `evidence_01`, and `evidence_30` is also key=value) |

## 3. Record types -> policy action (from `deletion_rules.csv` and the samples)

| record | present means | finding | remediation | verification |
|---|---|---|---|---|
| USER_PROFILE (account) | profile row / 200 / FOUND | REPORT_REMAINING_RECORD | DELETE_RECORD | VERIFY_RECORD_ABSENT (always listed) |
| SECONDARY_IDENTIFIER, CACHE_ENTRY, EMAIL_DELIVERY_LOG | never observed: `cache_*` (284 activity rows) and `email_delivery_*` (368) appear in no evidence file, so no step can come from them | none | none | none |
| SEARCH_INDEX_ENTRY | hit / FOUND / row | REPORT_REMAINING_RECORD | DELETE_RECORD | VERIFY_RECORD_ABSENT |
| USER_EXPORT | row / `available` true / FOUND | REPORT_REMAINING_RECORD | DELETE_RECORD | VERIFY_RECORD_ABSENT |
| MARKETING_PROFILE | live profile | REPORT_REMAINING_RECORD | DELETE_RECORD | VERIFY_RECORD_ABSENT |
| SUPPORT_ATTACHMENT (own only) | file listed / FOUND / `attachment_pii_scan` | REPORT_REMAINING_RECORD | DELETE_RECORD | VERIFY_RECORD_ABSENT |
| SUPPORT_MESSAGE (shared context) | requester email/name/phone non-null, IDENTIFIABLE, `message_pii_scan` | REPORT_EXPOSED_PII | REDACT_RECORD | VERIFY_RECORD_REDACTED |
| ANALYTICS_PROFILE | any of user_id/email/phone/hash non-null, IDENTIFIABLE | REPORT_EXPOSED_PII | ANONYMIZE_RECORD | VERIFY_RECORD_ANONYMIZED |
| ACCOUNT_TOMBSTONE | name/email/phone/hash still present | REPORT_EXPOSED_PII | REDACT_RECORD | VERIFY_RECORD_REDACTED |
| DATA_FLOW | `enabled` true, ACTIVE, continuous sync | REPORT_ACTIVE_DATA_FLOW | DISABLE_DATA_FLOW | VERIFY_DATA_FLOW_DISABLED |
| BACKUP_ARCHIVE | `restore_allowed` true, ACTIVE, `eligible`+`deletion_block=false` | REPORT_RESTORE_RISK | BLOCK_RESTORE | VERIFY_RESTORE_BLOCKED |
| SECURITY_AUDIT_LOG | row / FOUND (within retention) | none | none | VERIFY_RECORD_PRESENT |
| LEGAL_HOLD_RECORD | hold active | none | none | VERIFY_RECORD_PRESENT (inferred, no sample) |

`system_id` equals the activity stream's `target_system` for that resource type (e.g.
`account_service`, `search_service`, `support_platform`, `analytics_platform`, `export_service`,
`integration_service`, `backup_service`, `identity_service`, `security_service`; also seen in activity:
`marketing_platform`, `object_storage`, `legal_service`). The last three never occur in a sample answer.

## 4. Per-format state signals

**Ledger text/log/JSON (`evidence_03`, 08, 41, 13, 36, 50).** One line or record per resource:
`system | resource_id | record_type | result | subject_reference` where the last column is an email
(sometimes upper-cased) or a `user_N`. Results seen: FOUND, NOT_FOUND, IDENTIFIABLE, ANONYMIZED, ACTIVE,
DISABLED, BLOCKED, REDACTED. JSON ledgers carry `recorded_at` per record (clock rule 2).

**JSON readback (`service_resource_export_*`, families `service_exports.<service>.<collection>`).**
- `account_service.profile_lookups[]`: `status_code` 404 + `profile: null` = absent; 200 + profile = present.
  A 404 carries no identifier at all.
- `analytics_platform.profiles[]`: all of `customer_reference/email/phone/email_hash` null = anonymized.
- `search_service.index_queries[]`: `hits.total`, `hits.documents[]`; a query that returns another person's
  near-duplicate email is a decoy.
- `support_platform.tickets[]`: `requester_*` null = redacted (`customer_reference` stays).
- `integration_service.connectors[]`: `enabled`, `last_delivery_status` (stopped / delivered).
- `backup_service.restore_entries[]`: `restore_allowed`. `export_service.exports[]`: `object_key`, owner.
- `security_service.audit_records[]`: `subject_reference`, `retention_until`.
- Every item has `observed_at`.

**Typed inventory SQL.** `snapshot_scope(origin_system, captured_at)` lists the systems the snapshot
covers; a missing row is absence only for a covered system (`evidence_90` covers `account_service` only
and has no profile rows). Tables: customer_profiles (`account_status` ACTIVE or DELETION_PENDING),
customer_search_documents, customer_analytics_profiles, support_records, customer_exports,
connector_subscriptions (`enabled`), backup_restore_entries (`restore_allowed`), security_audit_records.
`customer_reference` is `user_N` or null.

**Generic SQL (read / reporting / regional / failover replicas).** `customer_data_primary` plus one or
more replica tables with `(resource_id, origin_system, collection_name, record_json, updated_at)`.
Compare tables: a row only in a replica is a ghost; rows in both are plain remaining copies. Collections
seen: customer_profiles, customer_search_documents, customer_analytics_reports, support_conversations,
ticket_attachments, customer_export_jobs, connector_configurations, backup_catalog,
security_audit_events, retained_order_records, deleted_customer_references (tombstones).

**Typed accounts SQL (`evidence_54`).** `customer_profiles_primary` vs `customer_profiles_failover_replica`
with identifiers inline. Row only in the failover table = ghost (case_05).

**Bundles.** `snapshots[]` each with `captured_at`, `data_store`, `collection`, `records[]`. Some bundles
use ledger-style records with their own `recorded_at` and a `lookup_value` instead. Stale older snapshots
appear next to the at-audit one.

**Logs (7 dialects, one event vocabulary).** Group lines by trace id; the identifier is in `lookup_key`,
`match_key`, `subject_key`, `owner_key`, `scan_key`, `correlation_key` or `subject_ref`.
- `profile_lookup_completed`: `rows=0 http_status=404` absent, `rows=1 200` present.
- `index_query_completed`: `result=hit|miss`.
- `connector_config_read_completed` / `connector_heartbeat` / `connector_config_loaded`: `enabled`,
  `scheduler_registered` (both were equal in every observed line).
- `restore_policy_read_completed`: `restore_allowed`, `archive_present`. `restore_candidate_evaluated`:
  `eligible=true deletion_block=false` = restorable. `restore_authorization_completed`: `decision=deny
  policy=privacy_deletion` = blocked.
- `support_ticket_read_completed`: requester fields; `message_pii_scan` / `attachment_pii_scan`:
  `matched_value`, `detector=direct_identifier`, `file`. `message_read`: `message_text`.
- `analytics_profile_read_completed` / `analytics_profile_read` (`direct_identifiers` 0/1) /
  `analytics_identity_scan` (`matched_value`).
- `export_download_check_completed` / `export_metadata_read_completed`: `available`.
- `deletion_marker_check`: `marker_found` (support replica).
- `retained_order_loaded` (legal_service): `reason`, `access=allowed`, resource `legal_hold_N`.
- Noise to drop: `connection_acquired`, `dependency_retry` (reason `read_timeout`), `dependency_recovered`,
  `cache_lookup`, `export_started/completed`, `pool_sample`, heartbeats of infra services, `circuit_breaker`.

## 5. Open semantic questions (no sample truth)

- Is `account_status = DELETION_PENDING` "present"? (Expected: yes, still a remaining record.)
- Does an expired export (`expires_at` < `audit_at`, `download_available=false`) count as present? Case_33.
- Legal-hold step shape and when it is included.
- `system_id` for object storage / marketing / legal records.
- Whether `resource_id` ties sort as strings or numbers (no sample has a same-system tie).
- Which formats' multi-observation ordering uses `recorded_at` vs file order (only ledger-style files have it).
