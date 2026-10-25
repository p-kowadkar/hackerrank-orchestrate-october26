"""Stored responses as Markdown files: `<root>/<origin>/<step>/<key>.md` with a small front matter and one JSON block.

`transcribed`: written by a person (here: the assistant in a Claude Code session, by reading the image). It carries no
usage fields, and the loader refuses a transcribed file that has any.
`recorded`: written by the record backend from a real API response, with the usage that response reported.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from .interface import LLMResult, LLMValidationError, Usage
from .schemas import validate

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures"
USAGE_KEYS = ("prompt_tokens", "completion_tokens", "total_tokens", "cost_usd")
_BLOCK = re.compile(r"```json\n(.*?)\n```", re.S)


def path_for(root: Path, origin: str, step: str, key: str) -> Path:
    return Path(root) / origin / step / f"{key}.md"


def parse_fixture(text: str, expect_origin: Optional[str] = None) -> LLMResult:
    if not text.startswith("---\n"):
        raise LLMValidationError(["fixture has no front matter"])
    head, _sep, body = text[4:].partition("\n---\n")
    meta = {}
    for line in head.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    origin = meta.get("origin", "")
    if origin not in ("transcribed", "recorded"):
        raise LLMValidationError([f"fixture origin must be transcribed or recorded, got {origin!r}"])
    if expect_origin and origin != expect_origin:
        raise LLMValidationError([f"fixture origin {origin!r} found where {expect_origin!r} was expected"])
    has_usage = any(k in meta and meta[k] not in ("", "none") for k in USAGE_KEYS)
    if origin == "transcribed" and has_usage:
        raise LLMValidationError(["a transcribed fixture must not carry usage numbers"])
    mt = _BLOCK.search(body)
    if not mt:
        raise LLMValidationError(["fixture has no JSON block"])
    data = validate(meta.get("step", ""), json.loads(mt.group(1)))
    usage = None
    if origin == "recorded":
        if not has_usage:
            raise LLMValidationError(["a recorded fixture must carry the usage of the response it stores"])
        cost = meta.get("cost_usd", "none")
        usage = Usage(int(meta["prompt_tokens"]), int(meta["completion_tokens"]), int(meta["total_tokens"]),
                      None if cost in ("none", "") else float(cost), "api")
    return LLMResult(meta["step"], meta["key"], data, origin, meta.get("model", ""), meta.get("provider", ""),
                     meta.get("request_id", ""), usage, "")


def render_fixture(result: LLMResult, extra: dict) -> str:
    head = {"step": result.step, "key": result.key, "origin": result.origin}
    head.update(extra)
    if result.origin == "recorded":
        u = result.usage
        head.update({"model": result.model, "provider": result.provider, "request_id": result.request_id,
                     "prompt_tokens": u.prompt_tokens, "completion_tokens": u.completion_tokens,
                     "total_tokens": u.total_tokens, "cost_usd": "none" if u.cost_usd is None else u.cost_usd})
    lines = ["---"] + [f"{k}: {v}" for k, v in head.items()] + ["---", "", "```json",
                                                                json.dumps(result.data, indent=1, ensure_ascii=False), "```", ""]
    return "\n".join(lines)
