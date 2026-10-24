"""Parsers for the structured evidence: handover text, JSON (readbacks, bundles, ledgers, collections), SQL."""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from .. import model as m
from ..tokens import tokens_of, tokens_of_obj
from .common import Sink, collection_state, ledger_obs, _any

SYSTEMS = {"account_service", "search_service", "export_service", "support_platform", "analytics_platform",
           "integration_service", "backup_service", "security_service", "identity_service", "legal_service"}


# ----------------------------------------------------------------------------------------------- text ledger
_LEDGER_LINE = re.compile(r"^-\s+(\d{4}-\d\d-\d\dT[\d:]+Z) \| (\w+) \| (\w+) \| (\w+) \| (\w+) \| (.*)$")


def parse_text(sink: Sink, file_id: str, captured_at: str, path: Path):
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.rstrip()
        if not line.startswith("- "):
            continue
        mt = _LEDGER_LINE.match(line)
        if not mt:
            sink.unrecognised(file_id, "text line")
            continue
        time, system, rid, rtype, result, subject = mt.groups()
        ledger_obs(sink, file_id, captured_at, time, rid, rtype, result, subject, "ledger_txt", system)


# --------------------------------------------------------------------------------------------------- JSON
def _readback(sink: Sink, file_id: str, captured_at: str, doc: dict):
    ex = doc["service_exports"]
    src = "readback_json"
    for it in ex.get("account_service", {}).get("profile_lookups", []):
        absent = it.get("status_code") == 404 or it.get("profile") is None
        toks = tokens_of_obj(it.get("profile") or {})
        sink.add(file_id, captured_at, it["observed_at"], it["resource_id"], m.ACCOUNT,
                 m.ABSENT if absent else m.PRESENT, toks, src)
    for it in ex.get("analytics_platform", {}).get("profiles", []):
        exposed = _any(it, "customer_reference", "email", "phone", "email_hash", "user_id")
        sink.add(file_id, captured_at, it["observed_at"], it["resource_id"], m.ANALYTICS,
                 m.EXPOSED if exposed else m.CLEAN, tokens_of_obj(it), src)
    for it in ex.get("search_service", {}).get("index_queries", []):
        total = (it.get("hits") or {}).get("total", 0)
        sink.add(file_id, captured_at, it["observed_at"], it["resource_id"], m.SEARCH,
                 m.PRESENT if total else m.ABSENT, tokens_of_obj(it), src)
    for it in ex.get("support_platform", {}).get("tickets", []):
        exposed = _any(it, "requester_email", "requester_name", "requester_phone")
        sink.add(file_id, captured_at, it["observed_at"], it["resource_id"], m.SUPPORT_MESSAGE,
                 m.EXPOSED if exposed else m.CLEAN, tokens_of_obj(it), src)
    for it in ex.get("integration_service", {}).get("connectors", []):
        sink.add(file_id, captured_at, it["observed_at"], it["resource_id"], m.DATA_FLOW,
                 m.ACTIVE if it.get("enabled") else m.DISABLED, tokens_of_obj(it), src)
    for it in ex.get("backup_service", {}).get("restore_entries", []):
        sink.add(file_id, captured_at, it["observed_at"], it["resource_id"], m.BACKUP,
                 m.RESTORABLE if it.get("restore_allowed") else m.BLOCKED, tokens_of_obj(it), src)
    for it in ex.get("export_service", {}).get("exports", []):
        sink.add(file_id, captured_at, it["observed_at"], it["resource_id"], m.EXPORT, m.PRESENT, tokens_of_obj(it), src)
    for it in ex.get("security_service", {}).get("audit_records", []):
        sink.add(file_id, captured_at, it["observed_at"], it["resource_id"], m.AUDIT, m.PRESENT, tokens_of_obj(it), src)
    known = {"account_service", "analytics_platform", "search_service", "support_platform", "integration_service",
             "backup_service", "export_service", "security_service"}
    for svc in set(ex) - known:
        sink.unrecognised(file_id, f"readback service {svc}")


def _collection_record(sink: Sink, file_id: str, captured_at: str, time: str, collection: str, rec: dict, src: str):
    cs = collection_state(collection, rec)
    if cs is None:
        sink.unrecognised(file_id, f"collection {collection}")
        return
    rtype, state = cs
    toks = tokens_of_obj(rec)
    sink.add(file_id, captured_at, time, rec["resource_id"], rtype, state, toks, src)
    src_rid = rec.get("source_resource_id")
    if src_rid:   # a derived record names its source account: identity-only link
        sink.add(file_id, captured_at, time, src_rid, m.ACCOUNT, m.LINK, toks, src + ":source")


def _bundle(sink: Sink, file_id: str, captured_at: str, doc: dict):
    for snap in doc["snapshots"]:
        store, coll, snap_time = snap["data_store"], snap["collection"], snap["captured_at"]
        if store in SYSTEMS:
            sink.snapshot(file_id, captured_at, store, snap_time)
        for rec in snap["records"]:
            if "record_type" in rec and "recorded_at" in rec:       # ledger-flavoured record inside a bundle
                ledger_obs(sink, file_id, captured_at, rec["recorded_at"], rec["resource_id"], rec["record_type"],
                           rec["result"], rec.get("lookup_value") or rec.get("subject_reference"), "bundle_ledger",
                           rec.get("system", ""))
            else:
                _collection_record(sink, file_id, captured_at, snap_time, coll, rec, "bundle")


