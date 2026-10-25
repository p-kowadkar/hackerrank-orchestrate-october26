"""Log evidence: seven dialects, one event vocabulary.

Lines are normalised to (timestamp, event, trace id, key/values), grouped by trace id, and the terminal event of a
trace becomes an observation. Identity tokens come from every line of the trace (the identifier is on the
"started" line, the resource on the "completed" line).
"""
from __future__ import annotations

import json
import re
from collections import OrderedDict
from pathlib import Path

from .. import model as m
from ..tokens import tokens_of
from .common import Sink, ledger_obs

KV_RE = re.compile(r'(\w+)=("(?:[^"\\]|\\.)*"|[^\s"]+)')
TS_RE = re.compile(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ) (.*)$")
PIPE_RE = re.compile(r"^\| (\w+) \| (\w+) \| ([\w\-]+) \| (\w+) \| (.*)$")
BRACKET_RE = re.compile(r"^\[(\w+)\] \[(\w+)\] \[([\w\-]+)\] (\w+): (.*)$")
SYSLOG_RE = re.compile(r"^<\d+>1 (\S+) (\w+) (\S+) - - (.*)$")

# events that only carry identity or are infrastructure noise
STARTED = {
    "profile_lookup_started", "index_query_started", "connector_config_read_started", "restore_policy_read_started",
    "restore_policy_check_started", "audit_record_read_started", "audit_record_query_started",
    "support_ticket_read_started", "message_scan_started", "attachment_scan_started", "analytics_profile_read_started",
    "analytics_profile_scan_started", "export_download_check_started", "export_metadata_read_started",
    "retained_order_query_started", "contact_query_started",
}
NOISE = {
    "connection_acquired", "dependency_retry", "dependency_recovered", "cache_lookup", "export_started",
    "export_completed", "pool_sample", "properties_reloaded", "connection_pool_pressure", "lease_extended",
    "lease_renewed", "checkpoint_saved", "timer_tick", "certificate_checked", "disk_latency", "cache_refresh",
    "flag_snapshot_loaded", "slow_call_rate", "consumer_lag", "delivery_abandoned", "thumbnail_failed",
    "batch_started", "telemetry_flushed",
}


def unquote(v: str) -> str:
    if v.startswith('"') and v.endswith('"'):
        v = v[1:-1].replace('\\"', '"')
    return v


def kvparse(s: str) -> dict:
    return {k: unquote(v) for k, v in KV_RE.findall(s)}


def parse_line(line: str):
    """-> dict(ts, event, trace, kv, dialect, raw) or None for lines that are not log records.
    dialect is one of json, pipe, bracket, syslog, cloud (requestId + nested message), kv."""
    mt = TS_RE.match(line)
    if not mt:
        return None
    ts, rest = mt.groups()
    trace, event, kv, dialect = None, None, {}, "kv"
    if rest.startswith("{"):
        dialect = "json"
        try:
            kv = {k: ("null" if v is None else str(v)) for k, v in json.loads(rest).items()}
        except ValueError:
            return None
        event, trace = kv.get("event"), kv.get("trace_id")
    elif PIPE_RE.match(rest):
        dialect = "pipe"
        _lvl, _svc, trace, event, tail = PIPE_RE.match(rest).groups()
        kv = kvparse(tail)
    elif BRACKET_RE.match(rest):
        dialect = "bracket"
        _lvl, _svc, trace, event, tail = BRACKET_RE.match(rest).groups()
        kv = kvparse(tail)
    elif SYSLOG_RE.match(rest):
        dialect = "syslog"
        _host, _svc, trace, tail = SYSLOG_RE.match(rest).groups()
        kv = kvparse(tail)
        event = kv.get("event")
    else:
        kv = kvparse(rest)
        if "message" in kv:                                  # requestId/message dialect with escaped nested pairs
            dialect = "cloud"
            kv.update(kvparse(kv["message"]))
        event = kv.get("event")
        trace = kv.get("trace_id") or kv.get("requestId")
    if not event:
        return None
    return {"ts": ts, "event": event, "trace": trace or kv.get("trace_id"), "kv": kv, "dialect": dialect, "raw": line}


def _t(v) -> bool:
    return str(v).strip().lower() == "true"


def _null(v) -> bool:
    return v is None or str(v).strip().lower() in ("", "null", "none")


