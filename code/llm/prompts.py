"""Prompts live in Markdown files under code/prompts/. A prompt file has `## System` and `## Task` sections; anything
else in the file (the schema description, notes) is documentation for people and is part of the Task text."""
from __future__ import annotations

import re
from pathlib import Path

PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts"


def load_prompt(name: str, directory: Path = PROMPT_DIR) -> tuple:
    """-> (system, task) text of code/prompts/<name>.md."""
    text = (directory / f"{name}.md").read_text(encoding="utf-8")
    parts = re.split(r"^## ", text, flags=re.M)
    sections = {p.split("\n", 1)[0].strip().lower(): p.split("\n", 1)[1].strip() if "\n" in p else "" for p in parts[1:]}
    if "system" not in sections or "task" not in sections:
        raise ValueError(f"prompt {name} needs '## System' and '## Task' sections")
    rest = [f"## {k.title()}\n{v}" for k, v in sections.items() if k not in ("system", "task")]
    return sections["system"], "\n\n".join([sections["task"]] + rest)
