"""Scorer for predicted vs. golden answers.

Only this module reads sample_output.csv (the pipeline never does). The hidden grader's weights are unknown, so every
component is reported separately instead of being folded into one number.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ghostaudit import model as m                      # noqa: E402
from ghostaudit.data import case_sort_key              # noqa: E402

KEY_FIELDS = ("phase", "system_id", "resource_id", "operation")
ALL_FIELDS = m.STEP_FIELDS


def load_answers(path: Path) -> dict:
    with open(path, newline="", encoding="utf-8") as fh:
        return {r["case_id"]: (r["deletion_status"], json.loads(r["steps_json"])) for r in csv.DictReader(fh)}


def _key(s: dict) -> tuple:
    return tuple(s[k] for k in KEY_FIELDS)


def _full(s: dict) -> tuple:
    return tuple(s[k] for k in ALL_FIELDS if k != "step_no")


def _lcs(a: list, b: list) -> int:
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    for x in a:
        cur = [0]
        for j, y in enumerate(b, 1):
            cur.append(prev[j - 1] + 1 if x == y else max(prev[j], cur[-1]))
        prev = cur
    return prev[-1]


@dataclass
class Discrepancy:
    case_id: str
    kind: str            # STATUS | MISSING | EXTRA | FIELD | ORDER
    detail: str
    tag: str = ""        # root-cause tag, filled in by the caller's classifier


@dataclass
class Scorecard:
    n_cases: int = 0
    status_correct: int = 0
    confusion: Counter = field(default_factory=Counter)
    per_class: dict = field(default_factory=lambda: defaultdict(lambda: [0, 0]))   # gold status -> [correct, total]
    tp: int = 0
    fp: int = 0
    fn: int = 0
    key_tp: int = 0
    key_fp: int = 0
    key_fn: int = 0
    field_hits: Counter = field(default_factory=Counter)
    field_total: Counter = field(default_factory=Counter)
    exact_cases: int = 0
    pos_hits: int = 0           # golden steps whose position holds an identical predicted step
    pos_total: int = 0
    lcs_sum: float = 0.0
    discrepancies: list = field(default_factory=list)
    exact_case_ids: list = field(default_factory=list)

    @staticmethod
    def _prf(tp, fp, fn):
        p = tp / (tp + fp) if tp + fp else 1.0
        r = tp / (tp + fn) if tp + fn else 1.0
        return p, r, (2 * p * r / (p + r) if p + r else 0.0)

    def step_prf(self):
        return self._prf(self.tp, self.fp, self.fn)

    def key_prf(self):
        return self._prf(self.key_tp, self.key_fp, self.key_fn)


def score(pred: dict, gold: dict, classify=None) -> Scorecard:
    """pred/gold: case_id -> (status, steps). `classify(case_id, discrepancy)` may return a root-cause tag."""
    sc = Scorecard()
    for cid in sorted(gold, key=case_sort_key):
        g_status, g_steps = gold[cid]
        p_status, p_steps = pred.get(cid, ("<missing>", []))
        sc.n_cases += 1
        sc.confusion[(g_status, p_status)] += 1
        sc.per_class[g_status][1] += 1
        if g_status == p_status:
            sc.status_correct += 1
            sc.per_class[g_status][0] += 1
        else:
            sc.discrepancies.append(Discrepancy(cid, "STATUS", f"predicted {p_status}, golden {g_status}"))
        # step multiset match on the full tuple (step_no ignored)
        g_full, p_full = Counter(_full(s) for s in g_steps), Counter(_full(s) for s in p_steps)
        tp = sum((g_full & p_full).values())
        sc.tp += tp
        sc.fp += sum(p_full.values()) - tp
        sc.fn += sum(g_full.values()) - tp
        # identification match on (phase, system, resource, operation)
        g_key, p_key = Counter(_key(s) for s in g_steps), Counter(_key(s) for s in p_steps)
        ktp = sum((g_key & p_key).values())
        sc.key_tp += ktp
        sc.key_fp += sum(p_key.values()) - ktp
        sc.key_fn += sum(g_key.values()) - ktp
        # field-level accuracy over golden steps aligned by key
        p_by_key = {_key(s): s for s in p_steps}
        for i, gs in enumerate(g_steps):
            ps = p_by_key.get(_key(gs))
            for f in ALL_FIELDS:
                sc.field_total[f] += 1
                if f in KEY_FIELDS:
                    ok = ps is not None
                elif f == "step_no":
                    ok = ps is not None and ps["step_no"] == gs["step_no"]
                else:
                    ok = ps is not None and ps[f] == gs[f]
                sc.field_hits[f] += ok
            if ps is None:
                sc.discrepancies.append(Discrepancy(cid, "MISSING", _fmt(gs)))
            else:
                for f in ("state", "evidence_id"):
                    if ps[f] != gs[f]:
                        sc.discrepancies.append(Discrepancy(cid, "FIELD", f"{_fmt(gs)}: {f} predicted {ps[f]!r}, golden {gs[f]!r}"))
        for ps in p_steps:
            if _key(ps) not in g_key:
                sc.discrepancies.append(Discrepancy(cid, "EXTRA", _fmt(ps)))
        # positional accuracy: step i of the prediction equals step i of the golden answer (all seven fields)
        sc.pos_total += len(g_steps)
        sc.pos_hits += sum(1 for gs, ps in zip(g_steps, p_steps) if _norm(gs) == _norm(ps))
        # sequence accuracy
        g_seq, p_seq = [_key(s) for s in g_steps], [_key(s) for s in p_steps]
        denom = max(len(g_seq), len(p_seq))
        sc.lcs_sum += (_lcs(g_seq, p_seq) / denom) if denom else 1.0
        if g_status == p_status and [_norm(s) for s in g_steps] == [_norm(s) for s in p_steps]:
            sc.exact_cases += 1
            sc.exact_case_ids.append(cid)
        elif g_status == p_status and Counter(_key(s) for s in g_steps) == Counter(_key(s) for s in p_steps) \
                and g_seq != p_seq:
            sc.discrepancies.append(Discrepancy(cid, "ORDER", "same steps in a different order"))
    if classify:
        for d in sc.discrepancies:
            d.tag = classify(d.case_id, d) or d.tag
    return sc


def _norm(s: dict) -> tuple:
    return tuple(s[k] for k in ALL_FIELDS)


def _fmt(s: dict) -> str:
    ev = s["evidence_id"] or "-"
    return f"{s['phase'][:4]} {s['operation']} {s['system_id']}/{s['resource_id']} @{ev}"


# ---------------------------------------------------------------------------------- visibility of golden ids
def visible_resource_ids(dataset_root: Path, extra_texts=()) -> set:
    """Every resource id that appears anywhere in participant-facing data (never in the answer files)."""
    seen = set()
    skip = {"sample_output.csv", "output.csv"}
    for p in Path(dataset_root).rglob("*"):
        if p.is_file() and p.name not in skip and p.suffix.lower() in (".csv", ".txt", ".log", ".json", ".sql"):
            seen.update(m.RID_RE.findall(p.read_text(encoding="utf-8", errors="ignore")))
    for t in extra_texts:
        seen.update(m.RID_RE.findall(t))
    return seen


# ------------------------------------------------------------------------------------ derived (unverified) cases
_FENCE = re.compile(r"```json\n(.*?)\n```", re.S)


def load_derived(path: Path) -> list:
    if not Path(path).exists():
        return []
    return [json.loads(b) for b in _FENCE.findall(Path(path).read_text(encoding="utf-8"))]


def score_derived(pred: dict, derived: list) -> list:
    """For each hand-derived case: does the status match and are the required core steps present?
    These expectations are my own reading of the evidence; they are NOT ground truth and never enter headline numbers."""
    out = []
    for d in derived:
        status, steps = pred.get(d["case_id"], ("<missing>", []))
        have = {(s["phase"], s["resource_id"], s["operation"], s["state"], s["evidence_id"]) for s in steps}
        req = [(r["phase"], r["resource_id"], r["operation"], r["state"], r["evidence_id"]) for r in d["required_steps"]]
        missing = [r for r in req if r not in have]
        out.append({"case_id": d["case_id"], "status_ok": status == d["status"], "predicted": status,
                    "expected": d["status"], "required": len(req), "found": len(req) - len(missing), "missing": missing,
                    "confidence": d.get("confidence", ""), "note": d.get("note", "")})
    return out


# ------------------------------------------------------------------------------------------------- rendering
def render_scorecard(sc: Scorecard, title: str, tag_counts: Counter | None = None) -> str:
    p, r, f = sc.step_prf()
    kp, kr, kf = sc.key_prf()
    L = [f"## {title}", "", f"Cases: {sc.n_cases}", "", "| metric | value |", "|---|---|",
         f"| case status accuracy | {sc.status_correct}/{sc.n_cases} = {sc.status_correct / max(sc.n_cases, 1):.1%} |",
         f"| step-level exact match: precision / recall / F1 | {p:.3f} / {r:.3f} / {f:.3f} (tp {sc.tp}, fp {sc.fp}, fn {sc.fn}) |",
         f"| step identification (phase, system, resource, operation): P / R / F1 | {kp:.3f} / {kr:.3f} / {kf:.3f} |",
         f"| cases reproduced exactly (status and every step, order and step_no) | {sc.exact_cases}/{sc.n_cases} = {sc.exact_cases / max(sc.n_cases, 1):.1%} |",
         f"| mean sequence overlap (LCS of step keys / longer sequence) | {sc.lcs_sum / max(sc.n_cases, 1):.3f} |",
         f"| positional match (step i equals golden step i, all seven fields) | {sc.pos_hits}/{sc.pos_total} = {sc.pos_hits / max(sc.pos_total, 1):.1%} |", ""]
    L += ["Field-level accuracy over golden steps (aligned by phase, system, resource, operation):", "",
          "| field | correct |", "|---|---|"]
    for f_ in ALL_FIELDS:
        L.append(f"| {f_} | {sc.field_hits[f_]}/{sc.field_total[f_]} = {sc.field_hits[f_] / max(sc.field_total[f_], 1):.1%} |")
    L += ["", "Status by golden class:", "", "| golden | correct / total |", "|---|---|"]
    for k, (c, t) in sorted(sc.per_class.items()):
        L.append(f"| {k} | {c}/{t} |")
    L += ["", "Confusion (golden -> predicted):", ""]
    L += [f"- {g} -> {p_}: {n}" for (g, p_), n in sorted(sc.confusion.items())]
    if tag_counts:
        L += ["", "Discrepancies by root cause:", ""] + [f"- {t or 'untagged'}: {n}" for t, n in tag_counts.most_common()]
    L += ["", f"Every discrepancy ({len(sc.discrepancies)}):", ""]
    by_case = defaultdict(list)
    for d in sc.discrepancies:
        by_case[d.case_id].append(d)
    for cid in sorted(by_case, key=case_sort_key):
        L.append(f"- **{cid}**")
        for d in by_case[cid]:
            L.append(f"  - {d.kind}{' [' + d.tag + ']' if d.tag else ''}: {d.detail}")
    if not sc.discrepancies:
        L.append("- none")
    return "\n".join(L)
