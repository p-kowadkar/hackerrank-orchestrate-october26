"""Loaders for the participant-facing CSV files. Nothing here reads organizer-only data."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from .paths import DATASET_DIR


def read_csv(path: Path) -> list:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


@dataclass(frozen=True)
class Request:
    case_id: str
    email: str
    requested_at: str
    reported_status: str
    reported_at: str
    audit_at: str
    request_text: str
    origin: str = "eval"   # "eval" (deletion_requests.csv) or "sample" (sample_deletion_requests.csv)

    @property
    def number(self) -> int:
        return int(self.case_id.split("_")[1])


def case_sort_key(case_id: str):
    """Natural order: case_33 < case_100. The same order as deletion_requests.csv."""
    prefix, _, num = case_id.partition("_")
    return (prefix, int(num)) if num.isdigit() else (prefix, 10 ** 9, case_id)


def load_requests(path: Path, origin: str) -> list:
    return [Request(origin=origin, **{k: r[k] for k in (
        "case_id", "email", "requested_at", "reported_status", "reported_at", "audit_at", "request_text")})
        for r in read_csv(path)]


class Dataset:
    """All participant-facing tables, loaded once."""

    def __init__(self, root: Path = DATASET_DIR):
        self.root = Path(root)
        self.requests = load_requests(self.root / "deletion_requests.csv", "eval")
        self.sample_requests = load_requests(self.root / "sample_deletion_requests.csv", "sample")
        self.identities = read_csv(self.root / "user_identities.csv")
        self.audit_log = read_csv(self.root / "user_audit_log.csv")
        self.activity = read_csv(self.root / "system_activity.csv")
        self.rules = read_csv(self.root / "deletion_rules.csv")
        self.manifest = {r["file_id"]: r for r in read_csv(self.root / "evidence_files.csv")}

    def evidence_path(self, file_id: str) -> Path:
        return self.root / self.manifest[file_id]["file_path"]

    @property
    def all_requests(self) -> list:
        """Eval first, then samples. Used as matching context; the output only contains the requested set."""
        return list(self.requests) + list(self.sample_requests)
