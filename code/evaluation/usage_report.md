# Usage report

Status: **no model has been called yet.** This file will be rewritten from the usage ledger after the final full-dataset
run. Until a real API response exists, every figure below is zero or "not measured"; nothing in it is estimated or invented.

## Final run that produced `output.csv` (current state)

| item | value |
|---|---|
| model providers | none |
| model names | none |
| model calls | 0 |
| input tokens | 0 |
| output tokens | 0 |
| total tokens | 0 |
| average tokens per request (518 requests) | 0 |
| estimated total cost | 0 (no billable call was made) |
| estimated cost per request | 0 |

How the current `output.csv` is produced: `python3 code/main.py` runs a deterministic pipeline (rules, parsers and the
dataset's own tables). It needs no network, no API key and no model, and gives byte-identical output on every run.

## Where a model will be used (planned, Sprints 4 and 5)

| step | purpose | requests affected | status |
|---|---|---|---|
| screenshot transcription | read the 11 application screenshots (they are images, so a vision model is the only way) | 12 image/PDF cases | not built; the 4 PDFs need no model (text extraction) |
| intent fallback | classify a request text the rule-based classifier marks UNCLEAR | expected 0 of the 518 (the classifier recognises all 518 today) | not built |

Both steps will sit behind one small interface with `replay`, `live`, `record` and `off` backends. Offline runs read stored
responses; the final run is `live` on an empty fixture directory so that every counted call is real. Stored responses
transcribed by hand are marked `transcribed` and are never allowed to carry usage numbers.

## Rules for the numbers that will appear here

- Tokens come only from the `usage` field of real API responses, recorded per call in the usage ledger. No count is estimated
  from text length and none is copied from a price list.
- Cost is computed from those recorded tokens and the provider's published per-token prices at the time of the run; the
  prices used will be listed next to the totals.
- The report will give per-model and overall totals, the number of calls, input and output tokens, total and average tokens
  per request, and estimated total and per-request cost, as the task requires.
- The API key is read from the environment variable `OPENROUTER_API_KEY` (a placeholder is used when it is absent); it is
  never written to a file, log or report. A real key is needed outside the development sandbox.

## Why the figures may stay at zero for the 506 text-only requests

The 506 requests that are neither image/PDF cases nor unclear text are decided without a model. If the final run is
`live`, they still show 0 calls, which is the honest description of the architecture: the model reads pixels and, rarely,
ambiguous text; the audit logic is deterministic code.
