# Architecture proposal (design only, nothing built yet)

## Principles
1. Decisions are deterministic: identity, linking, state at `audit_at`, policy, ordering, JSON.
2. An LLM only *perceives* (reads a screenshot, classifies ambiguous request text). It never
   decides a verdict, never invents an id, and its output is schema-validated and cross-checked.
3. Every LLM step sits behind one small interface, so the whole system runs offline today against
   stored sample responses and against OpenRouter once a key exists. No code outside `code/llm/`
   knows which backend answered.
4. Token counts and costs come only from real API responses. Replayed or hand-written responses carry
   no usage and are excluded from every usage total.

## What I would challenge in the first plan
- **PDFs need no LLM.** All four extract with `pdftotext`. That leaves 11 screenshots.
- **Intent classification is mostly a lookup.** 508 of 518 texts are templated deletion language in six
  languages; the 10 non-deletion ones are also backed by `CLASSIFY_REQUEST` events. The LLM is the
  fallback for text the lexicon cannot place, not the main path.
- **The hard part is not LLM-shaped.** It is entity matching and time handling (which resource belongs
  to which case, what was true at `audit_at`). An LLM cannot recover an id that is not in the data.
- Everything else in the original bias stands: scorer first, evidence parsed once, small sprints.

## The LLM interface (`code/llm/`)

Two steps use it. Both are listed so nothing hides behind a third path.

| step | input | output (JSON schema, validated) | used for |
|---|---|---|---|
| `screenshot_transcribe` | one PNG | `{app, title, subject{resource_id, fields}, rows[{resource_id?, label, fields}], notes}` | the 11 UI screenshots |
| `intent_classify` | one `request_text` | `{label: DELETE / NON_DELETE / UNCLEAR, language, cue}` | text the lexicon cannot place |

```python
@dataclass(frozen=True)
class LLMRequest:
    step: str                 # "screenshot_transcribe" | "intent_classify"
    input_ref: str            # "evidence_09" | "case_539"
    input_sha: str            # sha256 of the PNG bytes or the text
    schema_version: int       # bump when the output schema changes
    system: str; user: str    # rendered from code/prompts/<step>.md
    images: tuple[Path, ...] = ()

@dataclass
class Usage:                  # filled ONLY from an API response
    prompt_tokens: int | None
    completion_tokens: int | None
    cost_usd: float | None    # provider-reported; None when not reported

@dataclass
class LLMResult:
    data: dict                # schema-validated payload
    origin: str               # "live" | "recorded" | "transcribed"
    model: str | None
    recorded_at: str | None
    usage: Usage | None       # None unless origin is live/recorded AND the API returned it

class LLMBackend(Protocol):
    def run(self, req: LLMRequest) -> LLMResult: ...
```

Backends (selected by `--llm` or `LLM_MODE`, default `replay`):

| backend | behaviour |
|---|---|
| `replay` | Looks up `code/llm/fixtures/<step>/<input_ref>.md` by `(step, input_sha, schema_version)`. A miss raises `FixtureMissing`. It never fabricates an answer. |
| `live` | OpenAI-compatible SDK, `base_url=https://openrouter.ai/api/v1`, key from `os.environ.get("OPENROUTER_API_KEY", "placeholder")`, models from `OPENROUTER_MODEL_VISION` / `OPENROUTER_MODEL_TEXT` (no baked-in defaults; pick them from the provider's live model list). Temperature 0. Reads `response.usage` verbatim. |
| `record` | `live` plus writing each answer to a fixture (origin `recorded`, with the usage the API returned), so later runs replay it. |
| `off` | Raises `LLMUnavailable`. Callers degrade (see below) and the run report says so. |

Fixture format is Markdown (the code judge ignores raw `.json`): a small header (`step`, `input_ref`,
`input_sha`, `schema_version`, `origin`, `model`, `recorded_at`, optional `usage`) followed by one fenced
JSON block. Rules enforced by a test:
- `origin: transcribed` fixtures (written by me from `code/notes/evidence_artifacts.md`, not by a model) may not
  contain a `usage` field.
- Only `origin: live` / `recorded` results contribute to token totals.
- A fixture's key ignores prompt wording, so editing a prompt does not silently invalidate fixtures;
  changing the schema bumps `schema_version`.

Prompts live in `code/prompts/*.md` (versioned header). They are source, so the judge sees them.

### Safety rails on the LLM output
- `screenshot_transcribe`: the LINK event, not the picture, picks the subject. The reader checks that the
  LINK resource id appears in the transcription and records a warning otherwise (`marketing_001` shows
  a person who is not in `user_identities`). Facts feed the same `Observation` type as every other parser.
- `intent_classify`: runs only after the lexicon and the `CLASSIFY_REQUEST` event. Negated deletion cues
  ("I am not asking for deletion", "do not close the account") route to the LLM instead of being counted
  as deletion.
- One schema-repair retry at most, logged. After that: `UNCLEAR` / "no screenshot facts" plus a warning.
- Degradation with `--llm off` or a fixture miss: the case is still produced from the other evidence, the
  missing step is listed in the run report, and nothing is guessed.

### Token and cost accounting (real calls only)
- Every live call appends one row to `code/evaluation/usage_ledger.md`: run id, timestamp, step, input ref,
  model, prompt tokens, completion tokens, cost or `not reported`.
- `usage_report.md` is generated from ledger rows with `origin: live` of the final run: per-model and
  overall totals, per-request averages (totals / 518), and the count of calls that returned no usage.
- Cost is the provider-reported figure. If it is missing for some calls, the report says "partial". An
  estimate may use pricing fetched from the provider's model-list endpoint during that run (stored with a
  timestamp). No price is hard-coded and nothing is back-filled.
