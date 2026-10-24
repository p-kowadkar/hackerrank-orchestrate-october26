# Hand-derived expectations for the 12 image/PDF cases (UNVERIFIED)

These are **my own reading** of the screenshots and PDFs against `deletion_rules.csv`. They are not ground truth, were
not produced by the organizers, and **never enter the headline accuracy numbers**. The scorer reports them in a
separate section. Each entry lists only the core steps I am confident about (`required_steps`); the golden answer
will probably contain more (the user's account, an audit record), so the check is "required steps present and status
equal", not exact match. `system_id` is deliberately not compared. Details of each artifact: `code/notes/evidence_artifacts.md`.

## case_33: Ingrid Dahl, audit 07-19T13:00

Status INCOMPLETE; confidence medium. Statement PDF is a user export with PII. export_1260 (expired 06-25) is deliberately not required: its state at the audit date is undecided.

```json
{
 "case_id": "case_33",
 "status": "INCOMPLETE",
 "confidence": "medium",
 "note": "Statement PDF is a user export with PII. export_1260 (expired 06-25) is deliberately not required: its state at the audit date is undecided.",
 "required_steps": [
  {
   "phase": "FINDING",
   "resource_id": "export_1842",
   "operation": "REPORT_REMAINING_RECORD",
   "state": "PRESENT",
   "evidence_id": "evidence_18"
  },
  {
   "phase": "REMEDIATION",
   "resource_id": "export_1842",
   "operation": "DELETE_RECORD",
   "state": "ABSENT",
   "evidence_id": ""
  },
  {
   "phase": "VERIFICATION",
   "resource_id": "export_1842",
   "operation": "VERIFY_RECORD_ABSENT",
   "state": "ABSENT",
   "evidence_id": ""
  }
 ]
}
```

## case_34: Haruka Sato, audit 09-27T13:00

Status INCOMPLETE; confidence high. Older log (09-15) says 404; newer screenshot (09-26) shows the account live, so the newest evidence wins. support_9538 is also likely but not required.

```json
{
 "case_id": "case_34",
 "status": "INCOMPLETE",
 "confidence": "high",
 "note": "Older log (09-15) says 404; newer screenshot (09-26) shows the account live, so the newest evidence wins. support_9538 is also likely but not required.",
 "required_steps": [
  {
   "phase": "FINDING",
   "resource_id": "account_5762",
   "operation": "REPORT_REMAINING_RECORD",
   "state": "PRESENT",
   "evidence_id": "evidence_04"
  },
  {
   "phase": "REMEDIATION",
   "resource_id": "account_5762",
   "operation": "DELETE_RECORD",
   "state": "ABSENT",
   "evidence_id": ""
  },
  {
   "phase": "VERIFICATION",
   "resource_id": "account_5762",
   "operation": "VERIFY_RECORD_ABSENT",
   "state": "ABSENT",
   "evidence_id": ""
  }
 ]
}
```

## case_35: Gabriel Silva, audit 09-02T08:00

Status INCOMPLETE; confidence high. search_1874 is a near-duplicate email belonging to someone else and must not appear.

```json
{
 "case_id": "case_35",
 "status": "INCOMPLETE",
 "confidence": "high",
 "note": "search_1874 is a near-duplicate email belonging to someone else and must not appear.",
 "required_steps": [
  {
   "phase": "FINDING",
   "resource_id": "search_428",
   "operation": "REPORT_REMAINING_RECORD",
   "state": "PRESENT",
   "evidence_id": "evidence_09"
  },
  {
   "phase": "REMEDIATION",
   "resource_id": "search_428",
   "operation": "DELETE_RECORD",
   "state": "ABSENT",
   "evidence_id": ""
  },
  {
   "phase": "VERIFICATION",
   "resource_id": "search_428",
   "operation": "VERIFY_RECORD_ABSENT",
   "state": "ABSENT",
   "evidence_id": ""
  }
 ]
}
```

## case_39: Aditi Jain, audit 08-08T10:00

Status INCOMPLETE; confidence high. Continuous sync to the analytics warehouse, healthy.

```json
{
 "case_id": "case_39",
 "status": "INCOMPLETE",
 "confidence": "high",
 "note": "Continuous sync to the analytics warehouse, healthy.",
 "required_steps": [
  {
   "phase": "FINDING",
   "resource_id": "data_flow_1121",
   "operation": "REPORT_ACTIVE_DATA_FLOW",
   "state": "ACTIVE",
   "evidence_id": "evidence_14"
  },
  {
   "phase": "REMEDIATION",
   "resource_id": "data_flow_1121",
   "operation": "DISABLE_DATA_FLOW",
   "state": "DISABLED",
   "evidence_id": ""
  },
  {
   "phase": "VERIFICATION",
   "resource_id": "data_flow_1121",
   "operation": "VERIFY_DATA_FLOW_DISABLED",
   "state": "DISABLED",
   "evidence_id": ""
  }
 ]
}
```

## case_45: Oliver Bennett, audit 09-06T09:00

Status COMPLETE; confidence medium. Both evidence_37 (09-05T07:00) and evidence_55 (09-05T06:30) are admissible; the latest is cited. Whether the five sibling audit events belong in the answer is unknown.

```json
{
 "case_id": "case_45",
 "status": "COMPLETE",
 "confidence": "medium",
 "note": "Both evidence_37 (09-05T07:00) and evidence_55 (09-05T06:30) are admissible; the latest is cited. Whether the five sibling audit events belong in the answer is unknown.",
 "required_steps": [
  {
   "phase": "VERIFICATION",
   "resource_id": "audit_record_003",
   "operation": "VERIFY_RECORD_PRESENT",
   "state": "PRESENT",
   "evidence_id": "evidence_37"
  }
 ]
}
```

## case_46: Leonie Girard, audit 03-11T08:00

Status COMPLETE; confidence medium. Tombstone holds only the stable key; account lookup is 404. The audit record (probably audit_record_1797) is visible only 188 days later and is not required.

```json
{
 "case_id": "case_46",
 "status": "COMPLETE",
 "confidence": "medium",
 "note": "Tombstone holds only the stable key; account lookup is 404. The audit record (probably audit_record_1797) is visible only 188 days later and is not required.",
 "required_steps": [
  {
   "phase": "VERIFICATION",
   "resource_id": "account_6523",
   "operation": "VERIFY_RECORD_ABSENT",
   "state": "ABSENT",
   "evidence_id": "evidence_67"
  },
  {
   "phase": "VERIFICATION",
   "resource_id": "tombstone_17",
   "operation": "VERIFY_RECORD_REDACTED",
   "state": "REDACTED",
   "evidence_id": "evidence_42"
  }
 ]
}
```

## case_50: Omar Darwish, audit 07-14T12:00

Status INCOMPLETE; confidence high. Profile shows name, email and user id.

```json
{
 "case_id": "case_50",
 "status": "INCOMPLETE",
 "confidence": "high",
 "note": "Profile shows name, email and user id.",
 "required_steps": [
  {
   "phase": "FINDING",
   "resource_id": "analytics_7438",
   "operation": "REPORT_EXPOSED_PII",
   "state": "PRESENT",
   "evidence_id": "evidence_19"
  },
  {
   "phase": "REMEDIATION",
   "resource_id": "analytics_7438",
   "operation": "ANONYMIZE_RECORD",
   "state": "ANONYMIZED",
   "evidence_id": ""
  },
  {
   "phase": "VERIFICATION",
   "resource_id": "analytics_7438",
   "operation": "VERIFY_RECORD_ANONYMIZED",
   "state": "ANONYMIZED",
   "evidence_id": ""
  }
 ]
}
```

## case_52: Ingrid Dahl, audit 06-19T14:00

Status INCOMPLETE; confidence high. Export Ready, 0 downloads, expires 06-25 (after the audit).

```json
{
 "case_id": "case_52",
 "status": "INCOMPLETE",
 "confidence": "high",
 "note": "Export Ready, 0 downloads, expires 06-25 (after the audit).",
 "required_steps": [
  {
   "phase": "FINDING",
   "resource_id": "export_1260",
   "operation": "REPORT_REMAINING_RECORD",
   "state": "PRESENT",
   "evidence_id": "evidence_23"
  },
  {
   "phase": "REMEDIATION",
   "resource_id": "export_1260",
   "operation": "DELETE_RECORD",
   "state": "ABSENT",
   "evidence_id": ""
  },
  {
   "phase": "VERIFICATION",
   "resource_id": "export_1260",
   "operation": "VERIFY_RECORD_ABSENT",
   "state": "ABSENT",
   "evidence_id": ""
  }
 ]
}
```

## case_53: Kofi Agyeman, audit 05-25T09:00

Status INCOMPLETE; confidence medium. Conversation mixes customer identity with agent and order context, so rule_05 REDACT (not delete).

```json
{
 "case_id": "case_53",
 "status": "INCOMPLETE",
 "confidence": "medium",
 "note": "Conversation mixes customer identity with agent and order context, so rule_05 REDACT (not delete).",
 "required_steps": [
  {
   "phase": "FINDING",
   "resource_id": "support_1034",
   "operation": "REPORT_EXPOSED_PII",
   "state": "PRESENT",
   "evidence_id": "evidence_28"
  },
  {
   "phase": "REMEDIATION",
   "resource_id": "support_1034",
   "operation": "REDACT_RECORD",
   "state": "REDACTED",
   "evidence_id": ""
  },
  {
   "phase": "VERIFICATION",
   "resource_id": "support_1034",
   "operation": "VERIFY_RECORD_REDACTED",
   "state": "REDACTED",
   "evidence_id": ""
  }
 ]
}
```

## case_55: Amelia Reed, audit 04-30T11:00

Status INCOMPLETE; confidence high. Archive retained until 2026-07-26 and restore not blocked.

```json
{
 "case_id": "case_55",
 "status": "INCOMPLETE",
 "confidence": "high",
 "note": "Archive retained until 2026-07-26 and restore not blocked.",
 "required_steps": [
  {
   "phase": "FINDING",
   "resource_id": "backup_9287",
   "operation": "REPORT_RESTORE_RISK",
   "state": "ACTIVE",
   "evidence_id": "evidence_32"
  },
  {
   "phase": "REMEDIATION",
   "resource_id": "backup_9287",
   "operation": "BLOCK_RESTORE",
   "state": "BLOCKED",
   "evidence_id": ""
  },
  {
   "phase": "VERIFICATION",
   "resource_id": "backup_9287",
   "operation": "VERIFY_RESTORE_BLOCKED",
   "state": "BLOCKED",
   "evidence_id": ""
  }
 ]
}
```

## case_61: Priya Raman, audit 02-14T10:00

Status INCOMPLETE; confidence medium. system_id for object storage is unconfirmed (probably object_storage); it is not compared here.

```json
{
 "case_id": "case_61",
 "status": "INCOMPLETE",
 "confidence": "medium",
 "note": "system_id for object storage is unconfirmed (probably object_storage); it is not compared here.",
 "required_steps": [
  {
   "phase": "FINDING",
   "resource_id": "object_19",
   "operation": "REPORT_REMAINING_RECORD",
   "state": "PRESENT",
   "evidence_id": "evidence_46"
  },
  {
   "phase": "REMEDIATION",
   "resource_id": "object_19",
   "operation": "DELETE_RECORD",
   "state": "ABSENT",
   "evidence_id": ""
  },
  {
   "phase": "VERIFICATION",
   "resource_id": "object_19",
   "operation": "VERIFY_RECORD_ABSENT",
   "state": "ABSENT",
   "evidence_id": ""
  }
 ]
}
```

## case_63: Kwame Mensah, audit 09-17T09:20

Status INCOMPLETE; confidence medium. The screenshot shows a different person than the LINK event; identity follows the LINK event.

```json
{
 "case_id": "case_63",
 "status": "INCOMPLETE",
 "confidence": "medium",
 "note": "The screenshot shows a different person than the LINK event; identity follows the LINK event.",
 "required_steps": [
  {
   "phase": "FINDING",
   "resource_id": "marketing_001",
   "operation": "REPORT_REMAINING_RECORD",
   "state": "PRESENT",
   "evidence_id": "evidence_60"
  },
  {
   "phase": "REMEDIATION",
   "resource_id": "marketing_001",
   "operation": "DELETE_RECORD",
   "state": "ABSENT",
   "evidence_id": ""
  },
  {
   "phase": "VERIFICATION",
   "resource_id": "marketing_001",
   "operation": "VERIFY_RECORD_ABSENT",
   "state": "ABSENT",
   "evidence_id": ""
  }
 ]
}
```
