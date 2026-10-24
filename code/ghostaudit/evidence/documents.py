"""PDF evidence (text-extractable) and the hooks for screenshot evidence."""
from __future__ import annotations

import subprocess
from pathlib import Path

from .. import model as m
from ..tokens import tokens_of
from .common import Sink

_PREFIX_RTYPE = (
    ("account_", m.ACCOUNT), ("search_", m.SEARCH), ("export_", m.EXPORT), ("marketing_", m.MARKETING),
    ("support_", m.SUPPORT_ATTACHMENT), ("analytics_", m.ANALYTICS), ("tombstone_", m.TOMBSTONE),
    ("data_flow_", m.DATA_FLOW), ("backup_", m.BACKUP), ("audit_record_", m.AUDIT), ("legal_hold_", m.LEGAL_HOLD),
    ("object_", m.SUPPORT_ATTACHMENT),
)


def default_rtype(resource_id: str):
    for prefix, rtype in _PREFIX_RTYPE:
        if resource_id.startswith(prefix):
            return rtype
    return None


def pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
        return "\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)
    except ImportError:                                           # pragma: no cover - optional system fallback
        return subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True, check=True).stdout


def parse_pdf(sink: Sink, file_id: str, captured_at: str, path: Path, links: list):
    """A PDF is a business artifact: it proves a record exists. Resource ids come from the text or a LINK event."""
    text = pdf_text(path)
    toks = tokens_of(text)
    rids = set(m.RID_RE.findall(text))
    made = 0
    for rid in sorted(rids):
        rtype = default_rtype(rid)
        if rtype in (m.AUDIT, m.SUPPORT_ATTACHMENT, m.EXPORT, m.LEGAL_HOLD):
            sink.add(file_id, captured_at, captured_at, rid, rtype, m.PRESENT, toks, "pdf")
            made += 1
    for link in links:
        if link.resource_id in rids:
            continue
        rtype = default_rtype(link.resource_id)
        if rtype is not None:
            sink.add(file_id, captured_at, captured_at, link.resource_id, rtype, m.PRESENT,
                     toks | {link.email.lower(), link.user_id.lower()}, "pdf:link")
            made += 1
    if not made:
        sink.ignored(file_id)          # e.g. the legal register: context only, no resource ids
