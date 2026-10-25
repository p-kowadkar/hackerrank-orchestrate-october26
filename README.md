# HackerRank Orchestrate - October 2026

## Ghost Data Still Exists

Build an AI agent that audits whether a user's personal data was actually deleted.

A deletion workflow may report **Complete** while data still exists in databases, logs, support attachments, exports, search indexes, archives, or backups. Sync and restore processes may also bring deleted data back.

For each request, the agent must first determine whether deletion was actually requested. It then returns `COMPLETE`, `INCOMPLETE`, or `NOT_APPLICABLE`, reports any remaining data or recreation risk, and produces the ordered remediation and verification steps required to finish an authorized deletion safely.

Read [`problem_statement.md`](./problem_statement.md) for the complete challenge contract.

---

## Quick Start

Clone the repository and move into the project directory:

```bash
git clone https://github.com/interviewstreet/hackerrank-orchestrate-october26.git
cd hackerrank-orchestrate-october26
```

Start your AI coding tool from the **repository root** so it automatically reads [`AGENTS.md`](./AGENTS.md) and logs your session turns to `log.txt` in the root directory.

Build your solution in `code/main.py`, or use another language and document its setup and run command clearly in your README.

Your solution must:

- Read the input files from `dataset/`
- Generate one prediction row for every request in `dataset/deletion_requests.csv`
- Write the final predictions to `output.csv` in the repository root

Run the starter Python entry point with:

```bash
python3 code/main.py
```

The blank template at `dataset/output.csv` is provided as a reference. Your final generated file for submission must be the root-level `output.csv`.


## Running this solution

Requirements: Python 3.9+ and one small dependency (`pypdf`, pure Python, used to read the four PDFs).

```bash
pip install -r code/requirements.txt
python3 code/main.py                       # reads dataset/, writes output.csv (518 rows) at the repository root
python3 code/evaluation/main.py            # scores the 32 samples, writes code/evaluation/sample_scorecard.md
python3 -m unittest discover -s code/tests -t code     # offline test suite
```

Options and evaluation tools (all offline):

```bash
python3 code/main.py --ambiguity hybrid|guess|omit     # what to do when an account stays ambiguous (default hybrid)
python3 code/main.py --no-tiebreak --no-cadence        # switch off the two dataset-specific heuristics
python3 code/evaluation/custom_cases.py                # hand-built evaluation cases -> custom_cases_results.md
python3 code/evaluation/coverage.py                    # per-format coverage and consistency -> coverage_report.md
python3 code/evaluation/identity_backtest.py           # backtests of the residual matching -> residual_backtest.md
python3 code/evaluation/results_table.py --write       # refreshes the tables in evaluation_report.md
```

The two heuristics (`reported_status` against worker result, and the worker cadence for anonymized analytics profiles)
exploit how this dataset was built, are only ever used after evidence has failed to decide, and are counted in
`code/evaluation/run_report.md`; `code/evaluation/evaluation_report.md` section 6 describes and backtests them.

On Windows use `py -3` instead of `python3`; nothing here depends on bash. Paths are resolved from the location
of the code, so any checkout folder name works.

`output.csv` rows are in natural numeric order of `case_id` (`case_33` before `case_100`, the order of
`deletion_requests.csv`). The brief says "sorted by case_id" without defining the order, so this is a stated
assumption.

How it works, in one paragraph: identity resolution (current and historical emails, hashes, phones) -> request
intent (multilingual, negation-aware) -> every evidence file is parsed once into time-stamped observations ->
resources are linked to the case through identity tokens inside a time window -> the state of each resource at
`audit_at` is the newest admissible observation (a file or a record dated after `audit_at` is never used; claims in
`system_activity.csv` are hints, never proof) -> `deletion_rules.csv` maps each record type to its action -> steps
are ordered and cited deterministically. Design notes, the evidence catalogue and the sprint plan are in
`code/notes/`. Reports are in `code/evaluation/`.

LLM use and API keys: two steps may use a model, both through one interface in `code/llm/` (`off`, `replay`, `live`,
`record`): reading the 11 application screenshots, and a fallback for request texts the rule-based classifier cannot place
(it fires for none of the 518). `python3 code/main.py` defaults to `--llm replay`: offline, deterministic, no key; the
screenshots are then read from stored transcriptions made by hand (`code/llm/fixtures/transcribed/`, labelled
`transcribed`, no usage numbers). Live calls are opt-in and refused unless all three are given:

```bash
export OPENROUTER_API_KEY=...            # a real key; outside the development sandbox this is required
python3 code/main.py --llm live --model <openrouter-model-id> --confirm-live
python3 code/llm/compare.py              # model readings against the transcriptions, writes screenshot_agreement.md
```

The key is read only from the environment (a placeholder is used when it is unset, and the placeholder is refused); it is
never written anywhere. Every real response is appended to `code/evaluation/usage_ledger.md` with the tokens and cost the
provider reported, and `python3 code/main.py` regenerates `code/evaluation/run_manifest.md` and `usage_report.md` together with
`output.csv`, so the usage report always describes the run that produced the output file. Request texts sent to a model in
`live` mode contain whatever personal data the request itself contains. Prompts are Markdown files in `code/prompts/`.

## Dataset

All participant-facing files are in `dataset/`:

| File | Contents |
| --- | --- |
| `deletion_requests.csv` | 518 requests |
| `sample_deletion_requests.csv` | 32 sample requests |
| `sample_output.csv` | Correct sample answers |
| `user_identities.csv` | Current user identities |
| `user_audit_log.csv` | Historical identity changes |
| `system_activity.csv` | Activity across services and data processes |
| `deletion_rules.csv` | Required treatment for each data category |
| `evidence_files.csv` | Manifest of supplied evidence files |
| `output.csv` | Blank output template |

