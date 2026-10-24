"""Human-readable run report (Markdown). Contains counts and ids only, never evidence payloads."""
from __future__ import annotations

from collections import Counter

from .pipeline import RunResult


def run_report(run: RunResult, title: str = "Run report") -> str:
    lines = [f"# {title}", ""]
    st = Counter(r.status for r in run.results.values())
    lines += ["## Verdicts", ""] + [f"- {k}: {v}" for k, v in sorted(st.items())] + [""]
    how = Counter(a.how for a in run.assignments.values())
    lines += ["## Account identity (all deletion cases used as matching context)", ""]
    lines += [f"- resolved by {k}: {v}" for k, v in sorted(how.items())]
    lines += ["", f"Ambiguity policy: `{run.options.ambiguity}`. "
              "`guess` = deterministic pick among candidates; `ambiguous` = step omitted.", ""]
    uses = run.tiebreak_uses
    lines += ["## Status/worker-result tiebreak uses (last resort)", "",
              f"- uses: {len(uses)}; narrowed to one account: {sum(1 for u in uses if u.resolved)}; "
              f"narrowed but still tied: {sum(1 for u in uses if not u.resolved)}", ""]
    if uses:
        lines += ["| case | candidates before | after | resolved |", "|---|---|---|---|"]
        lines += [f"| {u.case_id} | {', '.join(u.before)} | {', '.join(u.after)} | {'yes' if u.resolved else 'no'} |" for u in uses]
        lines.append("")
    ahow = Counter(a.how for a in run.analytics.values())
    lines += ["## Anonymized analytics identity (no identifier in evidence)", ""]
    lines += [f"- resolved by {k}: {v}" for k, v in sorted(ahow.items())] or ["- none needed"]
    cuses = run.cadence_uses
    lines += ["", "## Worker-cadence heuristic uses", "",
              f"- learned gaps (seconds): {', '.join(str(g) for g in sorted(run.cadence)) or 'none'}",
              f"- uses: {len(cuses)}; narrowed to one profile: {sum(1 for u in cuses if len(u.after) == 1)}", ""]
    if cuses:
        lines += ["| case | candidates before | after |", "|---|---|---|"]
        lines += [f"| {u.case_id} | {', '.join(u.before)} | {', '.join(u.after)} |" for u in cuses]
        lines.append("")
    tot = Counter()
    for fid, c in run.index.stats.items():
        tot.update(c)
    lines += ["## Evidence parsing", "",
              f"- observations: {len(run.index.obs)}; records parsed: {tot['parsed']}; noise events ignored: {tot['ignored']}; "
              f"unrecognised: {tot['unknown']}; files skipped (screenshots): {tot['skipped']}", ""]
    if run.warnings:
        lines += ["## Warnings", ""] + [f"- {w}" for w in run.warnings] + [""]
    return "\n".join(lines)
