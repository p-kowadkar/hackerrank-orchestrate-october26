"""Per-format coverage, replica invariants and cross-format consistency.

Generates code/evaluation/coverage_report.md. Everything here is measured on participant-facing data; the only use of
golden answers is to say which evidence families the 32 samples actually exercise ("sample truth"), because the
families without it are the ones that need extra hardening.

Run: python3 code/evaluation/coverage.py
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ghostaudit import model as m                      # noqa: E402
from ghostaudit.data import Dataset                    # noqa: E402
from ghostaudit.evidence.logs import parse_line        # noqa: E402
from ghostaudit.paths import DATASET_DIR               # noqa: E402
from llm.offline import run_replay as run             # noqa: E402
from ghostaudit.planner import PlanOptions             # noqa: E402
from ghostaudit.timeutil import epoch                  # noqa: E402
from score import load_answers                         # noqa: E402

REGIONS = ("ap_south", "eu_west", "us_east", "ap_northeast", "eu_central", "us_west", "sa_east", "ca_central",
           "ap_southeast", "eu_north", "me_central", "af_south")
EVAL_ONLY_REPLICAS = ("data:reporting_replica", "data:regional_replicas", "data:failover_replica")   # families
EVAL_ONLY_LOGS = ("structured_service_events", "syslog_archive", "application_trace", "operations_stream",
                  "cloud_runtime_export")
EVAL_ONLY = EVAL_ONLY_REPLICAS + EVAL_ONLY_LOGS
OUT = Path(__file__).resolve().parent / "coverage_report.md"


def family_of(path: str) -> str:
    stem = Path(path).stem
    stem = re.sub(r"(_\d{8})(_\d{6})?$", "", stem)
    for r in REGIONS:
        if stem.endswith("_" + r):
            stem = stem[: -len(r) - 1]
    return stem.replace("customer_data_", "data:") if stem.startswith("customer_data_") else stem


def sample_truth_files(res, gold: dict) -> set:
    """Files a sample answer depends on: cited by a golden step, or deciding a resource of a sample case."""
    files = {s["evidence_id"] for _st, steps in gold.values() for s in steps if s["evidence_id"]}
    for cid in gold:
        for d in res.results[cid].decisions:
            if d.obs is not None:
                files.add(d.obs.file_id)
    return files


# ---------------------------------------------------------------------------------------------------- 1. coverage
def file_table(ds: Dataset, res, truth_files: set) -> list:
    rows = []
    for fid in sorted(ds.manifest, key=lambda f: int(f.split("_")[1])):
        row = ds.manifest[fid]
        st, unk = res.index.stats[fid], res.index.unknown[fid]
        path = ds.evidence_path(fid)
        lines = len([ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]) \
            if path.suffix in (".log", ".txt", ".sql", ".json") else 0
        dialects = ""
        if path.suffix == ".log":
            c = Counter()
            for ln in path.read_text(encoding="utf-8").splitlines():
                rec = parse_line(ln)
                if rec:
                    c[rec["dialect"]] += 1
            dialects = "+".join(f"{k}" for k, _v in c.most_common())
        rows.append({"fid": fid, "family": family_of(row["file_path"]), "ext": path.suffix.lstrip("."), "lines": lines,
                     "parsed": st["parsed"], "ignored": st["ignored"], "snapshots": st["snapshots"],
                     "unknown": st["unknown"], "skipped": st["skipped"], "dialect": dialects,
                     "unknown_what": dict(unk), "truth": fid in truth_files})
    return rows


def render_families(rows: list) -> list:
    fam = defaultdict(lambda: Counter())
    meta = {}
    for r in rows:
        f = fam[r["family"]]
        f["files"] += 1
        for k in ("parsed", "ignored", "snapshots", "unknown", "skipped"):
            f[k] += r[k]
        f["truth"] += r["truth"]
        meta[r["family"]] = r["ext"]
    L = ["| family | type | files | records parsed | noise ignored | snapshots | unknown | skipped | files a sample answer depends on |",
         "|---|---|---|---|---|---|---|---|---|"]
    for name in sorted(fam):
        f = fam[name]
        L.append(f"| {name} | {meta[name]} | {f['files']} | {f['parsed']} | {f['ignored']} | {f['snapshots']} | {f['unknown']} | "
                 f"{f['skipped']} | {f['truth']} |")
    return L


# ---------------------------------------------------------------------------------------------- 2. replica checks
def read_sql(path: Path) -> tuple:
    text = path.read_text(encoding="utf-8")
    con = sqlite3.connect(":memory:")
    try:
        con.executescript(text)
        tables = {}
        for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'"):
            cols = [c[1] for c in con.execute(f'PRAGMA table_info("{t}")')]
            tables[t] = [dict(zip(cols, r)) for r in con.execute(f'SELECT * FROM "{t}"')]
    finally:
        con.close()
    header = re.search(r"^-- Captured at:\s*(\S+)", text, re.M)
    topo = re.search(r"^-- Database topology:\s*(\S+)", text, re.M)
    return tables, (header.group(1) if header else ""), (topo.group(1) if topo else "")


def replica_files(ds: Dataset) -> list:
    out = []
    for fid, row in ds.manifest.items():
        if row["file_path"].endswith(".sql"):
            tables, header, topo = read_sql(ds.evidence_path(fid))
            if "customer_data_primary" in tables and len(tables) > 1:
                out.append((fid, row["file_path"], tables, header, topo))
    return sorted(out, key=lambda x: int(x[0].split("_")[1]))


def replica_report(ds: Dataset) -> tuple:
    rows, ghosts = [], []
    for fid, path, tables, header, topo in replica_files(ds):
        prim = {r["resource_id"]: r for r in tables["customer_data_primary"]}
        late = sum(1 for t in tables.values() for r in t if r["updated_at"] > header)
        diff = 0
        only = []
        for name, rs in tables.items():
            if name == "customer_data_primary":
                continue
            for r in rs:
                p = prim.get(r["resource_id"])
                if p is None:
                    only.append((name, r))
                elif p["record_json"] != r["record_json"]:
                    diff += 1
        for name, r in only:
            ghosts.append((fid, name, r["resource_id"], r["collection_name"], json.loads(r["record_json"])))
        rows.append({"fid": fid, "family": family_of(path), "topology": topo, "tables": len(tables),
                     "rows": sum(len(t) for t in tables.values()), "ghosts": len(only),
                     "ghost_kinds": sorted({r["collection_name"] for _n, r in only}), "content_diffs": diff, "late": late,
                     "eval_only": family_of(path) in EVAL_ONLY_REPLICAS})
    return rows, ghosts


def ghost_check(ds: Dataset, res, ghosts: list) -> list:
    """Each ghost account must show up as a REPORT_REMAINING_RECORD in every case that owns it and can see the file."""
    from ghostaudit.identity import IdentityResolver
    from ghostaudit.tokens import tokens_of_obj
    resolver = IdentityResolver(ds.identities, ds.audit_log)
    reqs = {r.case_id: r for r in ds.all_requests}
    out = []
    for fid, _table, rid, _coll, rec in ghosts:
        cap = ds.manifest[fid]["captured_at"]
        toks = tokens_of_obj(rec)
        owners = {u for t in toks for u in resolver.token_users.get(t, ())}
        for cid, r in res.results.items():
            if res.intents[cid][0] != "DELETE":
                continue
            uid, _ = resolver.resolve(reqs[cid].email)
            if uid in owners and cap <= reqs[cid].audit_at and epoch(reqs[cid].audit_at) - epoch(cap) <= 14 * 86400:
                found = any(s["resource_id"] == rid and s["operation"] == "REPORT_REMAINING_RECORD" for s in r.steps)
                out.append((fid, rid, cid, r.status, found))
    return out


# ------------------------------------------------------------------------------------ 3. cross-format consistency
def cross_format(res) -> dict:
    """Same resource, two different files, observation times within an hour: do the formats agree on type and state?"""
    stats = defaultdict(Counter)
    examples = defaultdict(list)
    fam = {}
    for o in res.index.obs:
        fam.setdefault(o.file_id, None)
    for rid, obs in res.index.by_rid.items():
        real = [o for o in obs if o.state != m.LINK]
        for i, a in enumerate(real):
            for b in real[i + 1:]:
                if a.file_id == b.file_id or abs(epoch(a.obs_time) - epoch(b.obs_time)) > 3600:
                    continue
                agree = (a.rtype, a.state) == (b.rtype, b.state)
                key = tuple(sorted((a.src.split(":")[0], b.src.split(":")[0])))
                stats[key]["agree" if agree else "differ"] += 1
                if not agree:
                    examples[key].append((rid, a.file_id, a.rtype, a.state, b.file_id, b.rtype, b.state))
    return {"stats": stats, "examples": examples}


def worker_agreement(ds: Dataset, res) -> dict:
    """For the record types where the worker's result tracks reality, how often does the parsed state agree, by family?"""
    ev = defaultdict(list)
    for a in ds.activity:
        ev[a["resource_id"]].append((a["event_type"], a["reported_result"], a["event_time"]))
    expect = {m.ANALYTICS: ("ANONYMIZE_RECORD", m.CLEAN), m.SUPPORT_MESSAGE: ("REDACT_RECORD", m.CLEAN),
              m.TOMBSTONE: ("REDACT_RECORD", m.CLEAN)}
    path_of = {fid: family_of(row["file_path"]) for fid, row in ds.manifest.items()}
    out = defaultdict(Counter)
    for r in res.results.values():
        for d in r.decisions:
            if d.obs is None or d.rtype not in expect:
                continue
            et, good = expect[d.rtype]
            events = [(rs, t) for e, rs, t in ev.get(d.resource_id, ()) if e == et]
            if not events:
                continue
            succeeded = any(rs == "SUCCESS" for rs, _t in events)
            ok = (d.state == good) == succeeded
            late = (not ok) and d.state == m.EXPOSED and succeeded and d.obs.obs_time > max(t for rs, t in events if rs == "SUCCESS")
            out[path_of[d.obs.file_id]]["agree" if ok else ("recreated after success" if late else "differ")] += 1
    return out


