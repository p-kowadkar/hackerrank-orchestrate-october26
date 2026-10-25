"""The one interface every model-backed step goes through.

Two steps use it: `screenshot_transcribe` (the 11 application screenshots) and `intent_classify` (request texts the rule
based classifier cannot place). A backend takes an `LLMRequest` and returns an `LLMResult` whose `data` has already been
validated against the step's schema, or raises. There are four backends: off, replay, live, record.

Honesty rules enforced here and in usage.py:
  * `Usage` exists only on results that came from a real API response (`source == "api"`);
  * a result read from a hand-made ("transcribed") fixture has `usage = None` and can never reach the ledger;
  * a missing fixture raises `FixtureMissing`; nothing is ever invented.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Protocol

STEPS = ("screenshot_transcribe", "intent_classify")
ORIGINS = ("transcribed", "recorded", "live")


class LLMError(RuntimeError):
    """Base class for every failure of a model-backed step."""


class LLMUnavailable(LLMError):
    """The backend is switched off, or live access is not configured."""


class FixtureMissing(LLMError):
    """Replay found no stored response for the request."""


class LLMValidationError(LLMError):
    """The response does not satisfy the step's schema. `.problems` lists every reason."""

    def __init__(self, problems: list):
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass(frozen=True)
class LLMRequest:
    step: str                       # one of STEPS
    key: str                        # stable id of the input: the evidence file id, or the case id
    system: str                     # system prompt (from code/prompts/*.md)
    user: str                       # task text (from code/prompts/*.md plus the per-input context)
    image_path: Optional[Path] = None
    meta: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: Optional[float]       # as reported by the provider; None when the provider reported none
    source: str = "api"             # only "api" is ever accepted by the ledger


@dataclass(frozen=True)
class LLMResult:
    step: str
    key: str
    data: dict                      # validated structured output
    origin: str                     # transcribed | recorded | live
    model: str = ""
    provider: str = ""
    request_id: str = ""
    usage: Optional[Usage] = None
    raw_text: str = ""


class LLMBackend(Protocol):
    name: str

    def run(self, req: LLMRequest) -> LLMResult:
        ...
