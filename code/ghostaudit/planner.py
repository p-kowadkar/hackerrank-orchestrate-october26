"""From resource decisions to the ordered findings / remediation / verification steps."""
from __future__ import annotations

from dataclasses import dataclass, field

from . import model as m
from .data import Request
from .state import Decision, absence_proof, decide, directly_linked


@dataclass
class CaseContext:
    request: Request
    user_id: str
    tokens: frozenset
    direct: dict = field(default_factory=dict)          # resource_id -> linking file ids


@dataclass
class CaseResult:
    case_id: str
    status: str                                         # COMPLETE | INCOMPLETE | NOT_APPLICABLE
    steps: list = field(default_factory=list)           # list of dict with the seven contract fields
    decisions: list = field(default_factory=list)       # Decision objects, for the run report
    notes: list = field(default_factory=list)
    account_how: str = ""


@dataclass
class PlanOptions:
    ambiguity: str = "hybrid"                          # guess | omit | hybrid (account and analytics matchers)
    verify_compliant_in_incomplete: bool = False        # list already-compliant resources in INCOMPLETE cases?
    verify_absent_nonaccount: bool = False              # list ABSENT search/export/... resources in COMPLETE cases?
    use_cadence: bool = True                            # link id-less analytics through the learned worker cadence
    use_tiebreak: bool = True                           # last-resort reported_status <-> worker-result tiebreak (accounts)


def build_context(index, resolver, request: Request) -> CaseContext:
    user_id, _form = resolver.resolve(request.email)
    tokens = resolver.usable_tokens(user_id)
    direct = directly_linked(index, tokens, user_id, request.audit_at)
    return CaseContext(request, user_id, tokens, direct)


def _step(phase_op: str, decision: Decision, evidence_id: str) -> dict:
    return {"phase": m.OP_PHASE[phase_op], "system_id": decision.system_id, "resource_id": decision.resource_id,
            "operation": phase_op, "state": m.OP_STATE[phase_op], "evidence_id": evidence_id or ""}


def decisions_for(index, ctx: CaseContext, account_rid, extra_rids=()) -> list:
    audit_at = ctx.request.audit_at
    rids = set(ctx.direct) | set(extra_rids)
    if account_rid:
        rids.add(account_rid)
    out = []
    for rid in sorted(rids):
        d = decide(index, rid, audit_at)
        if d is not None:
            out.append(d)
    # one account per case: keep only the chosen one if evidence linked several
    accounts = [d for d in out if d.rtype == m.ACCOUNT]
    if account_rid and len(accounts) > 1:
        out = [d for d in out if d.rtype != m.ACCOUNT or d.resource_id == account_rid]
    return out


def plan_case(index, ctx: CaseContext, account_rid, options: PlanOptions, extra_rids=()) -> CaseResult:
    audit_at = ctx.request.audit_at
    decisions = decisions_for(index, ctx, account_rid, extra_rids)
    violating = [d for d in decisions if d.violating]
    status = "INCOMPLETE" if violating else "COMPLETE"
    findings, remediation, verification = [], [], []
    for d in decisions:
        if d.violating:
            f_op, r_op, v_op = m.VIOLATION_OPS[d.rtype]
            findings.append(_step(f_op, d, d.obs.file_id))
            remediation.append(_step(r_op, d, ""))
            verification.append(_step(v_op, d, ""))
            continue
        # compliant resources
        if d.rtype == m.ACCOUNT:
            ev = ""
            if status == "COMPLETE":
                ev = d.obs.file_id if d.obs else (absence_proof(index, "account_service", audit_at) or "")
            verification.append(_step("VERIFY_RECORD_ABSENT", d, ev))
        elif d.rtype in (m.AUDIT, m.LEGAL_HOLD):
            ev = d.obs.file_id if (d.obs and status == "COMPLETE") else ""
            verification.append(_step("VERIFY_RECORD_PRESENT", d, ev))
        elif status == "COMPLETE" or options.verify_compliant_in_incomplete:
            if d.state == m.ABSENT and not options.verify_absent_nonaccount:
                continue
            ev = d.obs.file_id if (d.obs and status == "COMPLETE") else ""
            verification.append(_step(m.compliant_op(d.rtype), d, ev))
    steps = []
    for bucket in (findings, remediation, verification):
        bucket.sort(key=lambda s: (m.OPERATIONS.index(s["operation"]), s["system_id"], s["resource_id"]))
        steps.extend(bucket)
    for i, s in enumerate(steps, 1):
        s["step_no"] = i
    steps = [{k: s[k] for k in m.STEP_FIELDS} for s in steps]
    return CaseResult(ctx.request.case_id, status, steps, decisions)