def parse_json(sink: Sink, file_id: str, captured_at: str, path: Path):
    doc = json.loads(path.read_text(encoding="utf-8"))
    if "service_exports" in doc:
        _readback(sink, file_id, captured_at, doc)
    elif "snapshots" in doc:
        _bundle(sink, file_id, captured_at, doc)
    elif "records" in doc and doc["records"] and "record_type" in doc["records"][0]:
        for rec in doc["records"]:
            ledger_obs(sink, file_id, captured_at, rec["recorded_at"], rec["resource_id"], rec["record_type"],
                       rec["result"], rec.get("subject_reference") or rec.get("lookup_value"), "ledger_json",
                       rec.get("system", ""))
    elif "collection" in doc and "records" in doc:
        time = doc.get("captured_at") or captured_at
        for rec in doc["records"]:
            _collection_record(sink, file_id, captured_at, time, doc["collection"], rec, "collection_json")
    else:
        sink.unrecognised(file_id, "json shape")


# --------------------------------------------------------------------------------------------------- SQL
_CAPTURED = re.compile(r"^-- Captured at:\s*(\S+)", re.M)

_INVENTORY_TABLES = {   # table -> (system, rtype, exposure/state function)
    "customer_profiles": ("account_service", m.ACCOUNT, lambda r: m.PRESENT),
    "customer_search_documents": ("search_service", m.SEARCH, lambda r: m.PRESENT),
    "customer_analytics_profiles": ("analytics_platform", m.ANALYTICS,
                                    lambda r: m.EXPOSED if _any(r, "customer_reference", "email", "phone", "email_hash") else m.CLEAN),
    "support_records": ("support_platform", m.SUPPORT_MESSAGE,
                        lambda r: m.EXPOSED if _any(r, "requester_name", "requester_email", "requester_phone") else m.CLEAN),
    "customer_exports": ("export_service", m.EXPORT, lambda r: m.PRESENT),
    "connector_subscriptions": ("integration_service", m.DATA_FLOW, lambda r: m.ACTIVE if r.get("enabled") else m.DISABLED),
    "backup_restore_entries": ("backup_service", m.BACKUP, lambda r: m.RESTORABLE if r.get("restore_allowed") else m.BLOCKED),
    "security_audit_records": ("security_service", m.AUDIT, lambda r: m.PRESENT),
}


def _rows(con, table):
    cur = con.execute(f'SELECT * FROM "{table}"')
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def parse_sql(sink: Sink, file_id: str, captured_at: str, path: Path):
    text = path.read_text(encoding="utf-8")
    con = sqlite3.connect(":memory:")
    try:
        _parse_sql(sink, file_id, captured_at, text, con)
    finally:
        con.close()


def _parse_sql(sink: Sink, file_id: str, captured_at: str, text: str, con):
    try:
        con.executescript(text)
    except sqlite3.Error as exc:                                    # pragma: no cover - defensive
        sink.unrecognised(file_id, f"sql error {exc}")
        return
    tables = [t for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    mt = _CAPTURED.search(text)
    header_time = mt.group(1) if mt else captured_at
    if "snapshot_scope" in tables:                                   # typed inventory
        scope = {s: t for s, t in con.execute("SELECT origin_system, captured_at FROM snapshot_scope")}
        for system, t in scope.items():
            sink.snapshot(file_id, captured_at, system, t)
        for table in tables:
            if table == "snapshot_scope":
                continue
            spec = _INVENTORY_TABLES.get(table)
            if spec is None:
                sink.unrecognised(file_id, f"inventory table {table}")
                continue
            system, rtype, fn = spec
            for r in _rows(con, table):
                sink.add(file_id, captured_at, scope.get(system, captured_at), r["resource_id"], rtype, fn(r),
                         tokens_of_obj(r), "inventory_sql", system)
        return
    for table in tables:
        rows = _rows(con, table)
        cols = set(rows[0]) if rows else {c[1] for c in con.execute(f'PRAGMA table_info("{table}")')}
        if "record_json" in cols:                                     # generic primary + replicas
            for r in rows:
                rec = json.loads(r["record_json"])
                sink.snapshot(file_id, captured_at, r["origin_system"], header_time)
                _collection_record(sink, file_id, captured_at, header_time, r["collection_name"], rec, "generic_sql:" + table)
        elif table.startswith("customer_profiles_"):                  # typed accounts: primary / failover replica
            sink.snapshot(file_id, captured_at, "account_service", header_time)
            for r in rows:
                sink.add(file_id, captured_at, header_time, r["resource_id"], m.ACCOUNT, m.PRESENT, tokens_of_obj(r),
                         "accounts_sql:" + table, "account_service")
        elif table.startswith("search_documents_"):                    # typed search primary with a source link
            sink.snapshot(file_id, captured_at, "search_service", header_time)
            for r in rows:
                toks = tokens_of_obj(r)
                sink.add(file_id, captured_at, header_time, r["resource_id"], m.SEARCH, m.PRESENT, toks,
                         "search_sql:" + table, "search_service")
                if r.get("source_resource_id"):
                    sink.add(file_id, captured_at, header_time, r["source_resource_id"], m.ACCOUNT, m.LINK, toks,
                             "search_sql:source")
        else:
            sink.unrecognised(file_id, f"sql table {table}")
