"""Shared, lazily built fixtures so the suite stays fast (the dataset builds in about a second)."""
import sys
from functools import lru_cache
from pathlib import Path

CODE = Path(__file__).resolve().parents[1]
for p in (CODE, CODE / "evaluation"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from ghostaudit.data import Dataset          # noqa: E402
from ghostaudit.evidence import build_index  # noqa: E402
from ghostaudit.identity import IdentityResolver  # noqa: E402
from ghostaudit.pipeline import run          # noqa: E402
from ghostaudit.planner import PlanOptions   # noqa: E402


@lru_cache(maxsize=1)
def dataset():
    return Dataset()


@lru_cache(maxsize=1)
def index():
    return build_index(dataset())


@lru_cache(maxsize=1)
def resolver():
    ds = dataset()
    return IdentityResolver(ds.identities, ds.audit_log)


@lru_cache(maxsize=4)
def pipeline_run(ambiguity="guess"):
    ds = dataset()
    return run(ds, ds.all_requests, PlanOptions(ambiguity=ambiguity))
