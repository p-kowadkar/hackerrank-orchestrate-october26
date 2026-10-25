"""The `off` backend: no model, no fixtures. Every request is reported as unavailable, so callers fall back to their
deterministic behaviour (screenshots stay unread, unclear request texts default to deletion with a warning)."""
from __future__ import annotations

from .interface import LLMRequest, LLMResult, LLMUnavailable


class OffBackend:
    name = "off"

    def run(self, req: LLMRequest) -> LLMResult:
        raise LLMUnavailable(f"llm mode is off ({req.step} {req.key})")
