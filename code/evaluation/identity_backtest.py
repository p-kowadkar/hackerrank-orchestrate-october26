"""Backtests of the residual identity matching, on cases whose resource is known from evidence.

Accounts: for every case whose account is established directly by evidence, hide that link (for the whole reported_at
cohort at once, which is the hard situation: cohort-mates are ambiguous together), run the matcher from the activity
stream alone, and compare with the evidence-established account. This yields many more data points than the 32
samples and uses no golden labels. It answers: how accurate is a guess when k candidates remain, and does the
last-resort status/worker-result tiebreak help?

Analytics: the same idea for the anonymized analytics profile. Cases whose compliant profile is tied to them by evidence
have that link hidden; the matcher then has to find it from worker events, with and without the worker-cadence
heuristic. Accuracy is reported by the number of candidates left before the cadence is applied.

Run: python3 code/evaluation/identity_backtest.py  (writes code/evaluation/residual_backtest.md)
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ghostaudit.data import Dataset                         # noqa: E402
from ghostaudit.paths import DATASET_DIR                    # noqa: E402
from ghostaudit.timeutil import parse                       # noqa: E402
from score import load_answers                              # noqa: E402
from ghostaudit.evidence import build_index                 # noqa: E402
from ghostaudit.identity import IdentityResolver            # noqa: E402
from ghostaudit.intent import DELETE, classify_text         # noqa: E402
from ghostaudit import model as m                           # noqa: E402
from llm.offline import offline_reader, run_replay as run   # noqa: E402
from ghostaudit.planner import PlanOptions, build_context, decisions_for, plan_case  # noqa: E402
from ghostaudit.residual import AccountMatcher              # noqa: E402


def backtest(ds: Dataset | None = None, use_tiebreak: bool = True, policy: str = "guess") -> dict:
    ds = ds or Dataset()
    resolver = IdentityResolver(ds.identities, ds.audit_log)
    index = build_index(ds, offline_reader())
    contexts = [build_context(index, resolver, r) for r in ds.all_requests if classify_text(r.request_text).label == DELETE]
    truth = {}
    for c in contexts:
        direct = sorted(r for r in c.direct if r.startswith("account_"))
        if len(direct) == 1:
            truth[c.request.case_id] = direct[0]
    cohorts = defaultdict(list)
    for c in contexts:
        if c.request.case_id in truth:
            cohorts[c.request.reported_at].append(c.request.case_id)
    stats = Counter()
    for cohort_time, ids in cohorts.items():
        saved = {}
        for c in contexts:                                            # hide the cohort's evidence links
            if c.request.case_id in ids:
                saved[c.request.case_id] = dict(c.direct)
                c.direct = {k: v for k, v in c.direct.items() if not k.startswith("account_")}
        matcher = AccountMatcher(ds.activity, index, resolver, policy, use_tiebreak)
        for cid in ids:                                               # an unresolved account has no ownership trail either
            matcher.owners.pop(truth[cid], None)
        out = matcher.assign(contexts)
        for c in contexts:
            if c.request.case_id in saved:
                c.direct = saved[c.request.case_id]
        for cid in ids:
            a = out[cid]
            ok = a.resource_id == truth[cid]
            k = len(a.candidates) if a.candidates else 0
            stats[(a.how, min(k, 4) if a.how in ("guess", "ambiguous") else 1, ok)] += 1
            stats[("cohort", min(len(ids), 3), ok)] += 1
    return {"stats": stats, "n": len(truth)}


def render(result: dict, title: str) -> str:
    stats, n = result["stats"], result["n"]
    L = [f"### {title}", "", f"Cases with an evidence-established account: {n}.", "",
         "| how it was decided | candidates left | cases | correct | accuracy |", "|---|---|---|---|---|"]
    keys = sorted({(h, k) for (h, k, _ok) in stats if h != "cohort"}, key=lambda t: (["elimination", "tiebreak", "guess", "none", "ambiguous"].index(t[0]), t[1]))
    for h, k in keys:
        good, bad = stats[(h, k, True)], stats[(h, k, False)]
        L.append(f"| {h} | {k if h in ('guess', 'ambiguous') else '-'}{'+' if k == 4 and h in ('guess', 'ambiguous') else ''} | {good + bad} | {good} | {good / max(good + bad, 1):.0%} |")
    L += ["", "By size of the hidden reported_at cohort (cohort-mates are ambiguous together):", "",
          "| cohort size | cases | resolved correctly (any method) |", "|---|---|---|"]
    for size in (1, 2, 3):
        good, bad = stats[("cohort", size, True)], stats[("cohort", size, False)]
        if good + bad:
            L.append(f"| {size}{'+' if size == 3 else ''} | {good + bad} | {good} ({good / (good + bad):.0%}) |")
    return "\n".join(L)


# ---------------------------------------------------------------------------- policy value, same scorer as the samples
def policy_value(ds: Dataset | None = None, policies=("omit", "hybrid", "guess")) -> dict:
    """What does each ambiguity policy cost or gain under the scorer's own definitions?

    The 255 cases whose account evidence establishes get a pseudo-golden answer: the plan built with the true account.
    The account link is then hidden (cohort by cohort), the case is re-planned under each policy, and the result is
    scored with `score.score`, the same function that scores the 32 samples. Only the account step can differ, so the
    numbers isolate exactly what the policy decides. The pseudo-golden is our own plan, not an organizer answer.
    """
    from score import score
    ds = ds or Dataset()
    resolver = IdentityResolver(ds.identities, ds.audit_log)
    base = run(ds, ds.all_requests, PlanOptions())
    index = base.index
    contexts = [build_context(index, resolver, r) for r in ds.all_requests if base.intents[r.case_id][0] == DELETE]
    truth, still_present = {}, 0
    for c in contexts:
        direct = sorted(r for r in c.direct if r.startswith("account_"))
        if len(direct) != 1:
            continue
        acct = [d for d in base.results[c.request.case_id].decisions if d.resource_id == direct[0]]
        if acct and acct[0].violating:          # a residual account is never observed, so it is never a present one
            still_present += 1
            continue
        truth[c.request.case_id] = direct[0]
    cohorts = defaultdict(list)
    for c in contexts:
        if c.request.case_id in truth:
            cohorts[c.request.reported_at].append(c)
    gold = {cid: (base.results[cid].status, base.results[cid].steps) for cid in truth}
    cards = {}
    for pol in policies:
        pred = {}
        for _time, group in cohorts.items():
            saved = {c.request.case_id: dict(c.direct) for c in group}
            for c in group:
                c.direct = {k: v for k, v in c.direct.items() if not k.startswith("account_")}
            matcher = AccountMatcher(ds.activity, index, resolver, pol)
            for c in group:
                matcher.owners.pop(truth[c.request.case_id], None)
            out = matcher.assign(contexts)
            for c in group:
                cid = c.request.case_id
                a = base.analytics.get(cid)
                extra = [a.resource_id] if a and a.resource_id else []
                r = plan_case(index, c, out[cid].resource_id, PlanOptions(ambiguity=pol), extra)
                pred[cid] = (r.status, r.steps)
            for c in group:
                c.direct = saved[c.request.case_id]
        cards[pol] = score(pred, gold)
    return {"cards": cards, "n": len(truth), "still_present": still_present}


def render_policy_value(result: dict) -> str:
    L = [f"Pseudo-golden = our own plan with the true account, {result['n']} evidence-established cases whose account is "
         f"verified absent ({result['still_present']} more are left out because the account is still present: a residual, "
         "unobserved account is never one), scored with `score.score` (the sample scorer). Only the account step can differ.", "",
         "| policy | status acc | step P / R / F1 | field step_no | field resource_id | seq overlap | positional | exact cases |",
         "|---|---|---|---|---|---|---|---|"]
    for pol, sc in result["cards"].items():
        p, r, f = sc.step_prf()
        fld = lambda k: f"{sc.field_hits[k] / max(sc.field_total[k], 1):.3f}"   # noqa: E731
        L.append(f"| {pol} | {sc.status_correct}/{sc.n_cases} | {p:.3f} / {r:.3f} / {f:.4f} | {fld('step_no')} | "
                 f"{fld('resource_id')} | {sc.lcs_sum / max(sc.n_cases, 1):.3f} | {sc.pos_hits / max(sc.pos_total, 1):.3f} | "
                 f"{sc.exact_cases}/{sc.n_cases} |")
    return "\n".join(L)


# ----------------------------------------------------------------------------------------------- analytics
def _golden_analytics(path: Path) -> dict:
    gold = load_answers(path)
    return {cid: {st["resource_id"] for st in steps if st["resource_id"].startswith("analytics_")}
            for cid, (_status, steps) in gold.items()}


def cadence_hide_population(ds: Dataset) -> tuple:
    """Hiding evidence links needs a case whose compliant, identifier-free profile evidence links. Count them."""
    resolver = IdentityResolver(ds.identities, ds.audit_log)
    base = run(ds, ds.all_requests, PlanOptions())
    n = 0
    for r in ds.all_requests:
        if base.intents[r.case_id][0] != DELETE:
            continue
        c = build_context(base.index, resolver, r)
        decs = decisions_for(base.index, c, base.assignments[r.case_id].resource_id)
        n += any(d.rtype == m.ANALYTICS and not d.violating for d in decs)
    return n, len(base.analytics)


def cadence_sample_backtest(ds: Dataset, policy: str = "hybrid") -> dict:
    """Truth = the analytics profile in the golden answer of the COMPLETE sample cases (the only compliant profiles whose
    owner is known). Per case: candidates before cadence, how it was decided, right or wrong, with cadence on and off."""
    gold = _golden_analytics(DATASET_DIR / "sample_output.csv")
    out = {}
    for flag in (True, False):
        res = run(ds, ds.all_requests, PlanOptions(ambiguity=policy, use_cadence=flag))
        rows = []
        for cid, rids in sorted(gold.items()):
            a = res.analytics.get(cid)
            if not rids or a is None:                          # INCOMPLETE cases list the exposed profile; not this matcher
                continue
            before, after = res.analytics_trace.get(cid, (0, 0))
            rows.append((cid, before, after, a.how, a.resource_id in rids))
        out[flag] = {"rows": rows, "guesses_all": sum(1 for a in res.analytics.values() if a.how == "guess"),
                     "uses": len(res.cadence_uses), "gaps": sorted(res.cadence)}
    return out


def cadence_premise(ds: Dataset) -> dict:
    """Does the worker really space a case's resources by a fixed alternating gap? Checked on evidence-linked resources
    only: gaps between consecutive linked resources' worker events, and the gap before an evidence-linked analytics profile."""
    res = run(ds, ds.all_requests, PlanOptions())
    ev = defaultdict(list)
    for r in ds.activity:
        if r["source_system"] == "deletion_worker":
            ev[r["resource_id"]].append(r["event_time"])
    reqs = {r.case_id: r for r in ds.all_requests}
    pair_gaps, analytics_gaps = Counter(), Counter()
    for cid, result in res.results.items():
        rep = reqs[cid].reported_at
        items = []
        for d in result.decisions:
            if d.resource_id.startswith("account_") or d.resource_id not in ev:
                continue
            t = min(ev[d.resource_id], key=lambda x: abs(parse(x) - parse(rep)))
            if abs((parse(t) - parse(rep)).total_seconds()) <= 7200:
                items.append((t, d.resource_id))
        items.sort()
        for (t0, _r0), (t1, r1) in zip(items, items[1:]):
            gap = int((parse(t1) - parse(t0)).total_seconds())
            pair_gaps[gap] += 1
            if r1.startswith("analytics_"):
                analytics_gaps[gap] += 1
    return {"pairs": pair_gaps, "analytics": analytics_gaps}