Evidence is stored under `dataset/evidence/` and may include PDFs, images, logs, JSON, plain text, or SQL snapshot exports. SQL captures may contain a primary database, regional replicas, a reporting replica, or a failover replica so replication drift can be investigated directly. The `.sql` files are readable as text and executable with SQLite.

Only `deletion_requests.csv` requires answers. The other files provide evidence and context.

---

## Output

Create `output.csv` with these columns in this exact order:

```text
case_id,deletion_status,steps_json
```

Produce exactly one row per request. `deletion_status` is `COMPLETE`, `INCOMPLETE`, or `NOT_APPLICABLE`. `steps_json` is an ordered JSON array containing findings, remediation actions, and verification checks. Use an empty array (`[]`) for `NOT_APPLICABLE`. Evidence references may be a `file_id`, `activity_id`, or `audit_id`. Determine the resource state at `audit_at` from the available evidence; reported workflow statuses and operation results are claims. Use `dataset/sample_output.csv` as the format reference.

The final file must contain 518 data rows sorted by `case_id` (plus the header row). The grader parses `steps_json` as JSON, so object-key order and whitespace do not matter; array order does. Order findings, remediation, and verification in that phase order. Within a phase, follow the operation order in the problem statement, then sort by `system_id` and `resource_id`.

---

## Evaluation

`output.csv` will be compared with hidden canonical answers. Scoring considers:

- deletion assessment accuracy;
- current and historical identity resolution;
- discovery of remaining data and recreation risks;
- correct policy application and evidence references; and
- completeness and ordering of remediation and verification steps.

Your `code.zip` must include:

```text
code/evaluation/evaluation_report.md
code/evaluation/usage_report.md
```

- `evaluation_report.md` must cover case, row, field, and sequence accuracy, at least three additional evaluation cases created by you, failures found, and improvements made.
- `usage_report.md` must cover the final full-dataset run, including model providers and names, model calls, input and output tokens, total and average tokens per request, and estimated total and per-request cost. Include per-model and overall totals when using multiple models.

**Important:** Place `evaluation_report.md` and `usage_report.md` inside `code/evaluation/` (matching `code/evaluation/main.py` in this starter layout), write your complete evaluation metrics, custom evaluation test cases, and token/cost breakdowns directly inside those Markdown files, and keep prompts in source code or Markdown files. Automated code evaluation ignores raw data files (`.csv`, `.tsv`, `.json`, `.jsonl`, `.sql`, `.log`), so content stored only in those formats will not be visible to the code judge or AI interviewer.

---

## Chat Transcript

This repository includes [`AGENTS.md`](./AGENTS.md), which instructs compatible AI coding tools to append conversation summaries to `log.txt` in the repository root:

| Platform | Path |
| --- | --- |
| macOS / Linux | `<repo root>/log.txt` |
| Windows | `<repo root>\log.txt` |

- Always launch your AI coding agent from the repository root (or explicitly ask it to read `./AGENTS.md` first) so every turn is logged to `log.txt` with the required `User Prompt`, `Agent Response Summary`, `Actions`, and `Context` sections.
- Upload `log.txt` directly as your `chat_transcript` submission on HackerRank.
- Do not include API keys, tokens, credentials, or secrets in prompts, code, configuration, or `log.txt`.

---

## Packaging `code.zip` and Submission

| Item | Description |
| --- | --- |
| `code.zip` | Runnable solution, prompts, configuration, `README.md`, and `evaluation/` reports |
| `output.csv` | One answer row for each of the 518 requests in `dataset/deletion_requests.csv` |
| `chat_transcript` | The root `log.txt` file generated by your coding agent |
| AI interview | Live explanation of your architecture, approach, and evaluation |

You may use any programming language, model, framework, or retrieval approach. Include clear setup and execution instructions in `README.md` inside `code.zip`.

To package `code.zip` from the repository root without bundling the dataset:

**macOS / Linux:**

```bash
zip -r code.zip README.md code -x "*/__pycache__/*" "*/.venv/*" "*/venv/*" "*/node_modules/*" "*/.git/*" "*/.DS_Store"
```

**Windows (PowerShell):**

```powershell
Compress-Archive -Path README.md, code -DestinationPath code.zip -Force
```

When packaging `code.zip`:

- Keep your evaluation reports in `code/evaluation/` so they are bundled automatically with `code` (or add `evaluation` to the archive command above if you placed them in a top-level `evaluation/` directory).
- Do **not** include `dataset/`, virtual environments (`.venv`, `venv`, `node_modules`), or build caches (`__pycache__`). On Windows, keep `.venv` at the repository root (outside `code/`) and remove any `code/__pycache__` folders before running `Compress-Archive`.
- Do **not** include nested archives (`.zip`, `.tar`, `.gz`, `.tgz`, `.7z`, `.rar`) inside `code.zip` — submissions containing nested archive files will be rejected.

Before submitting, confirm that:

- `output.csv` has the exact header `case_id,deletion_status,steps_json` and contains all 518 data rows sorted by `case_id`;
- every `steps_json` value is a valid JSON array with consecutive step numbers starting at `1`;
- findings cite valid evidence IDs, and `COMPLETE` verification steps cite evidence proving the current state;
- proposed remediation and future verification steps use an empty `evidence_id` (`""`);
- `code.zip` includes your runnable code, `README.md`, `code/evaluation/evaluation_report.md`, and `code/evaluation/usage_report.md`;
- `log.txt` follows the `AGENTS.md` turn format and is uploaded to the `chat_transcript` slot; and
- no API keys, credentials, real personal data, or sensitive configuration values are included.
