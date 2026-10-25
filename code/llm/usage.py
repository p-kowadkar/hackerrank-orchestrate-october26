"""The usage ledger: an append-only Markdown table with one row per real API response.

Rows are written only by the live backend, at the moment a response arrives, so no call can be missed and nothing else can
reach the table. `Ledger.record` refuses anything that is not a live result carrying provider-reported usage.
Markdown (not JSON/CSV) so that the report reviewers can read it.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .interface import LLMResult

LEDGER_PATH = Path(__file__).resolve().parents[1] / "evaluation" / "usage_ledger.md"
COLUMNS = ("run_id", "time_utc", "step", "key", "provider", "model", "request_id", "prompt_tokens", "completion_tokens",
           "total_tokens", "cost_usd", "outcome")
HEADER = ("# Usage ledger\n\nOne row per real API response, appended by the live backend when the response arrives. Tokens and "
          "cost are exactly what the provider reported (`none` = the provider reported no cost). Nothing in this table is "
          "estimated. `outcome` is `ok` or `invalid` (the response arrived and was paid for but failed validation).\n\n"
          "| " + " | ".join(COLUMNS) + " |\n|" + "---|" * len(COLUMNS) + "\n")


class LedgerError(ValueError):
    pass


@dataclass(frozen=True)
class LedgerRow:
    run_id: str
    time_utc: str
    step: str
    key: str
    provider: str
    model: str
    request_id: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: Optional[float]
    outcome: str


class Ledger:
    def __init__(self, path: Path = LEDGER_PATH):
        self.path = Path(path)

    def record(self, result: LLMResult, run_id: str, outcome: str = "ok", now: Optional[datetime] = None) -> LedgerRow:
        if result.origin != "live":
            raise LedgerError(f"only live results enter the ledger, got origin {result.origin!r}")
        u = result.usage
        if u is None or u.source != "api":
            raise LedgerError("a ledger row needs usage reported by the API")
        if outcome not in ("ok", "invalid"):
            raise LedgerError(f"unknown outcome {outcome!r}")
        t = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
        row = LedgerRow(run_id, t, result.step, result.key, result.provider, result.model, result.request_id,
                        u.prompt_tokens, u.completion_tokens, u.total_tokens, u.cost_usd, outcome)
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(HEADER, encoding="utf-8")
        cells = [row.run_id, row.time_utc, row.step, row.key, row.provider, row.model, row.request_id,
                 str(row.prompt_tokens), str(row.completion_tokens), str(row.total_tokens),
                 "none" if row.cost_usd is None else repr(row.cost_usd), row.outcome]
        with open(self.path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write("| " + " | ".join(cells) + " |\n")
        return row

    def rows(self, run_id: Optional[str] = None) -> list:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.startswith("| ") or line.startswith("| run_id"):
                continue
            c = [x.strip() for x in line.strip().strip("|").split("|")]
            if len(c) != len(COLUMNS):
                continue
            row = LedgerRow(c[0], c[1], c[2], c[3], c[4], c[5], c[6], int(c[7]), int(c[8]), int(c[9]),
                            None if c[10] == "none" else float(c[10]), c[11])
            if run_id is None or row.run_id == run_id:
                out.append(row)
        return out
