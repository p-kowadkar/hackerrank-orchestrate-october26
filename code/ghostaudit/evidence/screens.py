"""Application screenshots: the structured facts a reader returns, their validation, and the observations they give.

A reader (a person or a vision model; see code/llm/) transcribes what a screenshot shows into a small, closed structure.
Everything after that is deterministic code: this module validates the structure and maps the facts of the highlighted
(subject) row to a record type and state. The model is asked for facts ("is the sync switched on?"), never for a verdict.

Why only the highlighted row becomes an observation: every screenshot has exactly one subject row plus rows that belong to
other people; who the subject is comes from the LINK_RESOURCE_IDENTITY activity, not from the picture.
"""
from __future__ import annotations

import re

from .. import model as m
from ..timeutil import parse
from ..tokens import tokens_of
from .common import Sink

RECORD_TYPES = ("ACCOUNT", "SEARCH", "DATA_FLOW", "ANALYTICS", "EXPORT", "SUPPORT_TICKET", "SUPPORT_ATTACHMENT", "BACKUP",
                "AUDIT", "TOMBSTONE", "MARKETING", "OTHER")
INTERNAL_TYPE = {"ACCOUNT": m.ACCOUNT, "SEARCH": m.SEARCH, "DATA_FLOW": m.DATA_FLOW, "ANALYTICS": m.ANALYTICS,
                 "EXPORT": m.EXPORT, "SUPPORT_TICKET": m.SUPPORT_MESSAGE, "SUPPORT_ATTACHMENT": m.SUPPORT_ATTACHMENT,
                 "BACKUP": m.BACKUP, "AUDIT": m.AUDIT, "TOMBSTONE": m.TOMBSTONE, "MARKETING": m.MARKETING}
# resource-id prefixes a record type may carry
PREFIXES = {"ACCOUNT": ("account_",), "SEARCH": ("search_",), "DATA_FLOW": ("data_flow_",), "ANALYTICS": ("analytics_",),
            "EXPORT": ("export_",), "SUPPORT_TICKET": ("support_",), "SUPPORT_ATTACHMENT": ("support_", "object_"),
            "BACKUP": ("backup_",), "AUDIT": ("audit_record_",), "TOMBSTONE": ("tombstone_",), "MARKETING": ("marketing_",)}
FACT_KEYS = {"enabled": (bool, type(None)), "restore_blocked": (bool, type(None)), "identifiable": (bool, type(None)),
             "status": (str, type(None)), "expires_at": (str, type(None))}
REQUIRED_FACT = {"DATA_FLOW": "enabled", "BACKUP": "restore_blocked", "ANALYTICS": "identifiable",
                 "SUPPORT_TICKET": "identifiable", "TOMBSTONE": "identifiable"}
ROW_KEYS = {"record_type", "resource_id", "label", "selected", "identifiers", "facts"}
_ISO = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
MAX_ROWS = 40


class ScreenError(ValueError):
    """The structure is not valid; `.problems` lists every reason."""

    def __init__(self, problems: list):
        super().__init__("; ".join(problems))
        self.problems = problems


