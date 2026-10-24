# Residual identity: how an id-less resource is matched to a case

A deleted account leaves no identifier behind, and an anonymized analytics profile carries none by design.
Evidence therefore cannot name them, and the worker events in `system_activity.csv` are the only trail. Everything
here is a heuristic, kept strictly below evidence in precedence, counted, and reported. Numbers come from
`python3 code/evaluation/identity_backtest.py` (255 cases whose account is established by evidence; the link is hidden
for a whole `reported_at` cohort at once, which is the hard situation) and from the 32 samples.

## Account (order of precedence)

1. **Evidence**: the account appears with one of the subject's identifiers inside the case window.
2. **Elimination**: take the `DELETE_RECORD` events on `account_service` in `[reported_at - 80 min, reported_at + 10 min]`,
   drop accounts owned by other users and accounts already assigned to another case, accept a unique survivor, repeat
   until stable. Backtest: 45/45 correct.
3. **Last-resort tiebreak** (your decision): prefer candidates whose worker result agrees with `reported_status`
   (SUCCESS-COMPLETE, PARTIAL-PARTIALLY_COMPLETE, FAILED-NOT_STARTED). It only narrows, is ignored if it would empty
   the set, never overrides evidence, and every use is recorded (`run_report.md`). Backtest: 82/82 correct when it
   resolves a case; 116 uses in the real run, 80 narrowed to a single account, 36 narrowed but still tied.
4. **Ambiguity policy**: see below.

The `account_00N` naming convention is not used anywhere (a test enforces this).

## Ambiguity policy

Backtest of the three policies on the 32 samples (criterion fixed before the run: step F1, then exact cases, then
fewer extra steps; ties to the more conservative policy):

| policy | step F1 | exact cases | extra steps | missing steps |
|---|---|---|---|---|
| omit | 0.9842 | 26/32 | 0 | 6 |
| hybrid | 0.9895 | 28/32 | 0 | 4 |
| guess | 0.9869 | 28/32 | 1 | 4 |

`hybrid` (guess only while at most 2 candidates remain, omit beyond that) wins and is the default.
The broader backtest agrees with the choice of a threshold at two candidates:

| candidates left | cases | correct | accuracy |
|---|---|---|---|
| 2 | 99 | 53 | 54% |
| 3 | 23 | 8 | 35% |
| 4+ | 4 | 1 | 25% |

Break-even for step F1 is roughly half of the current F1, i.e. a guess has to be right about half of the time to
beat omitting it. Two candidates clear that bar, three or more do not. Inside a cohort nothing breaks the tie (event
order vs case number 50%, `requested_at` 49%, user number 51%), so a two-way guess is a coin weighted slightly by
the earlier elimination steps. A case left with one candidate only because an earlier case guessed is labelled
`guess`, not `elimination`.

## Anonymized analytics profile (new heuristic, subject to your veto)

The profile has no identifier. A candidate must have a successful `ANONYMIZE_RECORD` event between 35 minutes before
and 5 minutes after `reported_at`, be observed as anonymized in admissible evidence, and not be claimed by another case.
For cases with directly linked compliant siblings (support, flow, backup, tombstone), the worker emits events on a
fixed cadence (gaps of 390 s and 449 s, learned from directly linked siblings and accepted only after at least five
occurrences). The analytics event must sit one, two or three cadence steps before the first sibling event. This is
a pattern learned from the data, not a documented rule, so it is reported separately (`run_report.md`, cadence uses)
and can be switched off with `PlanOptions(use_cadence=False)`.

## Assumptions to confirm

- Output rows are sorted in natural numeric order (`case_33` before `case_100`); the samples are sorted that way.
- Legal-hold records, `DELETION_PENDING` exports and expired exports have no sample truth; they are listed as open questions in
  `evidence_state_catalog.md`.
- `system_id` for object-storage, marketing and legal records follows the id prefix; no sample covers them.
