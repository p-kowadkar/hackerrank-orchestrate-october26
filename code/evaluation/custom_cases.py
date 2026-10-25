"""Additional evaluation cases built by hand (not from the dataset's golden answers).

Each case is a tiny, self-contained world: a few users, evidence files in a format that no sample answer exercises,
and an expected answer derived from the task contract (problem statement sections on operations, ordering and clock rules)
*before* running the pipeline. They are rendered to a temporary dataset directory so the real pipeline runs on them
exactly as it runs on dataset/.

Covers all three eval-only replica layouts (reporting, regional, failover), all five eval-only log dialects (json,
syslog, bracket, pipe, cloud) plus the key=value dialect as a control, the clock rules (record dated after the audit,
a later-captured file), historical-email identity, a claim that contradicts the evidence, and non-deletion requests.

Run: python3 code/evaluation/custom_cases.py   (writes code/evaluation/custom_cases_results.md)
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ghostaudit.data import Dataset              # noqa: E402
from ghostaudit.pipeline import run              # noqa: E402
from ghostaudit.planner import PlanOptions       # noqa: E402
from score import render_scorecard, score        # noqa: E402

OUT = Path(__file__).resolve().parent / "custom_cases_results.md"

# the task contract's operation table, typed independently of the pipeline: operation -> (phase, state)
CONTRACT = {
    "REPORT_REMAINING_RECORD": ("FINDING", "PRESENT"), "REPORT_EXPOSED_PII": ("FINDING", "PRESENT"),
    "REPORT_ACTIVE_DATA_FLOW": ("FINDING", "ACTIVE"), "REPORT_RESTORE_RISK": ("FINDING", "ACTIVE"),
    "DISABLE_DATA_FLOW": ("REMEDIATION", "DISABLED"), "BLOCK_RESTORE": ("REMEDIATION", "BLOCKED"),
    "DELETE_RECORD": ("REMEDIATION", "ABSENT"), "REDACT_RECORD": ("REMEDIATION", "REDACTED"),
    "ANONYMIZE_RECORD": ("REMEDIATION", "ANONYMIZED"),
    "VERIFY_RECORD_ABSENT": ("VERIFICATION", "ABSENT"), "VERIFY_RECORD_PRESENT": ("VERIFICATION", "PRESENT"),
    "VERIFY_RECORD_REDACTED": ("VERIFICATION", "REDACTED"), "VERIFY_RECORD_ANONYMIZED": ("VERIFICATION", "ANONYMIZED"),
    "VERIFY_DATA_FLOW_DISABLED": ("VERIFICATION", "DISABLED"), "VERIFY_RESTORE_BLOCKED": ("VERIFICATION", "BLOCKED"),
}


def S(op: str, system: str, rid: str, evidence: str = "") -> dict:
    phase, state = CONTRACT[op]
    return {"phase": phase, "system_id": system, "resource_id": rid, "operation": op, "state": state,
            "evidence_id": evidence}


def numbered(steps: list) -> list:
    return [dict(s, step_no=i) for i, s in enumerate(steps, 1)]


# ------------------------------------------------------------------------------------------------ renderers
def sql_snapshot(topology: str, captured: str, tables: dict) -> str:
    """tables: name -> list of (resource_id, origin_system, collection, record dict, updated_at)."""
    out = ["-- Ghost Data Still Exists: point-in-time database snapshot", "-- Dialect: SQLite-compatible SQL",
           f"-- Captured at: {captured}", f"-- Database topology: {topology}",
           "-- Compare the primary and any replica tables for replication drift.", "", "BEGIN TRANSACTION;"]
    for name, rows in tables.items():
        out.append(f"CREATE TABLE {name} (resource_id TEXT PRIMARY KEY, origin_system TEXT NOT NULL, "
                   "collection_name TEXT NOT NULL, record_json TEXT NOT NULL CHECK (json_valid(record_json)), "
                   "updated_at TEXT NOT NULL);")
        for rid, origin, coll, rec, upd in rows:
            body = json.dumps(rec, separators=(",", ":")).replace("'", "''")
            out.append(f"INSERT INTO \"{name}\" VALUES('{rid}','{origin}','{coll}','{body}','{upd}');")
    out.append("COMMIT;")
    return "\n".join(out) + "\n"


def log_line(dialect: str, ts: str, level: str, service: str, trace: str, event: str, **kv) -> str:
    q = lambda v: str(v)                                                                  # noqa: E731
    if dialect == "kv":
        body = " ".join(f"{k}={q(v)}" for k, v in kv.items())
        return f"{ts} level={level} service={service} trace_id={trace} event={event} {body}"
    if dialect == "json":
        doc = {"severity": level, "service": service, "trace_id": trace, "event": event, **{k: q(v) for k, v in kv.items()}}
        return f"{ts} {json.dumps(doc, separators=(',', ':'))}"
    body = " ".join(f'{k}="{q(v)}"' for k, v in kv.items())
    if dialect == "syslog":
        return f'{ts} <15>1 node-1 {service} {trace} - - level={level} event="{event}" {body}'
    if dialect == "bracket":
        return f"{ts} [{level}] [{service}] [{trace}] {event}: {body}"
    if dialect == "pipe":
        return f"{ts} | {level} | {service} | {trace} | {event} | {body}"
    if dialect == "cloud":
        inner = f'event=\\"{event}\\" ' + " ".join(f'{k}=\\"{q(v)}\\"' for k, v in kv.items())
        return f'{ts} requestId={trace} level={level} function={service} message="{inner}"'
    raise ValueError(dialect)


# ------------------------------------------------------------------------------------------------------ world
class World:
    def __init__(self):
        self.users, self.audit, self.activity, self.requests, self.files, self.expected = [], [], [], [], [], {}
        self.notes = {}

    def user(self, uid: str, name: str, email: str, phone: str = "+44 7700 900100"):
        h = hashlib.sha256(email.lower().encode()).hexdigest()
        self.users.append([uid, name, email, phone, h, "2026-01-01T00:00:00Z"])

    def file(self, rel: str, text: str, captured: str) -> str:
        fid = f"evidence_{len(self.files) + 1:02d}"
        self.files.append((fid, rel, captured, text))
        return fid

    def case(self, cid: str, email: str, requested: str, status: str, reported: str, audit: str, text: str,
             expected_status: str, steps: list, note: str):
        self.requests.append([cid, email, requested, status, reported, audit, text])
        self.expected[cid] = (expected_status, numbered(steps))
        self.notes[cid] = note

    def write(self, root: Path) -> Dataset:
        def w(name, header, rows):
            with open(root / name, "w", newline="", encoding="utf-8") as fh:
                cw = csv.writer(fh)
                cw.writerow(header)
                cw.writerows(rows)
        req_hdr = ["case_id", "email", "requested_at", "reported_status", "reported_at", "audit_at", "request_text"]
        w("deletion_requests.csv", req_hdr, self.requests)
        w("sample_deletion_requests.csv", req_hdr, [])
        w("user_identities.csv", ["user_id", "name", "email", "phone", "email_hash", "updated_at"], self.users)
        w("user_audit_log.csv", ["audit_id", "user_id", "event_time", "field_name", "old_value", "new_value"], self.audit)
        w("system_activity.csv", ["activity_id", "event_time", "event_type", "source_system", "target_system",
                                  "resource_id", "reported_result", "details"], self.activity)
        w("deletion_rules.csv", ["rule_id", "data_category", "condition", "required_action"], [])
        w("evidence_files.csv", ["file_id", "file_path", "origin", "captured_at"],
          [[fid, rel, "synthetic", cap] for fid, rel, cap, _t in self.files])
        for fid, rel, _cap, text in self.files:
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        return Dataset(root)


def build_world() -> World:
    wd = World()
    P = "2026-"

    # ---------------------------------------------------------------- CC-1 reporting-replica layout, ghost account
    wd.user("user_901", "Anna Ceder", "anna.ceder@example.org")
    wd.user("user_902", "Other Person", "someone.else@example.org")
    cap = P + "02-10T11:00:00Z"
    prim = [("audit_record_5003", "security_service", "security_audit_events",
             {"resource_id": "audit_record_5003", "subject_reference": "user_901", "event_name": "account_deletion_reviewed"}, cap),
            ("search_5002", "search_service", "customer_search_documents",
             {"resource_id": "search_5002", "index_name": "customer_directory_v3",
              "document": {"display_name": None, "email": "anna.ceder@example.org"}}, cap),
            ("search_5090", "search_service", "customer_search_documents",
             {"resource_id": "search_5090", "index_name": "customer_directory_v3",
              "document": {"display_name": None, "email": "someone.else@example.org"}}, cap)]
    ghost = ("account_5001", "account_service", "customer_profiles",
             {"resource_id": "account_5001", "customer_reference": "user_901", "full_name": "Anna Ceder",
              "email": "anna.ceder@example.org", "phone": "+44 7700 900100", "account_status": "ACTIVE"}, cap)
    f1 = wd.file("evidence/databases/customer_data_reporting_replica_20260210.sql",
                 sql_snapshot("reporting_replica", cap, {"customer_data_primary": prim,
                                                         "customer_data_reporting_replica": prim + [ghost]}), cap)
    wd.case("case_901", "anna.ceder@example.org", P + "02-01T09:00:00Z", "COMPLETE", P + "02-02T09:00:00Z", P + "02-10T12:00:00Z",
            "Please delete my account and all personal data you hold about me.", "INCOMPLETE", [
                S("REPORT_REMAINING_RECORD", "account_service", "account_5001", f1),
                S("REPORT_REMAINING_RECORD", "search_service", "search_5002", f1),
                S("DELETE_RECORD", "account_service", "account_5001"), S("DELETE_RECORD", "search_service", "search_5002"),
                S("VERIFY_RECORD_ABSENT", "account_service", "account_5001"), S("VERIFY_RECORD_ABSENT", "search_service", "search_5002"),
                S("VERIFY_RECORD_PRESENT", "security_service", "audit_record_5003")],
            "Reporting-replica layout. The account row exists only in the replica (drift), the search document is in both "
            "tables, a decoy search document belongs to another person, the audit record must be kept.")

    # ---------------------------------------------------------------- CC-2 regional-replicas layout
    wd.user("user_903", "Bo Lindahl", "bo.lindahl@example.org")
    cap = P + "03-20T11:00:00Z"
    prim = [("audit_record_5103", "security_service", "security_audit_events",
             {"resource_id": "audit_record_5103", "subject_reference": "user_903", "event_name": "account_deletion_reviewed"}, cap),
            ("support_5102", "support_platform", "ticket_attachments",
             {"resource_id": "support_5102", "ticket_id": "CS-1", "file_name": "invoice_3.pdf",
              "uploaded_by": "bo.lindahl@example.org", "storage_class": "ticket_attachment"}, cap)]
    ghost = ("account_5101", "account_service", "customer_profiles",
             {"resource_id": "account_5101", "customer_reference": "user_903", "full_name": "Bo Lindahl",
              "email": "bo.lindahl@example.org", "phone": "+44 7700 900100", "account_status": "ACTIVE"}, cap)
    f2 = wd.file("evidence/databases/customer_data_regional_replicas_20260320.sql",
                 sql_snapshot("regional_replicas", cap, {"customer_data_primary": prim, "customer_data_replica_eu_west": prim,
                                                         "customer_data_replica_ap_south": prim + [ghost]}), cap)
    wd.case("case_902", "bo.lindahl@example.org", P + "03-10T09:00:00Z", "PARTIALLY_COMPLETE", P + "03-11T09:00:00Z", P + "03-20T12:00:00Z",
            "I would like my account closed and my data erased.", "INCOMPLETE", [
                S("REPORT_REMAINING_RECORD", "account_service", "account_5101", f2),
                S("REPORT_REMAINING_RECORD", "support_platform", "support_5102", f2),
                S("DELETE_RECORD", "account_service", "account_5101"), S("DELETE_RECORD", "support_platform", "support_5102"),
                S("VERIFY_RECORD_ABSENT", "account_service", "account_5101"), S("VERIFY_RECORD_ABSENT", "support_platform", "support_5102"),
                S("VERIFY_RECORD_PRESENT", "security_service", "audit_record_5103")],
            "Regional-replicas layout. The ghost account sits in one of two regional replicas only; the support attachment "
            "is in all three tables and is the person's own attachment (deleted, not redacted).")

    # ---------------------------------------------------------------- CC-3 failover layout, exposed tombstone in the replica
    wd.user("user_904", "Carla Dunn", "carla.dunn@example.org")
    cap = P + "04-30T11:00:00Z"
    audit_row = ("audit_record_5202", "security_service", "security_audit_events",
                 {"resource_id": "audit_record_5202", "subject_reference": "user_904", "event_name": "account_deletion_reviewed"}, cap)
    tomb_clean = ("tombstone_5201", "identity_service", "deleted_customer_references",
                  {"resource_id": "tombstone_5201", "subject_reference": "user_904", "name": None, "email": None, "phone": None,
                   "email_hash": None, "account_status": "DELETED"}, cap)
    tomb_dirty = ("tombstone_5201", "identity_service", "deleted_customer_references",
                  {"resource_id": "tombstone_5201", "subject_reference": "user_904", "name": "Carla Dunn",
                   "email": "carla.dunn@example.org", "phone": None, "email_hash": None, "account_status": "DELETED"}, cap)
    f3 = wd.file("evidence/databases/customer_data_failover_replica_20260430.sql",
                 sql_snapshot("failover_replica", cap, {"customer_data_failover_replica": [audit_row, tomb_dirty],
                                                        "customer_data_primary": [audit_row, tomb_clean]}), cap)
    wd.activity.append(["activity_901", P + "04-29T08:20:00Z", "DELETE_RECORD", "deletion_worker", "account_service",
                        "account_5200", "SUCCESS", "Deletion worker received the final result for account_5200."])
    wd.case("case_903", "carla.dunn@example.org", P + "04-28T09:00:00Z", "COMPLETE", P + "04-29T09:00:00Z", P + "04-30T12:00:00Z",
            "Hello, please delete my account. I no longer use the service.", "INCOMPLETE", [
                S("REPORT_EXPOSED_PII", "identity_service", "tombstone_5201", f3),
                S("REDACT_RECORD", "identity_service", "tombstone_5201"),
                S("VERIFY_RECORD_ABSENT", "account_service", "account_5200"),
                S("VERIFY_RECORD_PRESENT", "security_service", "audit_record_5202"),
                S("VERIFY_RECORD_REDACTED", "identity_service", "tombstone_5201")],
            "Failover layout. The primary tombstone is redacted but the failover replica still holds the name and email: the "
            "tombstone is kept (never deleted) and redacted. The account has no row anywhere, only a successful delete event "
            "shortly before the report, so it is verified absent without a citation.")

    # ------------------------------- CC-4 one scenario, six log dialects (five eval-only ones plus key=value as control)
    dialects = ["json", "syslog", "bracket", "pipe", "cloud", "kv"]
    for i, dia in enumerate(dialects):
        n = 905 + i
        uid, email = f"user_{n}", f"dialect.user{n}@example.org"
        wd.user(uid, f"Dialect User {n}", email)
        audit_at = f"2026-{5 + i // 2:02d}-{(5 if i % 2 == 0 else 25):02d}T12:00:00Z"
        cap = audit_at.replace("T12:", "T11:")
        t = lambda mm, ss, d=audit_at: d[:11] + f"11:{mm:02d}:{ss:02d}Z"                   # noqa: E731
        acc, flow, bak, aud = f"account_{n}1", f"data_flow_{n}2", f"backup_{n}3", f"audit_record_{n}4"
        L = []
        for k, (svc, started, completed, kvs) in enumerate([
                ("account_service", "profile_lookup_started", "profile_lookup_completed",
                 {"resource_id": acc, "rows": 0, "http_status": 404}),
                ("integration_service", "connector_config_read_started", "connector_config_read_completed",
                 {"resource_id": flow, "enabled": "true", "scheduler_registered": "true"}),
                ("backup_service", "restore_policy_read_started", "restore_policy_read_completed",
                 {"resource_id": bak, "restore_allowed": "true", "archive_present": "true"}),
                ("security_service", "audit_record_read_started", "audit_record_read_completed",
                 {"resource_id": aud, "rows": 1})]):
            tr = f"tr-{n}{k}"
            L.append(log_line(dia, t(10 + k, 1), "INFO", svc, tr, started, resource_id=kvs["resource_id"], lookup_key=email))
            L.append(log_line(dia, t(10 + k, 2), "INFO", svc, tr, completed, **kvs, subject_key=email))
        L.append(log_line(dia, t(20, 0), "DEBUG", "db_pool", f"tr-{n}9", "connection_acquired", pool="main"))
        L.append(log_line(dia, t(20, 5), "DEBUG", "db_pool", f"tr-{n}8", "pool_sample", active="3"))
        fid = wd.file(f"evidence/logs/dialect_probe_{dia}_{audit_at[:10].replace('-', '')}.log", "\n".join(L) + "\n", cap)
        wd.case(f"case_{n}", email, audit_at[:8] + "01T09:00:00Z", "PARTIALLY_COMPLETE", audit_at[:8] + "02T09:00:00Z", audit_at,
                "Please erase my account and everything linked to it.", "INCOMPLETE", [
                    S("REPORT_ACTIVE_DATA_FLOW", "integration_service", flow, fid),
                    S("REPORT_RESTORE_RISK", "backup_service", bak, fid),
                    S("DISABLE_DATA_FLOW", "integration_service", flow), S("BLOCK_RESTORE", "backup_service", bak),
                    S("VERIFY_RECORD_ABSENT", "account_service", acc),
                    S("VERIFY_RECORD_PRESENT", "security_service", aud),
                    S("VERIFY_DATA_FLOW_DISABLED", "integration_service", flow), S("VERIFY_RESTORE_BLOCKED", "backup_service", bak)],
                f"Log dialect `{dia}`. The same scenario in every dialect: account lookup 404, connector enabled, restore allowed, "
                "audit record present, plus noise lines that must be ignored. Data flows are disabled before restores are blocked.")

    # ------------------------------------------------- CC-5 clock rules, historical email, a claim that contradicts the evidence
    wd.user("user_911", "Dana Ekwueme", "dana.ekwueme@example.org")
    wd.audit.append(["audit_901", "user_911", "2026-01-02T10:00:00Z", "email", "d.ekwueme@old-mail.example", "dana.ekwueme@example.org"])
    audit_at = P + "08-30T12:00:00Z"
    cap = P + "08-30T11:00:00Z"
    home = [log_line("syslog", P + "08-30T10:40:01Z", "INFO", "account_service", "tr-9111", "profile_lookup_started",
                     resource_id="account_9001", lookup_key="dana.ekwueme@example.org"),
            log_line("syslog", P + "08-30T10:40:02Z", "INFO", "account_service", "tr-9111", "profile_lookup_completed",
                     resource_id="account_9001", rows=0, http_status=404),
            log_line("syslog", P + "08-30T10:42:01Z", "INFO", "support_platform", "tr-9112", "support_ticket_read_started",
                     resource_id="support_9003", lookup_key="dana.ekwueme@example.org"),
            log_line("syslog", P + "08-30T10:42:02Z", "INFO", "support_platform", "tr-9112", "support_ticket_read_completed",
                     resource_id="support_9003", customer_reference="user_911", requester_name="null", requester_email="null",
                     requester_phone="null"),
            log_line("syslog", P + "08-30T10:44:01Z", "INFO", "security_service", "tr-9113", "audit_record_read_started",
                     resource_id="audit_record_9004", lookup_key="dana.ekwueme@example.org"),
            log_line("syslog", P + "08-30T10:44:02Z", "INFO", "security_service", "tr-9113", "audit_record_read_completed",
                     resource_id="audit_record_9004", rows=1),
            # planted: dated after the audit although it sits in this file; must be ignored (record gate)
            log_line("syslog", P + "09-02T08:00:01Z", "INFO", "account_service", "tr-9114", "profile_lookup_started",
                     resource_id="account_9001", lookup_key="dana.ekwueme@example.org"),
            log_line("syslog", P + "09-02T08:00:02Z", "INFO", "account_service", "tr-9114", "profile_lookup_completed",
                     resource_id="account_9001", rows=1, http_status=200)]
    f5 = wd.file("evidence/logs/syslog_archive_us_east_20260830.log", "\n".join(home) + "\n", cap)
    late = [log_line("json", P + "08-31T10:00:01Z", "INFO", "account_service", "tr-9121", "profile_lookup_started",
                     resource_id="account_9001", lookup_key="dana.ekwueme@example.org"),
            log_line("json", P + "08-31T10:00:02Z", "INFO", "account_service", "tr-9121", "profile_lookup_completed",
                     resource_id="account_9001", rows=1, http_status=200)]
    wd.file("evidence/logs/structured_service_events_eu_west_20260901.log", "\n".join(late) + "\n", P + "09-01T12:00:00Z")
    wd.case("case_911", "d.ekwueme@old-mail.example", P + "08-20T09:00:00Z", "NOT_STARTED", P + "08-21T09:00:00Z", audit_at,
            "Please remove my account. I changed my email address a while ago, this is the old one.", "COMPLETE", [
                S("VERIFY_RECORD_ABSENT", "account_service", "account_9001", f5),
                S("VERIFY_RECORD_PRESENT", "security_service", "audit_record_9004", f5),
                S("VERIFY_RECORD_REDACTED", "support_platform", "support_9003", f5)],
            "Request made with a historical email. The workflow claims NOT_STARTED but the evidence at the audit time shows the "
            "account gone, the ticket redacted and the audit record kept. A record dated after the audit sits in the same file "
            "and a later-captured file says the account is present: neither may change the answer or be cited.")

    # ------------------------------------------------------------------------------------- CC-6 non-deletion requests
    wd.user("user_912", "Eva Marín", "eva.marin@example.org")
    wd.user("user_913", "Finn Olsen", "finn.olsen@example.org")
    wd.case("case_912", "eva.marin@example.org", P + "06-01T09:00:00Z", "NOT_STARTED", P + "06-02T09:00:00Z", P + "06-10T12:00:00Z",
            "Hola, ¿podrían enviarme una copia de todos los datos personales que tienen sobre mí? Gracias.", "NOT_APPLICABLE", [],
            "Access request in Spanish.")
    wd.case("case_913", "finn.olsen@example.org", P + "06-03T09:00:00Z", "COMPLETE", P + "06-04T09:00:00Z", P + "06-10T12:00:00Z",
            "Please stop sending me promotional emails, but keep my account and my order history.", "NOT_APPLICABLE", [],
            "Marketing opt-out that explicitly keeps the account.")
    return wd


def evaluate() -> dict:
    wd = build_world()
    with tempfile.TemporaryDirectory() as tmp:
        ds = wd.write(Path(tmp))
        res = run(ds, ds.requests, PlanOptions())
        pred = {cid: (r.status, r.steps) for cid, r in res.results.items()}
        sc = score(pred, wd.expected)
        return {"world": wd, "pred": pred, "score": sc, "warnings": res.warnings}


def render(result: dict) -> str:
    wd, sc = result["world"], result["score"]
    L = ["# Additional evaluation cases (generated by `python3 code/evaluation/custom_cases.py`)", "",
         "Hand-built worlds in evidence formats that no sample answer exercises. The expected answers were derived from the task "
         "contract before the pipeline was run; the scorer is the same one used for the samples.", "",
         render_scorecard(sc, f"Result on {sc.n_cases} custom cases"), "", "## The cases", ""]
    for cid in sorted(wd.expected, key=lambda c: int(c.split("_")[1])):
        status, steps = wd.expected[cid]
        got = result["pred"][cid]
        L += [f"### {cid}: {wd.notes[cid]}", "",
              f"Expected {status} with {len(steps)} steps; produced {got[0]} with {len(got[1])} steps; "
              f"{'identical' if (status, steps) == got else 'DIFFERENT'}.", ""]
        if steps:
            L += ["| # | phase | operation | system | resource | state | evidence |", "|---|---|---|---|---|---|---|"]
            for s in steps:
                L.append(f"| {s['step_no']} | {s['phase']} | {s['operation']} | {s['system_id']} | {s['resource_id']} | {s['state']} | "
                         f"{s['evidence_id'] or '-'} |")
            L.append("")
    return "\n".join(L)


def main() -> int:
    result = evaluate()
    text = render(result)
    OUT.write_text(text, encoding="utf-8")
    sc = result["score"]
    p, r, f = sc.step_prf()
    print(f"custom cases: status {sc.status_correct}/{sc.n_cases}, step P/R/F1 {p:.3f}/{r:.3f}/{f:.3f}, exact {sc.exact_cases}/{sc.n_cases}")
    for d in sc.discrepancies:
        print("  ", d.case_id, d.kind, d.detail)
    return 0 if sc.exact_cases == sc.n_cases else 1


if __name__ == "__main__":
    sys.exit(main())
