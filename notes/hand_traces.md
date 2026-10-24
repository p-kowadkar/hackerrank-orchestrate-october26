# Hand traces of sample cases (Task A)

Each entry shows how the expected output follows from the data. Probes were throwaway scripts; the
quoted values are real. "Golden" = the row in `sample_output.csv`. Notation: `FIND` finding,
`REM` remediation, `VER` verification; `@ev` = cited evidence id.

## COMPLETE, 1 step: gone account (case_01, case_02)
- Request: amina.elmasri@gmail.com -> `user_01`; case_02 reported PARTIALLY_COMPLETE.
- Activity: `DELETE_RECORD account_001 SUCCESS` (case_01), `account_002 PARTIAL` (case_02), both within
  minutes of `reported_at`. A claim only.
- `evidence_54` (accounts SQL, captured 09-02T23:00, before both audits): neither `customer_profiles_primary`
  nor `customer_profiles_failover_replica` has `account_001` / `account_002`.
- Golden: `VER VERIFY_RECORD_ABSENT account_service/account_00N @evidence_54`. The id comes from the worker event
  (hero-case numbering), the proof from the snapshot that covers accounts and lacks the row.

## COMPLETE, 2 steps: anonymized analytics (case_04)
- Text: "keep anonymous statistics, but nothing in analytics should still point back to me."
- `evidence_56` (analytics report, 09-07T09:45, audit 09-07T10:20): `analytics_901` has user_id / email /
  phone / hash all null (anonymized); `analytics_824` carries someone else's identifiers (decoy).
- Golden: `VER ABSENT account_004 @evidence_54`, `VER ANONYMIZED analytics_901 @evidence_56`.
- Gap: `account_004` and the link of `analytics_901` to this user appear in no participant file (elimination
  only).

## INCOMPLETE, 3 steps: ghost row in the failover replica (case_05)
- Text: "I deleted this account and received a confirmation, but the same email address is still recognized."
- Activity: `DELETE_RECORD account_005 SUCCESS` then `SYNC_RECORD ... account_failover_replica` in the same minute.
- `evidence_54`: `customer_profiles_failover_replica` still holds `account_005 | user_05 | Leila Haddad |
  leila.haddad@yahoo.com | ... | ACTIVE`; `customer_profiles_primary` does not.
- Golden: `FIND REMAINING account_005 @evidence_54`, `REM DELETE account_005`, `VER ABSENT account_005`.
- Rule: a replica-only row is a remaining record; the SUCCESS log is a claim.

## INCOMPLETE, 4 steps: PDF attachment (case_07)
- Text: "delete my account and the identity document I sent to support."
- `evidence_58` (PDF, 09-12T07:30, audit 09-12T08:00): "Support reference CS-4827 / support_001", Priya Raman,
  `priya.raman@gmail.com`, +91 98765 73142, file `delivery_address_correction.pdf`, uploader customer.
  The email in the text links it; no LINK event is needed.
- Golden: `FIND REMAINING support_001 @evidence_58`, `REM DELETE support_001`, `VER ABSENT account_007`,
  `VER ABSENT support_001`. `account_007` comes from the worker event (SUCCESS 09-01T19:28).

## INCOMPLETE, 4 steps: log-only support record (case_10)
- Text: "used this Yahoo address before changing the email ... remove records linked to both addresses."
  Request email is the *old* email; the identity resolver maps it to `user_10`.
- `evidence_61` (`support_replica.log`, 09-17T22:00 <= audit 09-18T12:25): `contact_query_started
  lookup_key=nadia.ionescu@yahoo.com` -> `contact_query_completed resource_id=support_002 rows=1` ->
  `deletion_marker_check resource_id=support_002 marker_found=false`.
- Golden: `FIND REMAINING support_002 @evidence_61`, `REM DELETE`, `VER ABSENT account_010`, `VER ABSENT support_002`.

## INCOMPLETE, 5 steps: restore risk from a typed inventory (case_09)
- `evidence_93` (typed inventory SQL, 09-16T08:37, audit 09-16T09:00): `backup_restore_entries` row
  `backup_4978 | customer_email k.appiah88@gmail.com | restore_allowed 1`.
- Golden: `FIND RESTORE_RISK backup_4978 @evidence_93`, `REM BLOCK_RESTORE`, `VER ABSENT account_3960`,
  `VER PRESENT audit_record_4902`, `VER RESTORE_BLOCKED backup_4978`.
- `account_3960` and `audit_record_4902` are linked only by `evidence_06` (captured 09-18, 2 days after the
  audit): identity only. The account has no admissible evidence of presence, so it is verified as absent.
  A later log with line times before 09:00 does not make it citeable.

## INCOMPLETE, 5 steps: active flow and restore risk from a log (case_15, case_17)
- Both cite `evidence_01` (key=value log, 09-15T11:59). Lines are grouped by `trace_id`; the identifier is on the
  `*_started` line, the resource on the later line.
- case_15: `connector_config_read_started subject_key=lucia-torres@gmail.com` ... `resource_id=data_flow_9846
  event=connector_heartbeat enabled=true scheduler_registered=true last_run=success` -> ACTIVE.
  `account_4745`: `profile_lookup_completed rows=0 http_status=404` -> absent (the worker said SUCCESS).
