"""The `record` backend: live calls whose validated answers are also stored as `recorded` fixtures.

A key that already has a recorded fixture is replayed from it instead of being paid for twice. Recorded fixtures live next to,
never inside, the hand-made `transcribed` ones, so a transcription is never overwritten by a model reading."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .fixtures import FIXTURE_ROOT, parse_fixture, path_for, render_fixture
from .interface import LLMRequest, LLMResult


class RecordBackend:
    name = "record"

    def __init__(self, live, root: Path = FIXTURE_ROOT):
        self.live, self.root = live, Path(root)

    def run(self, req: LLMRequest) -> LLMResult:
        p = path_for(self.root, "recorded", req.step, req.key)
        if p.exists():
            return parse_fixture(p.read_text(encoding="utf-8"), expect_origin="recorded")
        result = self.live.run(req)
        recorded = LLMResult(result.step, result.key, result.data, "recorded", result.model, result.provider,
                             result.request_id, result.usage, "")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(render_fixture(recorded, {"run_id": self.live.run_id,
                                               "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}),
                     encoding="utf-8", newline="\n")
        return result
