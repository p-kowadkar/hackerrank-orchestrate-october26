"""Builds the in-memory evidence index once per run."""
from __future__ import annotations

import re
from collections import defaultdict

from .. import model as m
from ..data import Dataset
from ..timeutil import shift
from .common import Sink
from .documents import parse_pdf
from .logs import parse_log
from .structured import parse_json, parse_sql, parse_text

LINK_RE = re.compile(r"to (\S+?) and (user_\d+)|only to (\S+?) and (user_\d+)")


def extract_links(ds: Dataset) -> list:
    """LINK_RESOURCE_IDENTITY events; each ties a resource to a user and to the evidence file captured 7m01s earlier."""
    by_time = defaultdict(list)
    for fid, row in ds.manifest.items():
        by_time[row["captured_at"]].append(fid)
    out = []
    for r in ds.activity:
        if r["event_type"] != "LINK_RESOURCE_IDENTITY":
            continue
        mt = LINK_RE.search(r["details"])
        if not mt:
            continue
        email = mt.group(1) or mt.group(3)
        user = mt.group(2) or mt.group(4)
        files = by_time.get(shift(r["event_time"], minutes=-7, seconds=-1), [])
        out.append(m.LinkFact(r["activity_id"], r["event_time"], r["resource_id"], r["target_system"],
                              email.strip(".,").lower(), user, files[0] if files else ""))
    return out


class EvidenceIndex:
    def __init__(self, obs, snapshots, links, stats, unknown):
        self.obs = obs
        self.snapshots = snapshots
        self.links = links
        self.stats = stats
        self.unknown = unknown
        self.by_rid = defaultdict(list)
        self.by_token = defaultdict(list)
        for o in obs:
            self.by_rid[o.resource_id].append(o)
            for t in o.tokens:
                self.by_token[t].append(o)


def build_index(ds: Dataset, images=None) -> EvidenceIndex:
    """`images` is an optional callable (file_id, captured_at, path, links) used for screenshots (see llm/)."""
    sink = Sink()
    links = extract_links(ds)
    links_by_file = defaultdict(list)
    for lk in links:
        if lk.file_id:
            links_by_file[lk.file_id].append(lk)
    for fid in sorted(ds.manifest, key=lambda s: int(s.split("_")[1])):
        row = ds.manifest[fid]
        path, cap = ds.evidence_path(fid), row["captured_at"]
        ext = path.suffix.lower()
        if ext == ".log":
            parse_log(sink, fid, cap, path)
        elif ext == ".txt":
            parse_text(sink, fid, cap, path)
        elif ext == ".json":
            parse_json(sink, fid, cap, path)
        elif ext == ".sql":
            parse_sql(sink, fid, cap, path)
        elif ext == ".pdf":
            parse_pdf(sink, fid, cap, path, links_by_file.get(fid, []))
        elif ext == ".png":
            if images is not None:
                images(sink, fid, cap, path, links_by_file.get(fid, []))
            else:
                sink.skipped(fid, "screenshot (needs transcription)")
        else:
            sink.unrecognised(fid, f"file type {ext}")
    return EvidenceIndex(sink.finalize(), sink.snapshots, links, sink.stats, sink.unknown)
