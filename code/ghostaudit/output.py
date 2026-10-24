"""Deterministic writer and structural validator for output.csv."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from . import model as m
from .data import case_sort_key

HEADER = ["case_id", "deletion_status", "steps_json"]


def dump_steps(steps: list) -> str:
    return json.dumps([{k: s[k] for k in m.STEP_FIELDS} for s in steps], separators=(",", ":"), ensure_ascii=False)


def write_output(path: Path, results: dict) -> None:
    rows = [(cid, r.status, dump_steps(r.steps)) for cid, r in sorted(results.items(), key=lambda kv: case_sort_key(kv[0]))]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(HEADER)
        w.writerows(rows)


def read_output(path: Path) -> list:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def validate_output(path: Path, requests: list, manifest: dict | None = None) -> list:
    """Return a list of problems (empty = valid). `requests` are the Request rows the file must answer."""
    problems = []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        header = next(reader, None)
        raw = list(reader)
    if header != HEADER:
        problems.append(f"header is {header}, expected {HEADER}")
    req_by_id = {r.case_id: r for r in requests}
    ids = [r[0] for r in raw if r]
    if len(ids) != len(set(ids)):
        problems.append("duplicate case_id rows")
    if set(ids) != set(req_by_id):
        problems.append(f"case ids differ from the request file: missing {sorted(set(req_by_id) - set(ids))[:5]}, "
                        f"extra {sorted(set(ids) - set(req_by_id))[:5]}")
    if ids != sorted(ids, key=case_sort_key):
        problems.append("rows are not in natural case_id order")
    if len(raw) != len(requests):
        problems.append(f"{len(raw)} rows, expected {len(requests)}")
    for row in raw:
        if len(row) != 3:
            problems.append(f"{row[:1]}: row has {len(row)} columns")
            continue
        cid, status, js = row
        if status not in ("COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"):
            problems.append(f"{cid}: bad status {status!r}")
        try:
            steps = json.loads(js)
        except ValueError:
            problems.append(f"{cid}: steps_json is not valid JSON")
            continue
        if not isinstance(steps, list):
            problems.append(f"{cid}: steps_json is not an array")
            continue
        problems.extend(_check_steps(cid, status, steps, req_by_id.get(cid), manifest))
    return problems


def _check_steps(cid, status, steps, req, manifest) -> list:
    p = []
    if status == "NOT_APPLICABLE":
        return [] if steps == [] else [f"{cid}: NOT_APPLICABLE must have []"]
    keys = []
    phases_seen = []
    for i, s in enumerate(steps, 1):
        if set(s) != set(m.STEP_FIELDS):
            p.append(f"{cid}: step {i} has fields {sorted(s)}")
            continue
        if s["step_no"] != i:
            p.append(f"{cid}: step_no {s['step_no']} at position {i}")
        if s["phase"] not in m.PHASES or s["operation"] not in m.OPERATIONS:
            p.append(f"{cid}: unknown phase/operation at step {i}")
            continue
        if m.OP_PHASE[s["operation"]] != s["phase"] or m.OP_STATE[s["operation"]] != s["state"]:
            p.append(f"{cid}: step {i} phase/state does not match operation")
        ev = s["evidence_id"]
        must_cite = s["phase"] == "FINDING" or (s["phase"] == "VERIFICATION" and status == "COMPLETE")
        if s["phase"] == "REMEDIATION" or (s["phase"] == "VERIFICATION" and status == "INCOMPLETE"):
            if ev != "":
                p.append(f"{cid}: step {i} ({s['operation']}) must have an empty evidence_id")
        elif must_cite and not ev:
            p.append(f"{cid}: step {i} ({s['operation']}) must cite evidence")
        if ev and manifest is not None:
            if ev not in manifest:
                p.append(f"{cid}: step {i} cites unknown evidence {ev}")
            elif req is not None and manifest[ev]["captured_at"] > req.audit_at:
                p.append(f"{cid}: step {i} cites {ev} captured after audit_at")
        keys.append((m.PHASES.index(s["phase"]), m.OPERATIONS.index(s["operation"]), s["system_id"], s["resource_id"]))
        phases_seen.append(s["phase"])
    if keys != sorted(keys):
        p.append(f"{cid}: steps are not in phase / operation / system / resource order")
    if status == "COMPLETE" and any(ph != "VERIFICATION" for ph in phases_seen):
        p.append(f"{cid}: COMPLETE must contain verification steps only")
    if status == "INCOMPLETE" and not {"FINDING", "REMEDIATION", "VERIFICATION"} <= set(phases_seen):
        p.append(f"{cid}: INCOMPLETE must contain findings, remediation and verification")
    return p
