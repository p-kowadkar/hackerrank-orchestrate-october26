"""Run the deletion audit: python3 code/main.py

Reads dataset/, writes output.csv at the repository root, a run report, and (for the default output path) the run manifest and
the usage report of the run. The model-backed steps (screenshots, unclear request texts) go through code/llm/:

  --llm replay   (default) stored fixtures only: offline, deterministic, no key. Screenshots come from the hand transcriptions.
  --llm off      no model and no fixtures: screenshots stay unread.
  --llm live     real OpenRouter calls (needs OPENROUTER_API_KEY, --model, and --confirm-live); every response is ledgered.
  --llm record   like live, and also stores each answer as a `recorded` fixture; keys that already have one are not paid twice.
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
from llm.factory import MODES, make_backend, new_run_id              # noqa: E402
from llm.fixtures import FIXTURE_ROOT                                # noqa: E402
from llm.manifest import build_manifest, write_run_artifacts         # noqa: E402
from llm.reader import IntentFallback, ScreenshotReader              # noqa: E402
from llm.usage import Ledger                                         # noqa: E402


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
    ap.add_argument("--llm", choices=MODES, default="replay", help="how the model-backed steps are served (default: replay)")
    ap.add_argument("--fixtures", type=Path, default=FIXTURE_ROOT, help="root of the llm fixtures")
    ap.add_argument("--replay-origins", choices=("transcribed", "recorded", "both"), default="transcribed",
                    help="which fixtures replay may use (default: the hand transcriptions only)")
    ap.add_argument("--model", default=None, help="OpenRouter model id for live/record (or set GHOSTAUDIT_MODEL)")
    ap.add_argument("--confirm-live", action="store_true", help="required for --llm live/record: real, billable API calls")
    args = ap.parse_args(argv)
    if args.llm in ("live", "record") and not args.confirm_live:
        ap.error("--llm live/record makes real, billable API calls: add --confirm-live once the owner has confirmed the key")
    ds = Dataset(args.dataset)
    ledger = Ledger()
    run_id = new_run_id(args.llm)
    origins = ("transcribed", "recorded") if args.replay_origins == "both" else (args.replay_origins,)
    backend = make_backend(args.llm, fixtures=args.fixtures, replay_origins=origins, model=args.model, ledger=ledger, run_id=run_id)
    reader, fallback = ScreenshotReader(backend), IntentFallback(backend)
    res = run(ds, ds.requests, PlanOptions(ambiguity=args.ambiguity, use_cadence=not args.no_cadence,
                                       use_tiebreak=not args.no_tiebreak), images=reader, intent_fallback=fallback)
    if args.llm in ("live", "record") and reader.unread:
        print("refusing to write an output: live/record mode left screenshots unread, so the answer would not match what the usage "
              "report describes:")
        for fid, why in reader.unread:
            print(f"  screenshot {fid}: {why}")
        return 3
    write_output(args.out, res.results)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(run_report(res), encoding="utf-8")
    problems = validate_output(args.out, ds.requests, ds.manifest)
    print(f"wrote {args.out} ({len(res.results)} rows); structural problems: {len(problems)}")
    for fid, why in reader.unread + reader.problems:
        print(f"  screenshot {fid}: {why}")
    if Path(args.out).resolve() == DEFAULT_OUTPUT.resolve():           # only the submission file gets a manifest and usage report
        unclear = sum(1 for w in res.warnings if "intent unclear" in w)
        manifest = build_manifest(command=("python3 code/main.py " + " ".join(argv if argv is not None else sys.argv[1:])).strip(),
                                  output_path=args.out, n_rows=len(res.results), mode=args.llm,
                                  replay_origins=args.replay_origins, run_id=run_id, model=args.model or "",
                                  reader=reader, fallback=fallback, unclear_texts=unclear, ledger=ledger, repo_root=DEFAULT_OUTPUT.parent)
        write_run_artifacts(manifest, ledger)
    for p in problems[:20]:
        print("  -", p)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
