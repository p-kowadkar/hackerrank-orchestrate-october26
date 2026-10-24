"""Shared plumbing for the evidence parsers: the observation sink and the ledger vocabulary."""
from __future__ import annotations

from collections import Counter, defaultdict

from .. import model as m
from ..tokens import tokens_of


class Sink:
    """Collects observations, coverage snapshots and parse statistics."""

    def __init__(self):
        self.obs: list = []
        self.snapshots: list = []
        self.stats = defaultdict(Counter)       # file_id -> Counter(parsed / ignored / unknown / skipped)
        self.unknown = defaultdict(Counter)     # file_id -> Counter(description of what could not be parsed)

    def add(self, file_id, captured_at, obs_time, rid, rtype, state, tokens=frozenset(), src="", system_id=""):
        self.obs.append(m.Obs(file_id=file_id, captured_at=captured_at, obs_time=obs_time or captured_at,
                              resource_id=rid, rtype=rtype, state=state, tokens=frozenset(tokens),
                              system_id=system_id, src=src))
        self.stats[file_id]["parsed"] += 1

    def snapshot(self, file_id, captured_at, system_id, time):
        self.snapshots.append(m.Snapshot(file_id, captured_at, system_id, time))
        self.stats[file_id]["snapshots"] += 1

    def ignored(self, file_id, n=1):
        self.stats[file_id]["ignored"] += n

    def skipped(self, file_id, why):
        self.stats[file_id]["skipped"] += 1
        self.unknown[file_id]["skipped: " + why] += 1

    def unrecognised(self, file_id, what):
        self.stats[file_id]["unknown"] += 1
        self.unknown[file_id][what] += 1

    def finalize(self) -> list:
        """Merge copies of the same record seen at the same moment (primary + replicas): the worse state wins."""
        merged = {}
        for o in self.obs:
            key = (o.file_id, o.resource_id, o.obs_time, o.rtype)
            prev = merged.get(key)
            if prev is None:
                merged[key] = o
                continue
            worse = o if m.severity(o.rtype, o.state) > m.severity(prev.rtype, prev.state) else prev
            merged[key] = m.Obs(worse.file_id, worse.captured_at, worse.obs_time, worse.resource_id, worse.rtype,
                                worse.state, prev.tokens | o.tokens, worse.system_id or prev.system_id, worse.src)
        return list(merged.values())


# (record_type, result) vocabulary of the ledger-style evidence (handover text, record_lookup logs, JSON ledgers)
LEDGER = {
    ("USER_PROFILE", "FOUND"): (m.ACCOUNT, m.PRESENT), ("USER_PROFILE", "NOT_FOUND"): (m.ACCOUNT, m.ABSENT),
    ("SEARCH_INDEX_ENTRY", "FOUND"): (m.SEARCH, m.PRESENT), ("SEARCH_INDEX_ENTRY", "NOT_FOUND"): (m.SEARCH, m.ABSENT),
    ("USER_EXPORT", "FOUND"): (m.EXPORT, m.PRESENT), ("USER_EXPORT", "NOT_FOUND"): (m.EXPORT, m.ABSENT),
    ("MARKETING_PROFILE", "FOUND"): (m.MARKETING, m.PRESENT), ("MARKETING_PROFILE", "NOT_FOUND"): (m.MARKETING, m.ABSENT),
    ("SECURITY_AUDIT_LOG", "FOUND"): (m.AUDIT, m.PRESENT),
    ("LEGAL_HOLD_RECORD", "FOUND"): (m.LEGAL_HOLD, m.PRESENT),
    ("ANALYTICS_PROFILE", "IDENTIFIABLE"): (m.ANALYTICS, m.EXPOSED), ("ANALYTICS_PROFILE", "ANONYMIZED"): (m.ANALYTICS, m.CLEAN),
    ("SUPPORT_MESSAGE", "IDENTIFIABLE"): (m.SUPPORT_MESSAGE, m.EXPOSED), ("SUPPORT_MESSAGE", "REDACTED"): (m.SUPPORT_MESSAGE, m.CLEAN),
    ("SUPPORT_ATTACHMENT", "FOUND"): (m.SUPPORT_ATTACHMENT, m.PRESENT), ("SUPPORT_ATTACHMENT", "NOT_FOUND"): (m.SUPPORT_ATTACHMENT, m.ABSENT),
    ("DATA_FLOW", "ACTIVE"): (m.DATA_FLOW, m.ACTIVE), ("DATA_FLOW", "DISABLED"): (m.DATA_FLOW, m.DISABLED),
    ("BACKUP_ARCHIVE", "ACTIVE"): (m.BACKUP, m.RESTORABLE), ("BACKUP_ARCHIVE", "BLOCKED"): (m.BACKUP, m.BLOCKED),
    ("ACCOUNT_TOMBSTONE", "IDENTIFIABLE"): (m.TOMBSTONE, m.EXPOSED), ("ACCOUNT_TOMBSTONE", "REDACTED"): (m.TOMBSTONE, m.CLEAN),
}


def ledger_obs(sink: Sink, file_id, captured_at, time, rid, record_type, result, subject, src, system_id=""):
    key = (record_type.strip().upper(), result.strip().upper())
    if key not in LEDGER:
        sink.unrecognised(file_id, f"ledger {key}")
        return
    rtype, state = LEDGER[key]
    sink.add(file_id, captured_at, time, rid, rtype, state, tokens_of(subject or ""), src, system_id)


# --- collections shared by SQL replicas, bundles and standalone collection exports -------------------------

def _any(rec: dict, *keys) -> bool:
    return any(rec.get(k) not in (None, "", "null") for k in keys)


def collection_state(collection: str, rec: dict):
    """(rtype, state) of one record of a named collection, or None if the collection is unknown."""
    if collection == "customer_profiles":
        return m.ACCOUNT, m.PRESENT
    if collection == "customer_search_documents":
        return m.SEARCH, m.PRESENT
    if collection == "customer_analytics_reports":
        return m.ANALYTICS, (m.EXPOSED if _any(rec, "user_id", "email", "phone", "email_hash", "customer_reference") else m.CLEAN)
    if collection == "support_conversations":
        return m.SUPPORT_MESSAGE, (m.EXPOSED if tokens_of(str(rec.get("message_text", ""))) else m.CLEAN)
    if collection == "ticket_attachments":
        return m.SUPPORT_ATTACHMENT, m.PRESENT
    if collection == "customer_export_jobs":
        return m.EXPORT, (m.PRESENT if rec.get("download_available") else m.ABSENT)
    if collection == "connector_configurations":
        return m.DATA_FLOW, (m.ACTIVE if rec.get("enabled") else m.DISABLED)
    if collection == "backup_catalog":
        return m.BACKUP, (m.RESTORABLE if rec.get("restore_allowed") else m.BLOCKED)
    if collection == "security_audit_events":
        return m.AUDIT, m.PRESENT
    if collection == "retained_order_records":
        return m.LEGAL_HOLD, m.PRESENT
    if collection == "deleted_customer_references":
        return m.TOMBSTONE, (m.EXPOSED if _any(rec, "name", "email", "phone", "email_hash") else m.CLEAN)
    return None
