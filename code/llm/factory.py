"""Builds the backend for a mode and the run id that ties ledger rows to a run."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .fixtures import FIXTURE_ROOT
from .interface import LLMBackend
from .off import OffBackend
from .openrouter import OpenRouterBackend
from .record import RecordBackend
from .replay import ReplayBackend
from .usage import Ledger

MODES = ("off", "replay", "live", "record")


def new_run_id(mode: str) -> str:
    """Live and record runs get a timestamped id; offline runs a fixed one, so offline output stays byte-identical."""
    if mode in ("live", "record"):
        return "run-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"offline-{mode}"


def make_backend(mode: str, *, fixtures: Path = FIXTURE_ROOT, replay_origins=("transcribed",), model: Optional[str] = None,
                 ledger: Optional[Ledger] = None, run_id: Optional[str] = None, transport=None) -> LLMBackend:
    if mode == "off":
        return OffBackend()
    if mode == "replay":
        return ReplayBackend(fixtures, replay_origins)
    if mode in ("live", "record"):
        kwargs = {"transport": transport} if transport is not None else {}
        live = OpenRouterBackend(model, ledger or Ledger(), run_id or new_run_id(mode), allow_network=True, **kwargs)
        return live if mode == "live" else RecordBackend(live, fixtures)
    raise ValueError(f"unknown llm mode {mode!r}; choose one of {MODES}")
