"""End-to-end run: identity -> intent -> evidence -> linking -> account matching -> plan."""
from __future__ import annotations

from dataclasses import dataclass, field

from . import model as m
from .data import Dataset
from .evidence import build_index
from .identity import IdentityResolver
from .intent import DELETE, NON_DELETE, UNCLEAR, classify_text
from .planner import CaseResult, PlanOptions, build_context, decisions_for, plan_case
from .timeutil import parse
from .residual import AccountMatcher, AnalyticsMatcher, learn_cadence


@dataclass
class RunResult:
    results: dict = field(default_factory=dict)         # case_id -> CaseResult (requested set only)
    assignments: dict = field(default_factory=dict)     # case_id -> AccountAssignment (all deletion cases)
    intents: dict = field(default_factory=dict)         # case_id -> (label, reason, corroborated)
    analytics: dict = field(default_factory=dict)       # case_id -> AccountAssignment-like for anonymized analytics
    tiebreak_uses: list = field(default_factory=list)
    cadence_uses: list = field(default_factory=list)
    cadence: set = field(default_factory=set)
    warnings: list = field(default_factory=list)
    index: object = None
    options: PlanOptions = None


def classify_corroboration(ds: Dataset, index) -> set:
    """Emails that a CLASSIFY_REQUEST event flags as non-deletion (account id -> email via any evidence record)."""
    accounts = {r["resource_id"] for r in ds.activity if r["event_type"] == "CLASSIFY_REQUEST"}
    emails = set()
    for rid in accounts:
        for o in index.by_rid.get(rid, ()):
            emails.update(t for t in o.tokens if "@" in t)
    return emails


def run(ds: Dataset, requested=None, options: PlanOptions | None = None, images=None) -> RunResult:
    options = options or PlanOptions()
    requested = list(ds.requests if requested is None else requested)
    resolver = IdentityResolver(ds.identities, ds.audit_log)
    index = build_index(ds, images)
    flagged = classify_corroboration(ds, index)
    out = RunResult(index=index, options=options)
    contexts = []
    for req in ds.all_requests:                                   # matching context: eval + sample requests
        intent = classify_text(req.request_text)
        label = intent.label
        corroborated = req.email.lower() in flagged
        if label == UNCLEAR:
            out.warnings.append(f"{req.case_id}: intent unclear; defaulting to DELETE (LLM fallback not wired)")
            label = DELETE
        if label == DELETE and corroborated:
            out.warnings.append(f"{req.case_id}: text says deletion but a CLASSIFY_REQUEST event flags it non-deletion")
        out.intents[req.case_id] = (label, intent.reason, corroborated)
        if label == DELETE:
            contexts.append(build_context(index, resolver, req))
    matcher = AccountMatcher(ds.activity, index, resolver, options.ambiguity)
    out.assignments = matcher.assign(contexts)
    out.tiebreak_uses = matcher.tiebreak_uses
    by_case = {c.request.case_id: c for c in contexts}
    # anonymized analytics profiles carry no identifier: match them through the worker's action timeline
    worker = {}
    for r in ds.activity:
        if r["source_system"] == "deletion_worker" and r["reported_result"] == "SUCCESS" and r["event_type"] in (
                "REDACT_RECORD", "DISABLE_DATA_FLOW", "BLOCK_RESTORE"):
            worker.setdefault(r["resource_id"], []).append(r["event_time"])
    sibling_times, skip_analytics = {}, set()
    for ctx in contexts:
        times = []
        decisions = decisions_for(index, ctx, out.assignments[ctx.request.case_id].resource_id)
        if any(d.violating for d in decisions):      # an INCOMPLETE case never lists a compliant analytics profile
            skip_analytics.add(ctx.request.case_id)
        for d in decisions:
            if d.rtype == m.ANALYTICS:
                skip_analytics.add(ctx.request.case_id)
            if d.rtype in (m.SUPPORT_MESSAGE, m.TOMBSTONE, m.DATA_FLOW, m.BACKUP) and not d.violating and d.resource_id in worker:
                near = min(worker[d.resource_id], key=lambda t: abs((parse(t) - parse(ctx.request.reported_at)).total_seconds()))
                times.append(near)
        sibling_times[ctx.request.case_id] = sorted(times)
    out.cadence = learn_cadence(list(sibling_times.values())) if options.use_cadence else set()
    amatcher = AnalyticsMatcher(ds.activity, index, out.cadence, options.ambiguity)
    out.analytics = amatcher.assign(contexts, skip_analytics, sibling_times)
    out.cadence_uses = amatcher.cadence_uses
    for req in requested:
        label = out.intents[req.case_id][0]
        if label == NON_DELETE:
            out.results[req.case_id] = CaseResult(req.case_id, "NOT_APPLICABLE", [])
            continue
        asg = out.assignments[req.case_id]
        extra = [out.analytics[req.case_id].resource_id] if req.case_id in out.analytics and out.analytics[req.case_id].resource_id else []
        res = plan_case(index, by_case[req.case_id], asg.resource_id, options, extra)
        res.account_how = asg.how
        out.results[req.case_id] = res
    return out
