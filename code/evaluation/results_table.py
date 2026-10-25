"""Builds the numbers that evaluation_report.md quotes, so every figure in the report can be regenerated.

Run: python3 code/evaluation/results_table.py          (prints the blocks)
     python3 code/evaluation/results_table.py --write  (rewrites the marked blocks in evaluation_report.md)

Blocks are delimited by <!-- block:NAME --> ... <!-- /block:NAME --> lines in the report.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import custom_cases                                        # noqa: E402
from ghostaudit.data import Dataset                        # noqa: E402
from ghostaudit.paths import DATASET_DIR                   # noqa: E402
from ghostaudit.pipeline import run                        # noqa: E402
from ghostaudit.planner import PlanOptions                 # noqa: E402
from identity_backtest import cadence_hide_population, policy_value, render_policy_value   # noqa: E402
from main import evaluate, make_classifier, to_answers     # noqa: E402
from score import (load_answers, load_derived, render_scorecard, score_derived,          # noqa: E402
                   visible_resource_ids)
from ghostaudit.evidence import extract_links              # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent
REPORT = EVAL_DIR / "evaluation_report.md"


def collect() -> dict:
    ds = Dataset()
    res, pred, gold, sc = evaluate(ds, "hybrid")
    eval_ids = {r.case_id for r in ds.requests}
    sample_ids = set(gold)
    full = run(ds, ds.all_requests, PlanOptions())
    custom = custom_cases.evaluate()
    derived = load_derived(EVAL_DIR / "derived_cases.md")
    unverified = score_derived(to_answers(res.results), derived) if derived else []
    visible = visible_resource_ids(DATASET_DIR, extra_texts=[lk.resource_id for lk in extract_links(ds)])
    classify = make_classifier(visible, res)
    sc = __import__("score").score(pred, gold, classify)
    return {"ds": ds, "res": res, "sc": sc, "full": full, "custom": custom, "unverified": unverified,
            "eval_ids": eval_ids, "sample_ids": sample_ids}


def results_table(c: dict) -> str:
    sc, full = c["sc"], c["full"]
    tb_s = [u for u in full.tiebreak_uses if u.case_id in c["sample_ids"]]
    tb_e = [u for u in full.tiebreak_uses if u.case_id in c["eval_ids"]]
    cd_s = [u for u in full.cadence_uses if u.case_id in c["sample_ids"]]
    cd_e = [u for u in full.cadence_uses if u.case_id in c["eval_ids"]]
    ev = [full.results[i] for i in c["eval_ids"]]
    st = Counter(r.status for r in ev)
    p, r, f = sc.step_prf()
    unv = c["unverified"]
    L = ["Only the 32 golden samples carry accuracy figures. The second row is a count of how often the two dataset-specific "
         "heuristics were used, not an accuracy.", "",
         "| scope | cases | status accuracy | step P / R / F1 | exact cases | tiebreak uses (narrowed to one) | cadence uses (narrowed to one) |",
         "|---|---|---|---|---|---|---|",
         f"| 32 public samples (headline, golden answers) | {sc.n_cases} | {sc.status_correct}/{sc.n_cases} | {p:.3f} / {r:.3f} / {f:.3f} | "
         f"{sc.exact_cases}/{sc.n_cases} | {len(tb_s)} ({sum(u.resolved for u in tb_s)}) | {len(cd_s)} ({sum(len(u.after) == 1 for u in cd_s)}) |",
         f"| 518 evaluation requests (no golden answer; usage counts only) | {len(ev)} | n/a | n/a | n/a | {len(tb_e)} ({sum(u.resolved for u in tb_e)}) | "
         f"{len(cd_e)} ({sum(len(u.after) == 1 for u in cd_e)}) |", ""]
    L += [f"Verdicts on the 518 evaluation requests: COMPLETE {st['COMPLETE']}, INCOMPLETE {st['INCOMPLETE']}, "
          f"NOT_APPLICABLE {st['NOT_APPLICABLE']}.", ""]
    if unv:
        ok = sum(u["status_ok"] for u in unv)
        L += [f"Not accuracy either, because they are unverified: the 12 hand-derived image/PDF expectations "
              f"(`derived_cases.md`). Status matches {ok}/{len(unv)}; required steps found "
              f"{sum(u['found'] for u in unv)}/{sum(u['required'] for u in unv)}.", ""]
    return "\n".join(L)


def synthetic_block(c: dict) -> str:
    cs = c["custom"]["score"]
    ok = sum(1 for cid, (status, steps) in c["custom"]["world"].expected.items() if c["custom"]["pred"][cid] == (status, steps))
    return (f"| synthetic worlds | cases | reproduce their hand-derived answer exactly |\n|---|---|---|\n"
            f"| `custom_cases.py` | {cs.n_cases} | {ok}/{cs.n_cases} |\n")


def scorecard_block(c: dict) -> str:
    text = render_scorecard(c["sc"], "Headline: 32 sample cases")
    return text[: text.index("Every discrepancy")].rstrip() + "\n"


def residual_block(c: dict) -> str:
    full, ds = c["full"], c["ds"]
    ev = c["eval_ids"]
    acc = Counter(a.how for cid, a in full.assignments.items() if cid in ev)
    ana = Counter(a.how for cid, a in full.analytics.items() if cid in ev)
    nhide, nmatched = cadence_hide_population(ds)
    L = ["Accounts in the 518 evaluation requests that are not named by evidence (a deleted account leaves no identifier):", "",
         "| decided by | cases |", "|---|---|"]
    for k in ("evidence", "elimination", "tiebreak", "guess", "ambiguous", "none"):
        L.append(f"| {k} | {acc.get(k, 0)} |")
    L += ["", "Anonymized analytics profiles in the same set:", "", "| decided by | cases |", "|---|---|"]
    for k in ("elimination", "guess", "ambiguous"):
        L.append(f"| {k} | {ana.get(k, 0)} |")
    L += ["", f"Whole dataset (samples + evaluation): {nmatched} cases need an analytics profile that no evidence names.", ""]
    return "\n".join(L)


def policy_block(c: dict) -> str:
    return render_policy_value(policy_value(c["ds"]))


def switches_block(c: dict) -> str:
    ds, ev = c["ds"], c["eval_ids"]
    base = None
    L = ["| tiebreak | cadence | accounts guessed or omitted | analytics profiles guessed | steps that differ from the default run | verdicts that differ |",
         "|---|---|---|---|---|---|"]
    for tb in (True, False):
        for cd in (True, False):
            r = run(ds, ds.requests, PlanOptions(use_tiebreak=tb, use_cadence=cd))
            acc = sum(1 for i in ev if i in r.assignments and r.assignments[i].how in ("guess", "ambiguous", "none"))
            ana = sum(1 for i in ev if i in r.analytics and r.analytics[i].how == "guess")
            if base is None:
                base = r
            diff_steps = sum(1 for i in ev if r.results[i].steps != base.results[i].steps)
            diff_status = sum(1 for i in ev if r.results[i].status != base.results[i].status)
            L.append(f"| {'on' if tb else 'off'} | {'on' if cd else 'off'} | {acc} | {ana} | {diff_steps} cases | {diff_status} |")
    return "\n".join(L)


BLOCKS = {"results": results_table, "synthetic": synthetic_block, "scorecard": scorecard_block, "residual": residual_block, "policy": policy_block,
          "switches": switches_block}


def write_blocks(c: dict) -> None:
    text = REPORT.read_text(encoding="utf-8")
    for name, fn in BLOCKS.items():
        pat = re.compile(rf"(<!-- block:{name} -->\n).*?(<!-- /block:{name} -->)", re.S)
        if not pat.search(text):
            raise SystemExit(f"missing block marker {name} in {REPORT}")
        text = pat.sub(lambda m: m.group(1) + fn(c).rstrip() + "\n" + m.group(2), text)
    REPORT.write_text(text, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    c = collect()
    if args.write:
        write_blocks(c)
        print(f"updated {REPORT}")
    else:
        for name, fn in BLOCKS.items():
            print(f"--- {name}\n{fn(c)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
