"""Run the deletion audit: python3 code/main.py

Reads dataset/, writes output.csv at the repository root (and a run report next to the evaluation reports).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ghostaudit.data import Dataset                                  # noqa: E402
from ghostaudit.output import validate_output, write_output          # noqa: E402
from ghostaudit.paths import CODE_DIR, DATASET_DIR, DEFAULT_OUTPUT   # noqa: E402
from ghostaudit.pipeline import run                                  # noqa: E402
from ghostaudit.planner import PlanOptions                           # noqa: E402
from ghostaudit.report import run_report                             # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", type=Path, default=DATASET_DIR)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument("--report", type=Path, default=CODE_DIR / "evaluation" / "run_report.md")
    ap.add_argument("--ambiguity", choices=("guess", "omit", "hybrid"), default="hybrid",
                    help="what to do when an account stays ambiguous after evidence, elimination and tiebreak")
    ap.add_argument("--no-cadence", action="store_true",
                    help="do not use the learned worker cadence to link anonymized analytics profiles")
    ap.add_argument("--no-tiebreak", action="store_true",
                    help="do not use the reported_status <-> worker-result tiebreak for unresolved accounts")
    args = ap.parse_args(argv)
    ds = Dataset(args.dataset)
    res = run(ds, ds.requests, PlanOptions(ambiguity=args.ambiguity, use_cadence=not args.no_cadence,
                                       use_tiebreak=not args.no_tiebreak))
    write_output(args.out, res.results)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(run_report(res), encoding="utf-8")
    problems = validate_output(args.out, ds.requests, ds.manifest)
    print(f"wrote {args.out} ({len(res.results)} rows); structural problems: {len(problems)}")
    for p in problems[:20]:
        print("  -", p)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
