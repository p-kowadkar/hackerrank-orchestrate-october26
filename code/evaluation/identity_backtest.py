"""Backtest of the residual identity matching on cases whose account is known from evidence.

For every case whose account is established directly by evidence, hide that link (for the whole reported_at cohort
at once, which is the hard situation: cohort-mates are ambiguous together), run the matcher from the activity stream
alone, and compare with the evidence-established account. This yields many more data points than the 32 samples and
uses no golden labels. It answers: how accurate is a guess when k candidates remain, and does the last-resort
status/worker-result tiebreak help?
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ghostaudit.data import Dataset                         # noqa: E402
from ghostaudit.evidence import build_index                 # noqa: E402
from ghostaudit.identity import IdentityResolver            # noqa: E402
from ghostaudit.intent import DELETE, classify_text         # noqa: E402
from ghostaudit.planner import build_context                # noqa: E402
from ghostaudit.residual import AccountMatcher              # noqa: E402


def backtest(ds: Dataset | None = None, use_tiebreak: bool = True, policy: str = "guess") -> dict:
    ds = ds or Dataset()
    resolver = IdentityResolver(ds.identities, ds.audit_log)
    index = build_index(ds)
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
        matcher = AccountMatcher(ds.activity, index, resolver, policy)
        for cid in ids:                                               # an unresolved account has no ownership trail either
            matcher.owners.pop(truth[cid], None)
        if not use_tiebreak:
            import ghostaudit.residual as residual
            original = residual.STATUS_RESULT
            residual.STATUS_RESULT = {}
        out = matcher.assign(contexts)
        if not use_tiebreak:
            residual.STATUS_RESULT = original
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


if __name__ == "__main__":
    ds = Dataset()
    print(render(backtest(ds, True), "with the status/worker-result tiebreak, policy guess"))
    print()
    print(render(backtest(ds, False), "without the tiebreak, policy guess"))
    print()
    print(render(backtest(ds, True, "hybrid"), "with the tiebreak, policy hybrid (guess only with <= 2 candidates)"))
    print()
    print(render(backtest(ds, True, "omit"), "with the tiebreak, policy omit"))
