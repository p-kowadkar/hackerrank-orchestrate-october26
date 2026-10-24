"""Vocabulary of the output contract, the policy table, and the observation model."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

PHASES = ("FINDING", "REMEDIATION", "VERIFICATION")

# Operation order is the order of the table in problem_statement.md; it is the primary sort key inside a phase.
OPERATIONS = (
    "REPORT_REMAINING_RECORD", "REPORT_EXPOSED_PII", "REPORT_ACTIVE_DATA_FLOW", "REPORT_RESTORE_RISK",
    "DISABLE_DATA_FLOW", "BLOCK_RESTORE", "DELETE_RECORD", "REDACT_RECORD", "ANONYMIZE_RECORD",
    "VERIFY_RECORD_ABSENT", "VERIFY_RECORD_PRESENT", "VERIFY_RECORD_REDACTED", "VERIFY_RECORD_ANONYMIZED",
    "VERIFY_DATA_FLOW_DISABLED", "VERIFY_RESTORE_BLOCKED",
)
OP_PHASE = {op: PHASES[0 if op.startswith("REPORT") else 2 if op.startswith("VERIFY") else 1] for op in OPERATIONS}
OP_STATE = {
    "REPORT_REMAINING_RECORD": "PRESENT", "REPORT_EXPOSED_PII": "PRESENT", "REPORT_ACTIVE_DATA_FLOW": "ACTIVE",
    "REPORT_RESTORE_RISK": "ACTIVE", "DISABLE_DATA_FLOW": "DISABLED", "BLOCK_RESTORE": "BLOCKED",
    "DELETE_RECORD": "ABSENT", "REDACT_RECORD": "REDACTED", "ANONYMIZE_RECORD": "ANONYMIZED",
    "VERIFY_RECORD_ABSENT": "ABSENT", "VERIFY_RECORD_PRESENT": "PRESENT", "VERIFY_RECORD_REDACTED": "REDACTED",
    "VERIFY_RECORD_ANONYMIZED": "ANONYMIZED", "VERIFY_DATA_FLOW_DISABLED": "DISABLED",
    "VERIFY_RESTORE_BLOCKED": "BLOCKED",
}
STEP_FIELDS = ("step_no", "phase", "system_id", "resource_id", "operation", "state", "evidence_id")

# --- normalized record types and states ---------------------------------------------------------------
ACCOUNT, SEARCH, EXPORT, MARKETING = "ACCOUNT", "SEARCH", "EXPORT", "MARKETING"
SUPPORT_ATTACHMENT, SUPPORT_MESSAGE = "SUPPORT_ATTACHMENT", "SUPPORT_MESSAGE"
ANALYTICS, TOMBSTONE, DATA_FLOW, BACKUP = "ANALYTICS", "TOMBSTONE", "DATA_FLOW", "BACKUP"
AUDIT, LEGAL_HOLD = "AUDIT", "LEGAL_HOLD"

PRESENT, ABSENT = "PRESENT", "ABSENT"
EXPOSED, CLEAN = "EXPOSED", "CLEAN"
ACTIVE, DISABLED = "ACTIVE", "DISABLED"
RESTORABLE, BLOCKED = "RESTORABLE", "BLOCKED"
LINK = "LINK"  # identity-only observation: the record names the resource but says nothing about its state

# Within one type, a "worse" state wins when several copies of the same record are seen at the same moment.
VIOLATING = {ACCOUNT: PRESENT, SEARCH: PRESENT, EXPORT: PRESENT, MARKETING: PRESENT, SUPPORT_ATTACHMENT: PRESENT,
             ANALYTICS: EXPOSED, SUPPORT_MESSAGE: EXPOSED, TOMBSTONE: EXPOSED, DATA_FLOW: ACTIVE, BACKUP: RESTORABLE}
COMPLIANT = {ACCOUNT: ABSENT, SEARCH: ABSENT, EXPORT: ABSENT, MARKETING: ABSENT, SUPPORT_ATTACHMENT: ABSENT,
             ANALYTICS: CLEAN, SUPPORT_MESSAGE: CLEAN, TOMBSTONE: CLEAN, DATA_FLOW: DISABLED, BACKUP: BLOCKED,
             AUDIT: PRESENT, LEGAL_HOLD: PRESENT}

# type -> (finding op, remediation op, verification op after remediation)
VIOLATION_OPS = {
    ACCOUNT: ("REPORT_REMAINING_RECORD", "DELETE_RECORD", "VERIFY_RECORD_ABSENT"),
    SEARCH: ("REPORT_REMAINING_RECORD", "DELETE_RECORD", "VERIFY_RECORD_ABSENT"),
    EXPORT: ("REPORT_REMAINING_RECORD", "DELETE_RECORD", "VERIFY_RECORD_ABSENT"),
    MARKETING: ("REPORT_REMAINING_RECORD", "DELETE_RECORD", "VERIFY_RECORD_ABSENT"),
    SUPPORT_ATTACHMENT: ("REPORT_REMAINING_RECORD", "DELETE_RECORD", "VERIFY_RECORD_ABSENT"),
    ANALYTICS: ("REPORT_EXPOSED_PII", "ANONYMIZE_RECORD", "VERIFY_RECORD_ANONYMIZED"),
    SUPPORT_MESSAGE: ("REPORT_EXPOSED_PII", "REDACT_RECORD", "VERIFY_RECORD_REDACTED"),
    TOMBSTONE: ("REPORT_EXPOSED_PII", "REDACT_RECORD", "VERIFY_RECORD_REDACTED"),
    DATA_FLOW: ("REPORT_ACTIVE_DATA_FLOW", "DISABLE_DATA_FLOW", "VERIFY_DATA_FLOW_DISABLED"),
    BACKUP: ("REPORT_RESTORE_RISK", "BLOCK_RESTORE", "VERIFY_RESTORE_BLOCKED"),
}
COMPLIANT_OP = {
    ABSENT: "VERIFY_RECORD_ABSENT", CLEAN: None, DISABLED: "VERIFY_DATA_FLOW_DISABLED", BLOCKED: "VERIFY_RESTORE_BLOCKED",
}


def compliant_op(rtype: str) -> str:
    """Verification operation proving the compliant end state of a record type."""
    if rtype in (AUDIT, LEGAL_HOLD):
        return "VERIFY_RECORD_PRESENT"
    return VIOLATION_OPS[rtype][2]


# resource-id prefix -> system id (this is how the golden answers name the system)
PREFIX_SYSTEM = (
    ("account_", "account_service"), ("search_", "search_service"), ("export_", "export_service"),
    ("marketing_", "marketing_platform"), ("support_", "support_platform"), ("analytics_", "analytics_platform"),
    ("tombstone_", "identity_service"), ("data_flow_", "integration_service"), ("backup_", "backup_service"),
    ("audit_record_", "security_service"), ("legal_hold_", "legal_service"), ("object_", "object_storage"),
    ("cache_", "cache_service"), ("email_delivery_", "email_delivery_service"),
)
RID_RE = re.compile(r"\b(?:account|search|export|marketing|support|analytics|tombstone|data_flow|backup|audit_record|"
                    r"legal_hold|object|cache|email_delivery)_\d+\b")


def system_of(resource_id: str) -> str:
    for prefix, system in PREFIX_SYSTEM:
        if resource_id.startswith(prefix):
            return system
    return "unknown_service"


def severity(rtype: str, state: str) -> int:
    """Higher = worse. Used to merge copies of one record seen at the same time."""
    if state == VIOLATING.get(rtype):
        return 2
    if state == LINK:
        return 0
    return 1


@dataclass(frozen=True)
class Obs:
    """One observation of one resource, from one evidence file."""
    file_id: str
    captured_at: str   # manifest capture time of the file
    obs_time: str      # the record's own time (record, snapshot or log-line time); gates and orders observations
    resource_id: str
    rtype: str
    state: str
    tokens: frozenset = field(default_factory=frozenset)   # identity tokens found in the record
    system_id: str = ""
    src: str = ""      # parser tag, for diagnostics

    def sys(self) -> str:
        return self.system_id or system_of(self.resource_id)


@dataclass(frozen=True)
class Snapshot:
    """A snapshot that declares coverage of a system (used to prove absence by omission)."""
    file_id: str
    captured_at: str
    system_id: str
    time: str


@dataclass(frozen=True)
class LinkFact:
    """A LINK_RESOURCE_IDENTITY activity: the data catalog says this resource belongs to this user."""
    activity_id: str
    time: str
    resource_id: str
    system_id: str
    email: str
    user_id: str
    file_id: str = ""   # evidence file captured 7m01s earlier, if any