- The submission's final run is `--llm live` on an empty fixture directory so every counted call is real.

## Pipeline

```
dataset/*.csv, evidence/*  ->  loaders  ->  EvidenceIndex (built once per run, in memory)
                                              |  Observation(system, resource_id, record_type, state signals,
                                              |              identifiers, captured_at, recorded_at, file_id)
case row -> intent (lexicon / events / LLM) -> NOT_APPLICABLE shortcut: "[]"
         -> identity (current + old emails, hashes, phones; case-insensitive)
         -> linking (direct tokens, LINK events, then worker-event matching for id-less resources)
         -> state at audit_at (file gate, record gate, latest wins, claims are hints)
         -> policy (record type -> action) -> findings / remediation / verification
         -> ordering + citation rule -> steps_json -> output.csv
```

Layout (Python, entry `python3 code/main.py`):

```
code/main.py                   CLI: --llm {replay,live,record,off} --dataset dataset --out output.csv
code/audit/{io,identity,intent,linking,state,policy,planner,output}.py
code/audit/evidence/{logs,sql,json_records,ledger,pdf,screenshots}.py   -> Observation
code/llm/{interface,replay,openrouter,usage}.py     code/llm/fixtures/<step>/*.md
code/prompts/{screenshot_transcribe,intent_classify}.md
code/evaluation/{score.py, evaluation_report.md, usage_report.md, usage_ledger.md}
code/tests/                    offline, replay-backed
```

Notes:
- "Parsed once" means one `EvidenceIndex` per run (about 1.2 MB of evidence, seconds to build). There is no
  persisted evidence cache; only LLM answers are cached (as fixtures).
- Linking and state are separate modules on purpose: identity may use any capture date, state may not.
- Residual id matching (accounts and anonymized analytics) is a scored, explainable step: window, exclusion
  of resources owned by others, `reported_status` <-> worker-result agreement, then propagation. Ambiguous
  results are logged with their candidate lists rather than hidden.
- Output is built from sorted tuples with a fixed key function; JSON is dumped with sorted keys.

## Scorer (built first)
Computed on the 32 samples, reusable on custom cases:
- case status accuracy (also split by COMPLETE / INCOMPLETE / NOT_APPLICABLE);
- step-level exact match (all 7 fields) after order-aware alignment, and per-field accuracy;
- sequence accuracy: whole-array exact match and an order-aware overlap ratio;
- a per-case diff written as Markdown for the evaluation report.
The hidden grader's weights are unknown, so the scorer reports each component separately.

## Sprints (small, each with a test that fails first)
1. **Scorer, loaders, identity, writer.** Self-score of `sample_output.csv` is 100%; perturbations drop
   the right metric; 550/550 request emails resolve; ordering/JSON tests.
2. **Evidence ingestion.** Per-format parsers into `Observation`, with a coverage report (every file
   parses; no state-bearing log event dropped). PDFs via `pdftotext`; screenshots via `replay` fixtures
   transcribed from `code/notes/evidence_artifacts.md`.
3. **Linking and state.** Clock rules, latest-wins, replica diff, readback over claims. Report found-resource
   precision/recall and state accuracy on the samples.
4. **Residual matching and citation.** Accounts/analytics matching, citation rule, absence-proof rule. Report
   ambiguous counts.
5. **Planner, intent, full run.** Valid 518-row `output.csv`, samples scored, structural validator
   (consecutive step numbers, evidence-id rules, ordering).
6. **Live LLM (needs the key).** OpenRouter backend, `record` mode, 11 screenshots and any intent-fallback
   calls recorded, usage ledger checked against real responses, agreement report between each recorded
   transcription and my hand transcription.
7. **Eval-only families and reports.** Tests from the 12 derived image/PDF cases and at least three custom
   cases, legal-hold / expiry decisions, `evaluation_report.md`, final live run, `usage_report.md`, README,
   packaging.

Sprints 1-5 need no network. Sprint 6 is the only one blocked on the API key.

## Risks I cannot remove from the samples
- About 22% of account ids stay ambiguous after matching (two or three candidates).
- Some ids appear in no file (3 of ~130 in samples; 93 of 540 deletion cases have no discoverable audit record, 8 of which are expected).
- Eight format variants have no sample truth: three replica layouts (reporting, regional, failover-generic)
  and five log dialects (pipe, bracket, syslog, JSON lines, cloud-runtime).
- Legal-hold step shape, `object_storage` / `marketing_platform` / `legal_service` system ids, DELETION_PENDING,
  expired exports, and string-vs-numeric tie-breaks are unverified.