def render_cadence(ds: Dataset) -> str:
    n_hide, n_matched = cadence_hide_population(ds)
    L = ["### Cadence heuristic: what can be backtested", "",
         f"- Hiding evidence links (as for accounts) is **not possible**: {n_hide} cases have a compliant, identifier-free "
         "analytics profile that evidence links to them. An anonymized profile carries no identifier, so evidence never "
         f"links it; that is why the matcher exists ({n_matched} cases are matched by it).",
         "- The only ground truth for these profiles is the golden answers of the COMPLETE sample cases, reported below. "
         "It is a small sample, so read the accuracy as 'no failure observed', not as a rate.", ""]
    for pol in ("hybrid", "guess"):
        bt = cadence_sample_backtest(ds, pol)
        L += [f"#### Sample truth, policy {pol}", "",
              "| candidates before cadence | cadence | cases | right | decided by |", "|---|---|---|---|---|"]
        for flag in (True, False):
            rows = bt[flag]["rows"]
            for k in sorted({r[1] for r in rows}):
                sel = [r for r in rows if r[1] == k]
                how = Counter(r[3] for r in sel)
                L.append(f"| {k} | {'on' if flag else 'off'} | {len(sel)} | {sum(r[4] for r in sel)} | "
                         f"{', '.join(f'{v} {h}' for h, v in sorted(how.items()))} |")
        L += ["", f"Whole dataset (samples + eval): analytics guesses with cadence on {bt[True]['guesses_all']}, "
                  f"off {bt[False]['guesses_all']}; cadence narrowed {bt[True]['uses']} cases; learned gaps {bt[True]['gaps']}.", ""]
    prem = cadence_premise(ds)
    top = prem["pairs"].most_common(5)
    tot = sum(prem["pairs"].values())
    top4 = sum(v for _g, v in prem["pairs"].most_common(4))
    ana = prem["analytics"]
    L += ["#### Premise check on evidence-linked resources (no hidden links, no analytics guessing)", "",
          f"- Consecutive worker events of a case's linked resources: {tot} pairs; the four most common gaps "
          f"{[g for g, _v in prem['pairs'].most_common(4)]} s cover {top4} of them (top five with counts: {top}).",
          f"- Evidence-linked analytics profiles with a linked predecessor: {sum(ana.values())}; gap distribution "
          f"{ana.most_common(5)}. These profiles sit in the same alternating-gap pattern, which is the premise the "
          "cadence heuristic relies on.", ""]
    return "\n".join(L)


def main() -> None:
    ds = Dataset()
    parts = ["# Residual identity backtests (generated by `python3 code/evaluation/identity_backtest.py`)", "",
             "Evidence-established links are hidden and recovered from the activity stream alone. No golden answer is used.", "",
             "## Accounts", "",
             render(backtest(ds, True), "with the status/worker-result tiebreak, policy guess"), "",
             render(backtest(ds, False), "without the tiebreak, policy guess"), "",
             render(backtest(ds, True, "hybrid"), "with the tiebreak, policy hybrid (guess only with <= 2 candidates)"), "",
             render(backtest(ds, True, "omit"), "with the tiebreak, policy omit"), "",
             "### Policy value under the sample scorer", "", render_policy_value(policy_value(ds)), "",
             "## Anonymized analytics profiles (worker-cadence heuristic)", "",
             render_cadence(ds), ""]
    text = "\n".join(parts)
    print(text)
    (Path(__file__).resolve().parent / "residual_backtest.md").write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