def _terminal(sink: Sink, f: str, cap: str, rec: dict, toks: frozenset):
    ev, kv, ts = rec["event"], rec["kv"], rec["ts"]
    rid = kv.get("resource_id")
    add = lambda rtype, state, src="log": sink.add(f, cap, ts, rid, rtype, state, toks, src)  # noqa: E731
    if ev == "record_lookup":
        ledger_obs(sink, f, cap, ts, rid, kv["record_type"], kv["result"], kv.get("subject_reference"), "ledger_log",
                   kv.get("system", ""))
    elif ev == "profile_lookup_completed":
        add(m.ACCOUNT, m.ABSENT if (kv.get("rows") == "0" or kv.get("http_status") == "404") else m.PRESENT)
    elif ev == "index_query_completed":
        add(m.SEARCH, m.PRESENT if kv.get("result") == "hit" else m.ABSENT)
    elif ev in ("connector_config_read_completed", "connector_heartbeat", "connector_config_loaded"):
        live = _t(kv.get("enabled")) or _t(kv.get("scheduler_registered"))
        add(m.DATA_FLOW, m.ACTIVE if live else m.DISABLED)
    elif ev == "restore_policy_read_completed":
        add(m.BACKUP, m.RESTORABLE if _t(kv.get("restore_allowed")) else m.BLOCKED)
    elif ev == "restore_candidate_evaluated":
        add(m.BACKUP, m.RESTORABLE if (_t(kv.get("eligible")) and not _t(kv.get("deletion_block"))) else m.BLOCKED)
    elif ev == "restore_authorization_completed":
        add(m.BACKUP, m.BLOCKED if kv.get("decision") == "deny" else m.RESTORABLE)
    elif ev == "support_ticket_read_completed":
        exposed = any(not _null(kv.get(k)) for k in ("requester_email", "requester_name", "requester_phone"))
        add(m.SUPPORT_MESSAGE, m.EXPOSED if exposed else m.CLEAN)
    elif ev == "message_pii_scan":
        add(m.SUPPORT_MESSAGE, m.EXPOSED)
    elif ev == "message_read":
        add(m.SUPPORT_MESSAGE, m.EXPOSED if tokens_of(kv.get("message_text", "")) else m.CLEAN)
    elif ev == "attachment_pii_scan":
        add(m.SUPPORT_ATTACHMENT, m.PRESENT)
    elif ev == "analytics_profile_read_completed":
        exposed = any(not _null(kv.get(k)) for k in ("customer_reference", "email", "phone", "email_hash"))
        add(m.ANALYTICS, m.EXPOSED if exposed else m.CLEAN)
    elif ev == "analytics_profile_read":
        exposed = kv.get("direct_identifiers", "0") != "0" or not _null(kv.get("email")) or not _null(kv.get("phone"))
        add(m.ANALYTICS, m.EXPOSED if exposed else m.CLEAN)
    elif ev == "analytics_identity_scan":
        add(m.ANALYTICS, m.EXPOSED)
    elif ev == "contact_lookup_completed":                 # a marketing contact kept under an analytics id
        add(m.MARKETING, m.PRESENT if kv.get("rows", "1") != "0" else m.ABSENT)
    elif ev in ("export_download_check_completed", "export_metadata_read_completed"):
        add(m.EXPORT, m.PRESENT if _t(kv.get("available")) else m.ABSENT)
    elif ev == "audit_record_read_completed":
        add(m.AUDIT, m.PRESENT)
    elif ev == "retained_order_loaded":
        add(m.LEGAL_HOLD, m.PRESENT)
    elif ev == "contact_query_completed":
        add(m.SUPPORT_ATTACHMENT, m.PRESENT if kv.get("rows", "1") != "0" else m.ABSENT)
    elif ev == "deletion_marker_check":
        if _t(kv.get("marker_found")):
            add(m.SUPPORT_ATTACHMENT, m.ABSENT)
        else:
            sink.ignored(f)
    else:
        return False
    return True


def parse_log(sink: Sink, file_id: str, captured_at: str, path: Path):
    groups: "OrderedDict[str, list]" = OrderedDict()
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        rec = parse_line(line)
        if rec is None:
            sink.unrecognised(file_id, "log line")
            continue
        groups.setdefault(rec["trace"] or f"line{i}", []).append(rec)
    for recs in groups.values():
        toks = tokens_of("\n".join(r["raw"] for r in recs))
        for rec in recs:
            ev = rec["event"]
            if ev in NOISE or ev in STARTED:
                sink.ignored(file_id)
                continue
            if not _terminal(sink, file_id, captured_at, rec, toks):
                sink.unrecognised(file_id, f"event {ev}")