- case_17: `restore_policy_check_started subject_key=leonie.g9352@outlook.com` ... `resource_id=backup_3245
  event=restore_candidate_evaluated eligible=true deletion_block=false` -> restorable. Its account
  `account_4092` shows `profile_lookup_completed rows=0 http_status=404` (absent) although the worker
  event says `FAILED`.
- Golden (15): `FIND ACTIVE_DATA_FLOW`, `REM DISABLE_DATA_FLOW`, `VER ABSENT account`, `VER PRESENT audit`, `VER FLOW_DISABLED`.
  Golden (17): same shape with `RESTORE_RISK`, `BLOCK_RESTORE`, `VERIFY_RESTORE_BLOCKED`.

## INCOMPLETE, 8 steps: two violations in one handover ledger (case_13)
- `evidence_03` (handover text, 10-01T12:00 = audit) rows for `noor-khalil@proton.me`:
  `account_9335 USER_PROFILE NOT_FOUND`, `search_1308 SEARCH_INDEX_ENTRY FOUND`,
  `support_4218 SUPPORT_ATTACHMENT FOUND`; `audit_record_4816 SECURITY_AUDIT_LOG FOUND user_33`.
- Activity says every worker call FAILED, including the account delete; the ledger says the account is gone.
  Observation wins, so the account is *not* a finding.
- Golden: findings for search and support (REMAINING, since an attachment is deleted, not redacted), two
  DELETEs, four verifications (account absent, search absent, support absent, audit present). Ordering inside
  VERIFICATION follows operation order (ABSENT x3 sorted by system, then PRESENT).

## INCOMPLETE, 14 steps: all four violation kinds (case_11, case_29, case_18, case_30)
- case_11 (`evidence_03`): `search_052 FOUND`, `analytics_2034 IDENTIFIABLE`, `support_864 SUPPORT_MESSAGE
  IDENTIFIABLE`, `data_flow_9522 DATA_FLOW ACTIVE`; compliant: `account_4248 NOT_FOUND`,
  `audit_record_9394 FOUND user_32`.
- Mapping: search -> REMAINING + DELETE; analytics -> EXPOSED_PII + ANONYMIZE; support message -> EXPOSED_PII +
  REDACT; flow -> ACTIVE_DATA_FLOW + DISABLE.
- Step layout (4 FIND, 4 REM, 6 VER): FIND order REMAINING, EXPOSED_PII x2 (analytics before support), ACTIVE_DATA_FLOW;
  REM order DISABLE_DATA_FLOW, DELETE, REDACT, ANONYMIZE; VER order ABSENT x2, PRESENT, REDACTED, ANONYMIZED,
  FLOW_DISABLED. This is the operation table order, then `system_id`, then `resource_id`.
- case_29 uses `evidence_92` (JSON readback): the records carry the user's *old* email
  (`noah.f438085@outlook.com`) while a post-audit bundle shows the new one. Both forms resolve to `user_29`.

## COMPLETE, 6 steps: everything compliant (case_26, case_27, case_28)
- case_26 (`evidence_92`, audit 09-15T12:00): account lookup 404; analytics profile all null; support ticket
  `requester_*` null with `customer_reference user_26`; connector `enabled=false`; backup `restore_allowed=false`;
  audit record `subject_reference user_26`.
- Golden: `VER ABSENT account`, `PRESENT audit`, `REDACTED support`, `ANONYMIZED analytics`, `FLOW_DISABLED`,
  `RESTORE_BLOCKED`, all citing `evidence_92`. A stale 09-09 bundle snapshot (account ACTIVE) and a 09-17 one
  are excluded by the clock rules.
- reported_status NOT_STARTED, activity says DELETE FAILED, verdict COMPLETE: the readback outranks both.

## Readback beats the log, both ways (case_24, case_25)
- case_25: `DELETE_RECORD account_3136 FAILED`; `evidence_92` -> `status_code 404, profile null`. Golden COMPLETE.
- case_24: `DELETE_RECORD account_5334 SUCCESS`; `evidence_92` -> profile 200 with email. Golden INCOMPLETE:
  `FIND REMAINING account_5334` and `search_5577` @evidence_92.

## Tombstone (case_31 compliant, case_32 exposed)
- `evidence_51` (bundle, 09-15T12:00 = audit). `tombstone_440` (user_541): name/email/phone/hash all null ->
  `VER REDACTED @evidence_51` (case_31, COMPLETE). `tombstone_9178` (user_542): "Kofi Addo",
  `addo.kofi@gmail.com`, phone and hash present -> `FIND EXPOSED_PII`, `REM REDACT`, `VER REDACTED` (case_32).
- Account is verified absent in both: `account_service customer_profiles` snapshot has zero records.

## What the traces do not explain
- Which of 2-3 same-window accounts belongs to which case when no evidence names the account (about 22%).
- `audit_record_6645` (case_18), `audit_record_5569` (case_20), `account_004` (case_04): in no data file.
- Case_04's absence proof cites `evidence_54` although the later scope-only `evidence_90` also proves it.