def validate_screen(data) -> dict:
    """Return `data` if it is a valid screenshot transcription, else raise ScreenError listing every problem."""
    problems = []
    if not isinstance(data, dict):
        raise ScreenError(["top level is not an object"])
    extra = set(data) - {"screen", "rows", "notes"}
    if extra:
        problems.append(f"unknown top-level keys {sorted(extra)}")
    if not isinstance(data.get("screen"), str) or not data["screen"].strip():
        problems.append("screen must be a non-empty string")
    rows = data.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ScreenError(problems + ["rows must be a non-empty list"])
    if len(rows) > MAX_ROWS:
        problems.append(f"more than {MAX_ROWS} rows")
    selected = 0
    for i, row in enumerate(rows):
        where = f"rows[{i}]"
        if not isinstance(row, dict):
            problems.append(f"{where} is not an object")
            continue
        if set(row) != ROW_KEYS:
            problems.append(f"{where} keys must be exactly {sorted(ROW_KEYS)}, got {sorted(row)}")
            continue
        rtype, rid = row["record_type"], row["resource_id"]
        if rtype not in RECORD_TYPES:
            problems.append(f"{where}.record_type {rtype!r} is not one of {RECORD_TYPES}")
        if rid is not None and (not isinstance(rid, str) or not m.RID_RE.fullmatch(rid)):
            problems.append(f"{where}.resource_id {rid!r} is not a resource id")
        elif isinstance(rid, str) and rtype in PREFIXES and not rid.startswith(PREFIXES[rtype]):
            problems.append(f"{where}.resource_id {rid!r} does not fit record_type {rtype}")
        if row["label"] is not None and not isinstance(row["label"], str):
            problems.append(f"{where}.label must be a string or null")
        if not isinstance(row["selected"], bool):
            problems.append(f"{where}.selected must be a boolean")
        else:
            selected += row["selected"]
        if not isinstance(row["identifiers"], list) or not all(isinstance(x, str) for x in row["identifiers"]):
            problems.append(f"{where}.identifiers must be a list of strings")
        facts = row["facts"]
        if not isinstance(facts, dict) or set(facts) != set(FACT_KEYS):
            problems.append(f"{where}.facts keys must be exactly {sorted(FACT_KEYS)}")
            continue
        for k, types in FACT_KEYS.items():
            if not isinstance(facts[k], types):
                problems.append(f"{where}.facts.{k} has the wrong type")
        exp = facts["expires_at"]
        if isinstance(exp, str) and not _ISO.match(exp):
            problems.append(f"{where}.facts.expires_at {exp!r} is not an ISO-8601 UTC time")
        if row["selected"] is True:
            if rtype == "OTHER":
                problems.append(f"{where} is selected but record_type is OTHER")
            need = REQUIRED_FACT.get(rtype)
            if need and not isinstance(facts.get(need), bool):
                problems.append(f"{where} is a selected {rtype} row, so facts.{need} must be true or false")
    if selected != 1:
        problems.append(f"exactly one row must be selected, found {selected}")
    if problems:
        raise ScreenError(problems)
    return data


def row_state(row: dict, captured_at: str) -> str:
    """The model-independent mapping from the facts of a record to the state the audit logic uses."""
    rtype, f = row["record_type"], row["facts"]
    if rtype == "DATA_FLOW":
        return m.ACTIVE if f["enabled"] else m.DISABLED
    if rtype == "BACKUP":
        return m.BLOCKED if f["restore_blocked"] else m.RESTORABLE
    if rtype in ("ANALYTICS", "SUPPORT_TICKET", "TOMBSTONE"):
        return m.EXPOSED if f["identifiable"] else m.CLEAN
    if rtype == "EXPORT":
        exp = f["expires_at"]
        return m.ABSENT if exp and parse(exp) <= parse(captured_at) else m.PRESENT     # an expired export is not downloadable
    if rtype == "ACCOUNT" and (f["status"] or "").strip().lower() in ("deleted", "not found", "closed"):
        return m.ABSENT
    return m.PRESENT


def _compatible(rtype: str, rid: str) -> bool:
    return rid.startswith(PREFIXES.get(rtype, ()))


def screen_to_observations(sink: Sink, file_id: str, captured_at: str, data: dict, links: list) -> list:
    """Add the subject row's observation to the sink. Returns a list of problems that did not stop the parse."""
    problems = []
    row = next(r for r in data["rows"] if r["selected"])
    rtype = row["record_type"]
    rid = row["resource_id"]
    link = None
    if rid is not None:
        link = next((lk for lk in links if lk.resource_id == rid), None)
    else:
        fits = [lk for lk in links if _compatible(rtype, lk.resource_id)]
        if len(fits) == 1:
            rid, link = fits[0].resource_id, fits[0]
        else:
            problems.append(f"selected {rtype} row has no printed id and {len(fits)} compatible LINK events")
    if rid is None:
        sink.unrecognised(file_id, "screenshot subject row has no resource id")
        return problems
    if links and link is None:
        problems.append(f"the LINK event names {sorted(lk.resource_id for lk in links)} but the highlighted row is {rid}")
    toks = set(tokens_of("\n".join(row["identifiers"])))
    if link is not None:
        toks |= {link.email.lower(), link.user_id.lower()}
    sink.add(file_id, captured_at, captured_at, rid, INTERNAL_TYPE[rtype], row_state(row, captured_at), frozenset(toks),
             "image")
    return problems
