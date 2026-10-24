"""Which resources belong to a case, and what was true of each at audit_at.

Clock rules (see code/notes/evidence_state_catalog.md):
  * a file counts only if its manifest capture time is <= audit_at;
  * a record inside a usable file counts only if its own time is <= audit_at;
  * the newest admissible observation of a resource wins, in both directions;
  * evidence captured shortly *after* audit_at may still say which resources belong to the user (identity),
    but never what state they were in.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import model as m
from .evidence import EvidenceIndex
from .timeutil import shift

IGNORED_TYPES = ("cache_", "email_delivery_")      # appear in the activity stream only, never in evidence

# identity window around audit_at, in days: late bundles are exported up to ~7 days after the batch they describe
WINDOW_BEFORE_DAYS = 14
WINDOW_AFTER_DAYS = 8


@dataclass
class Decision:
    resource_id: str
    rtype: str
    system_id: str
    state: str                     # one of the model states
    obs: object = None             # the chosen observation (None = no admissible evidence)
    defaulted: bool = False        # state assumed, not observed
    notes: list = field(default_factory=list)

    @property
    def violating(self) -> bool:
        return self.state == m.VIOLATING.get(self.rtype)


def file_number(file_id: str) -> int:
    return int(file_id.split("_")[1])


def admissible(o: m.Obs, audit_at: str) -> bool:
    return o.state != m.LINK and o.captured_at <= audit_at and o.obs_time <= audit_at


def latest_observation(index: EvidenceIndex, resource_id: str, audit_at: str):
    cands = [o for o in index.by_rid.get(resource_id, ()) if admissible(o, audit_at)]
    if not cands:
        return None
    return max(cands, key=lambda o: (o.obs_time, o.captured_at, file_number(o.file_id)))


def directly_linked(index: EvidenceIndex, tokens: frozenset, user_id: str, audit_at: str) -> dict:
    """resource_id -> set of linking file ids, for resources whose records carry one of the user's tokens
    in a file captured inside the case window, plus the data catalog's LINK facts."""
    lo = shift(audit_at, days=-WINDOW_BEFORE_DAYS)
    hi = shift(audit_at, days=WINDOW_AFTER_DAYS)
    found: dict = {}
    for tok in tokens:
        for o in index.by_token.get(tok, ()):
            if lo <= o.captured_at <= hi and not o.resource_id.startswith(IGNORED_TYPES):
                found.setdefault(o.resource_id, set()).add(o.file_id)
    for lk in index.links:
        if lk.user_id == user_id and lk.time <= audit_at:
            found.setdefault(lk.resource_id, set()).add(lk.file_id or "LINK")
    return found


def absence_proof(index: EvidenceIndex, system_id: str, audit_at: str):
    """Latest admissible snapshot that declares coverage of the system (used when a record is simply not listed)."""
    snaps = [s for s in index.snapshots if s.system_id == system_id and s.captured_at <= audit_at and s.time <= audit_at]
    if not snaps:
        return None
    return max(snaps, key=lambda s: (s.time, s.captured_at, file_number(s.file_id))).file_id


def decide(index: EvidenceIndex, resource_id: str, audit_at: str, rtype_hint=None):
    """The Decision for one resource, or None if nothing can be said about it."""
    obs = latest_observation(index, resource_id, audit_at)
    prefix_type = _prefix_type(resource_id)
    if obs is not None:
        return Decision(resource_id, obs.rtype, obs.sys(), obs.state, obs)
    rtype = rtype_hint or prefix_type
    if rtype == m.ACCOUNT:     # no admissible sign of the account: it is verified as absent
        return Decision(resource_id, m.ACCOUNT, "account_service", m.ABSENT, None, True,
                        ["no admissible observation; assumed absent"])
    if rtype in (m.AUDIT, m.LEGAL_HOLD):   # retained records: known from identity evidence even if seen late
        return Decision(resource_id, rtype, m.system_of(resource_id), m.PRESENT, None, True,
                        ["identified from evidence outside the clock window"])
    return None


def _prefix_type(resource_id: str):
    for prefix, rtype in (("account_", m.ACCOUNT), ("audit_record_", m.AUDIT), ("legal_hold_", m.LEGAL_HOLD)):
        if resource_id.startswith(prefix):
            return rtype
    return None
