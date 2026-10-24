"""Extraction of identity tokens (emails, user ids, email hashes, phones) from arbitrary text."""
from __future__ import annotations

import re

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+")
USER_RE = re.compile(r"\buser_\d+\b")
HASH_RE = re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{64}(?![0-9a-fA-F])")
PHONE_RE = re.compile(r"\+\d[\d ()\-]{6,}\d")


def norm_phone(p: str) -> str:
    return "+" + re.sub(r"\D", "", p)


def tokens_of(text: str) -> frozenset:
    out = {m.lower() for m in EMAIL_RE.findall(text)}
    out.update(m.lower() for m in USER_RE.findall(text))
    out.update(m.lower() for m in HASH_RE.findall(text))
    out.update(norm_phone(m) for m in PHONE_RE.findall(text))
    return frozenset(out)


def flatten_strings(obj, out=None) -> list:
    """All scalar values of a JSON-like object as strings."""
    out = [] if out is None else out
    if isinstance(obj, dict):
        for v in obj.values():
            flatten_strings(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            flatten_strings(v, out)
    elif obj is not None:
        out.append(str(obj))
    return out


def tokens_of_obj(obj) -> frozenset:
    return tokens_of("\n".join(flatten_strings(obj)))
