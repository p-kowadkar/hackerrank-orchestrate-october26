"""Validation of structured model output, one validator per step."""
from __future__ import annotations

from ghostaudit.evidence.screens import ScreenError, validate_screen

from .interface import LLMValidationError

INTENT_LABELS = ("DELETE", "NON_DELETE")


def validate_screenshot_transcribe(data) -> dict:
    try:
        return validate_screen(data)
    except ScreenError as exc:
        raise LLMValidationError(exc.problems) from exc


def validate_intent_classify(data) -> dict:
    problems = []
    if not isinstance(data, dict) or set(data) != {"label", "reason"}:
        raise LLMValidationError(["output must be an object with exactly the keys label and reason"])
    if data["label"] not in INTENT_LABELS:
        problems.append(f"label must be one of {INTENT_LABELS}")
    if not isinstance(data["reason"], str) or not data["reason"].strip():
        problems.append("reason must be a non-empty string")
    if problems:
        raise LLMValidationError(problems)
    return data


VALIDATORS = {"screenshot_transcribe": validate_screenshot_transcribe, "intent_classify": validate_intent_classify}


def validate(step: str, data) -> dict:
    if step not in VALIDATORS:
        raise LLMValidationError([f"unknown step {step!r}"])
    return VALIDATORS[step](data)
