"""Timestamp helpers. All evidence uses UTC ISO-8601 with a trailing Z, which sorts lexicographically."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache

_FMT = "%Y-%m-%dT%H:%M:%SZ"


@lru_cache(maxsize=None)
def parse(ts: str) -> datetime:
    return datetime.strptime(ts, _FMT).replace(tzinfo=timezone.utc)


def epoch(ts: str) -> float:
    return parse(ts).timestamp()


def fmt(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime(_FMT)


def shift(ts: str, **delta) -> str:
    return fmt(parse(ts) + timedelta(**delta))


def minutes_between(later: str, earlier: str) -> float:
    return (parse(later) - parse(earlier)).total_seconds() / 60.0
