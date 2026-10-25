"""The `replay` backend: answers come only from stored fixtures. No network, no key, deterministic.

Fixtures are looked up in the given origins in order (default: transcribed only). A request without a fixture raises
FixtureMissing; replay never fabricates an answer and never reports usage for a transcribed fixture."""
from __future__ import annotations

from pathlib import Path

from .fixtures import FIXTURE_ROOT, parse_fixture, path_for
from .interface import FixtureMissing, LLMRequest, LLMResult


class ReplayBackend:
    name = "replay"

    def __init__(self, root: Path = FIXTURE_ROOT, origins=("transcribed",)):
        self.root, self.origins = Path(root), tuple(origins)

    def run(self, req: LLMRequest) -> LLMResult:
        for origin in self.origins:
            p = path_for(self.root, origin, req.step, req.key)
            if p.exists():
                return parse_fixture(p.read_text(encoding="utf-8"), expect_origin=origin)
        raise FixtureMissing(f"no {'/'.join(self.origins)} fixture for {req.step} {req.key} under {self.root}")
