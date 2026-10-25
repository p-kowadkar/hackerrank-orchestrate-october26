"""The two model-backed steps, as callables the audit core can plug in.

ScreenshotReader   build_index(images=reader): reads one PNG, validates the answer, adds the subject row's observation.
IntentFallback     run(intent_fallback=fb): classifies a request text the rule-based classifier marked UNCLEAR.

Both keep a record of every call (backend, origin, model, usage) and every problem, which the run manifest turns into the
usage report. A failure never stops the run: the screenshot stays unread, or the text keeps the default (deletion) with a warning.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ghostaudit.evidence.screens import screen_to_observations

from .interface import LLMError, LLMRequest, LLMUnavailable, LLMValidationError, Usage
from .prompts import load_prompt


@dataclass(frozen=True)
class CallRecord:
    step: str
    key: str
    backend: str
    origin: str                 # transcribed | recorded | live
    model: str
    usage: Optional[Usage]


class ScreenshotReader:
    STEP = "screenshot_transcribe"

    def __init__(self, backend, prompt_dir: Optional[Path] = None):
        self.backend = backend
        self.system, self.task = load_prompt(self.STEP, prompt_dir) if prompt_dir else load_prompt(self.STEP)
        self.calls: list = []
        self.problems: list = []          # (file_id, text)
        self.unread: list = []            # (file_id, reason)

    def __call__(self, sink, file_id: str, captured_at: str, path: Path, links: list):
        req = LLMRequest(self.STEP, file_id, self.system,
                         f"{self.task}\n\nEvidence file: {file_id}\nImage: {Path(path).name}", Path(path),
                         {"captured_at": captured_at})
        try:
            result = self.backend.run(req)
        except LLMUnavailable as exc:                    # includes FixtureMissing: the screenshot stays unread
            sink.skipped(file_id, f"screenshot not read: {exc}")
            self.unread.append((file_id, str(exc)))
            return
        except LLMValidationError as exc:
            sink.unrecognised(file_id, "screenshot answer failed validation")
            self.problems.append((file_id, "invalid answer: " + str(exc)))
            return
        except LLMError as exc:
            sink.skipped(file_id, f"screenshot not read: {exc}")
            self.unread.append((file_id, str(exc)))
            return
        self.calls.append(CallRecord(self.STEP, file_id, self.backend.name, result.origin, result.model, result.usage))
        for p in screen_to_observations(sink, file_id, captured_at, result.data, links):
            self.problems.append((file_id, p))


class IntentFallback:
    STEP = "intent_classify"

    def __init__(self, backend, prompt_dir: Optional[Path] = None):
        self.backend = backend
        self.system, self.task = load_prompt(self.STEP, prompt_dir) if prompt_dir else load_prompt(self.STEP)
        self.calls: list = []
        self.problems: list = []

    def __call__(self, case_id: str, request_text: str) -> Optional[str]:
        req = LLMRequest(self.STEP, case_id, self.system, f"{self.task}\n\nRequest text:\n{request_text}")
        try:
            result = self.backend.run(req)
        except LLMError as exc:
            self.problems.append((case_id, str(exc)))
            return None
        self.calls.append(CallRecord(self.STEP, case_id, self.backend.name, result.origin, result.model, result.usage))
        return result.data["label"]
