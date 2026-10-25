"""Helpers for tools and tests: the pipeline with the screenshots read from the stored (hand-made) transcriptions."""
from __future__ import annotations

from ghostaudit.pipeline import run

from .reader import ScreenshotReader
from .replay import ReplayBackend


def offline_reader() -> ScreenshotReader:
    return ScreenshotReader(ReplayBackend())


def run_replay(ds, requested=None, options=None, **kw):
    kw.setdefault("images", offline_reader())
    return run(ds, requested, options, **kw)