# ------------------------------------------------------------------------------------ 4. open semantics, how often
def semantic_counts(ds: Dataset, res) -> dict:
    idx = res.index
    c = {"legal-hold observations": sum(1 for o in idx.obs if o.rtype == m.LEGAL_HOLD),
         "tombstone observations": sum(1 for o in idx.obs if o.rtype == m.TOMBSTONE),
         "marketing-profile observations": sum(1 for o in idx.obs if o.rtype == m.MARKETING),
         "support ids seen as both message and attachment": sum(
             1 for rid, obs in idx.by_rid.items() if {o.rtype for o in obs if o.state != m.LINK} >= {m.SUPPORT_MESSAGE, m.SUPPORT_ATTACHMENT})}
    pend = expired = 0
    for fid, row in ds.manifest.items():
        text = ds.evidence_path(fid).read_text(encoding="utf-8", errors="ignore") if row["file_path"].endswith((".sql", ".json", ".txt", ".log")) else ""
        pend += text.count("DELETION_PENDING")
        expired += len(re.findall(r'download_available"?\s*[:=]\s*(?:false|0)', text))
    c["DELETION_PENDING mentions"] = pend
    c["exports with download_available false"] = expired
    return c


# ----------------------------------------------------------------------------------------------------- the report
def build_report() -> str:
    ds = Dataset()
    res = run(ds, ds.all_requests, PlanOptions())
    gold = load_answers(DATASET_DIR / "sample_output.csv")
    truth = sample_truth_files(res, gold)
    rows = file_table(ds, res, truth)
    unknown_total = sum(r["unknown"] for r in rows)
    L = ["# Evidence coverage and cross-format consistency (generated by `python3 code/evaluation/coverage.py`)", "",
         "Measured on participant-facing data. Golden sample answers are used only to say which families the 32 samples "
         "exercise; the families that none of them touches are the ones needing extra hardening.", "",
         "## 1. Coverage by family", "",
         f"{len(rows)} evidence files; unrecognised records across all files: **{unknown_total}** "
         "(a test fails if any state-bearing record is dropped silently). The 11 screenshots are read from the stored "
         "transcriptions (`code/llm/fixtures/transcribed/`): one parsed record each (the highlighted subject row); the other "
         "rows of a screen are context and are never observations. With `--llm off` they would show as `skipped`.", ""]
    L += render_families(rows)
    variants = [r for r in rows if r["family"] in EVAL_ONLY]
    L += ["", f"### The eight evidence variants with no sample truth ({len(variants)} files: three replica layouts, five log dialects)", "",
          "| file | family | type | lines | parsed | noise ignored | snapshots | unknown | line dialect |", "|---|---|---|---|---|---|---|---|---|"]
    for r in variants:
        L.append(f"| {r['fid']} | {r['family']} | {r['ext']} | {r['lines']} | {r['parsed']} | {r['ignored']} | {r['snapshots']} | "
                 f"{r['unknown']} | {r['dialect'] or '-'} |")
    L += ["", "Every log file uses exactly one dialect, and the five log families map to five different dialects: "
          "structured events = json, syslog archive = syslog, application trace = bracket, operations stream = pipe, "
          "cloud runtime export = cloud (requestId plus nested message).", ""]

    rep_rows, ghosts = replica_report(ds)
    L += ["## 2. Replica layouts: drift invariants", "",
          "Every SQL snapshot that has a `customer_data_primary` table plus replicas, including the sample-truth read "
          "replicas, so the three eval-only layouts can be compared with the ones the samples exercise.", "",
          "| file | family | topology | tables | rows | rows only in a replica | what kind | primary vs replica content differs | rows dated after the snapshot | eval-only layout |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rep_rows:
        L.append(f"| {r['fid']} | {r['family']} | {r['topology']} | {r['tables']} | {r['rows']} | {r['ghosts']} | "
                 f"{', '.join(r['ghost_kinds']) or '-'} | {r['content_diffs']} | {r['late']} | {'yes' if r['eval_only'] else 'no'} |")
    kinds = Counter(k for r in rep_rows for k in r["ghost_kinds"])
    L += ["", f"Invariants over {len(rep_rows)} files: ghost kinds {dict(kinds)}; primary/replica content differences "
          f"{sum(r['content_diffs'] for r in rep_rows)}; rows dated after their snapshot {sum(r['late'] for r in rep_rows)}. "
          "So replication drift always means the same thing in every layout: an account profile that exists only in a replica. "
          "That is why generic SQL rows are stamped with the snapshot time rather than their own `updated_at` (never later).", ""]
    chk = ghost_check(ds, res, ghosts)
    ok = sum(1 for *_x, found in chk if found)
    L += [f"Ghost accounts checked end to end: {len(ghosts)} replica-only rows; {len(chk)} (ghost, case) pairs where the owner has "
          f"a case within 14 days after the snapshot; the pipeline reports the ghost as a remaining record in **{ok}/{len(chk)}**.", ""]
    miss = [(f, r, c, s) for f, r, c, s, found in chk if not found]
    for f, r, c, s in miss[:10]:
        L.append(f"- not reported: {r} in {f} for {c} ({s})")
    L.append("")

    cf = cross_format(res)
    L += ["## 3. Cross-format consistency", "",
          "The same resource read through two different files, observation times within one hour: do the two formats give "
          "the same record type and state? Pairs are grouped by the formats involved.", "",
          "| format pair | agree | differ |", "|---|---|---|"]
    for key in sorted(cf["stats"]):
        c = cf["stats"][key]
        L.append(f"| {' / '.join(key)} | {c['agree']} | {c['differ']} |")
    tot_a = sum(c["agree"] for c in cf["stats"].values())
    tot_d = sum(c["differ"] for c in cf["stats"].values())
    L += ["", f"Overall: {tot_a} agree, {tot_d} differ.", ""]
    for key, ex in sorted(cf["examples"].items()):
        for e in ex[:12]:
            L.append(f"- differs ({' / '.join(key)}): {e[0]}: {e[1]} says {e[2]}/{e[3]}, {e[4]} says {e[5]}/{e[6]}")
    L += ["", "All the disagreements are one phenomenon: a support id that a home file renders as a ticket with requester "
          "details (message) and a later-captured file renders as an attachment. See evaluation_report.md, open risks.", ""]

    wa = worker_agreement(ds, res)
    L += ["## 4. Parsed state against the worker's outcome, by family of the deciding file", "",
          "Independent check for analytics, support messages and tombstones: a SUCCESS worker result should mean the "
          "record is clean in evidence. `recreated after success` is the deliberate trap (exposed again after the success).", "",
          "| family | agree | recreated after success | differ |", "|---|---|---|---|"]
    for fam_name in sorted(wa):
        c = wa[fam_name]
        L.append(f"| {fam_name} | {c['agree']} | {c['recreated after success']} | {c['differ']} |")
    L.append("")
    sc = semantic_counts(ds, res)
    L += ["## 5. How often the open semantic questions occur", ""] + [f"- {k}: {v}" for k, v in sc.items()] + [""]
    return "\n".join(L)


def main() -> None:
    text = build_report()
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
