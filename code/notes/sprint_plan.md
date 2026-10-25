# Sprint plan (prioritized, each sprint ends in a tested deliverable)

## Standing decisions (approved)
1. **Identity-resolution tiebreak.** The `reported_status` <-> worker-result agreement is a last-resort tiebreaker
   for unresolved resource identity only. It never overrides evidence and is never applied when evidence or
   elimination already decides. If it would remove every candidate it is ignored. Every use is counted and
   listed in the run report and the evaluation report.
2. **No `account_00N` naming convention.** An account id must come from evidence or from a worker event.
3. **Ambiguous resources: guess versus omit** is decided by a backtest on the 32 samples. The criterion is fixed
   before the run: step-level F1 on the samples, ties broken by case-level exact matches, then by fewer wrong steps.
   The winner becomes the default; the other stays available behind `--ambiguity`.
4. **Evaluation integrity.** Headline accuracy uses only `dataset/sample_output.csv`. The 12 hand-derived
   image/PDF answers live in `code/evaluation/derived_cases.md`, are scored in a separate section labelled
   "unverified", and never enter the headline numbers. The production pipeline never reads
   `sample_output.csv`; only the scorer does (a test enforces that).
5. **No LLM output, token count or cost is ever invented.** Only real API responses create usage rows.
6. **Documents ship in `code.zip`:** everything under `code/` (notes, design, reports).
7. **Row order.** `output.csv` rows are in natural numeric order of `case_id` (`case_33` before `case_100`, the
   order of `deletion_requests.csv`). The brief says "sorted by case_id" without saying how, and unpadded ids
   sort differently as strings. This is a flagged assumption.

## Priorities (why this order)
Expected score gain per unit of work: about 69% of eval cases sit in formats with sample truth, so they go first;
about 31% sit in eight format variants with none, which is the next biggest block; the 12 image/PDF cases are 2%
of the set; reports and packaging are mandatory but cheap once the numbers exist.

## Sprint 1: scorer, deterministic core, valid output (first milestone)
Deliverables:
- `code/evaluation/score.py` + `code/evaluation/main.py`: status accuracy, step-level exact match and F1,
  per-field accuracy, sequence accuracy, and a per-case discrepancy list with a root-cause tag.
- `code/ghostaudit/`: loaders, identity resolver, intent classifier, evidence parsers for every format, linking,
  state resolution (clock rules), policy, planner, citation, output writer, run report.
- `python3 code/main.py` writes a valid 518-row `output.csv` at the repo root.
- Offline tests (`python3 -m unittest discover -s code/tests`).
Acceptance:
- Scorer gives 100% to `sample_output.csv` against itself and drops the right metric under perturbation.
- 550/550 request emails resolve to a user; the intent classifier labels exactly 10 eval cases NOT_APPLICABLE.
- Every state-bearing event/record in the 78 text-like evidence files parses (no silent drops).
- `output.csv`: exact header, 518 rows, valid JSON arrays, consecutive step numbers, evidence-id rules, phase and
  operation ordering, deterministic bytes across two runs.
- A sample scorecard that lists every discrepancy with its cause.

## Order after the Sprint 1 review
Sprint 3 first (done), then the remaining sample-fidelity cleanup (Sprint 2), then Sprint 4. Reports
(`evaluation_report.md`, `usage_report.md`) are started and extended in every sprint. `case_04`, `case_18` and `case_20`
are documented as unrecoverable (their ids appear in no participant file) and are not worked on.

## Sprint 2: sample fidelity and the ambiguity policy
- Fix every discrepancy that is fixable from participant data; keep the rest, each with a documented cause.
- Anonymized-analytics matching and the remaining residual-id cases.
- Run the guess-versus-omit backtest and set the default.
Deliverable: sample scorecard where each remaining discrepancy is classed as unfixable (id absent from all data,
or genuinely ambiguous) or as an open question; tiebreak-use counts.

## Sprint 3: eval-only format hardening (DONE: coverage_report.md, test_variants.py, custom_cases.py, 12 hand-built cases)
- Reporting, regional and failover-generic replicas; pipe, bracket, syslog, JSON-line and cloud-runtime log
  dialects; ledger-style bundles; legal holds; DELETION_PENDING; expiry handling.
- Cross-format consistency checks (the same user and resource read through different formats agree).
- At least three additional evaluation cases built by hand from data we can verify structurally.
Deliverable: coverage report (per format: files, records, observations, unparsed lines = 0) and consistency tests.

## Sprint 4: LLM interface, screenshots and the 12 image/PDF cases
- `code/llm/` with replay/live/record/off backends, prompts as Markdown, Markdown fixtures, usage ledger.
- Screenshot reader and fixtures transcribed from `evidence_artifacts.md` (labelled `transcribed`, no usage).
- Intent fallback behind the same interface (expected to fire rarely).
Deliverable: the 12 cases run offline; separate "unverified derived" report; tests prove replay never fabricates and
transcribed fixtures never carry usage.

## Sprint 5: live OpenRouter (needs the key)
- Live backend; `record` mode regenerates the 11 screenshot fixtures from a real model; usage ledger filled only from
  API responses; agreement report between model transcription and my hand transcription.
Deliverable: ledger checked against real responses; if the network is still blocked, this sprint is skipped and the
usage report states that no live run happened.

## Sprint 6: reports, README, packaging
- `evaluation_report.md` (headline on samples, unverified section, discrepancy list, failures found and fixes,
  tiebreak counts, guess-versus-omit result), `usage_report.md` from real calls only, README with setup/run and the
  statement that a real key is needed outside this sandbox, `code.zip` dry run, final `output.csv`.
Deliverable: packaged zip passes a structural check (no dataset, no secrets, no nested archives, reports present).
