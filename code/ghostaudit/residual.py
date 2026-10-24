"""Resolving the account of a case when no evidence names it (a deleted account leaves no identifier behind).

Order of precedence, strictly:
  1. evidence: the account appears with one of the user's identity tokens inside the case window;
  2. elimination: among DELETE_RECORD worker events shortly before reported_at, drop accounts owned by other users
     and accounts already assigned to other cases; accept a unique survivor, repeat until stable;
  3. last-resort tiebreak: prefer candidates whose worker result agrees with the case's reported_status
     (SUCCESS<->COMPLETE, PARTIAL<->PARTIALLY_COMPLETE, FAILED<->NOT_STARTED). It only narrows a set that is still
     tied, it is ignored if it would empty the set, and every use is recorded;
  4. ambiguity policy: 'guess' (deterministic injective pick), 'omit', or 'hybrid' (guess only while at most
     HYBRID_MAX_GUESS candidates remain, omit beyond that). A case left with a single candidate only because an
     earlier case guessed is reported as a guess, not as elimination.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import model as m
from .evidence import EvidenceIndex
from .identity import IdentityResolver
from .state import file_number, latest_observation
from bisect import bisect_left, bisect_right

from .timeutil import epoch, minutes_between

STATUS_RESULT = {"COMPLETE": "SUCCESS", "PARTIALLY_COMPLETE": "PARTIAL", "NOT_STARTED": "FAILED"}
POOL_BEFORE_MIN = 80      # worker event happens up to 80 minutes before reported_at ...
POOL_AFTER_MIN = 10       # ... or a few minutes after it
HYBRID_MAX_GUESS = 2      # 'hybrid' policy: guess while at most this many candidates remain (backtest: ~49% at 2, ~29% at 3)


def may_guess(policy: str, remaining: int) -> bool:
    return policy == "guess" or (policy == "hybrid" and remaining <= HYBRID_MAX_GUESS)


@dataclass
class AccountAssignment:
    resource_id: str | None
    how: str                                   # evidence | elimination | tiebreak | guess | ambiguous | none
    candidates: tuple = ()
    notes: list = field(default_factory=list)


@dataclass
class TiebreakUse:
    case_id: str
    before: tuple
    after: tuple
    resolved: bool                             # narrowed to a single account


class AccountMatcher:
    def __init__(self, activity: list, index: EvidenceIndex, resolver: IdentityResolver, ambiguity: str = "guess"):
        self.index = index
        self.resolver = resolver
        self.ambiguity = ambiguity
        self.events = {}                        # rid -> list of (time, result)
        flat = []
        for r in activity:
            if r["event_type"] == "DELETE_RECORD" and r["target_system"] == "account_service":
                self.events.setdefault(r["resource_id"], []).append((r["event_time"], r["reported_result"]))
                flat.append((epoch(r["event_time"]), r["event_time"], r["resource_id"]))
        flat.sort()
        self._flat = flat
        self._epochs = [f[0] for f in flat]
        self.owners = self._owners()
        self.tiebreak_uses: list = []

    def _owners(self) -> dict:
        owners = {}
        for rid, obs in self.index.by_rid.items():
            if not rid.startswith("account_"):
                continue
            users = set()
            for o in obs:
                for t in o.tokens:
                    tu = self.resolver.token_users.get(t, ())
                    if len(tu) == 1:
                        users.update(tu)
            if users:
                owners[rid] = users
        return owners

    def _pool(self, ctx) -> list:
        rep = epoch(ctx.request.reported_at)
        lo = bisect_left(self._epochs, rep - POOL_BEFORE_MIN * 60)
        hi = bisect_right(self._epochs, rep + POOL_AFTER_MIN * 60)
        seen, out = set(), []
        for _e, t, rid in self._flat[lo:hi]:
            if rid not in seen:
                seen.add(rid)
                out.append((t, rid))
        owned_elsewhere = lambda rid: bool(self.owners.get(rid)) and ctx.user_id not in self.owners[rid]  # noqa: E731
        return [rid for t, rid in sorted(out) if not owned_elsewhere(rid)]

    def _result(self, rid: str, ctx):
        times = sorted(self.events.get(rid, []), key=lambda e: abs(minutes_between(ctx.request.reported_at, e[0])))
        return times[0][1] if times else None

    def assign(self, contexts: list) -> dict:
        """contexts: deletion cases (ordered). Returns case_id -> AccountAssignment."""
        out: dict = {}
        taken: set = set()
        pools: dict = {}
        for ctx in contexts:                                              # 1. evidence
            direct = sorted(r for r in ctx.direct if r.startswith("account_"))
            if direct:
                best = self._best_direct(ctx, direct)
                out[ctx.request.case_id] = AccountAssignment(best, "evidence", tuple(direct),
                                                             ["several accounts linked by evidence"] if len(direct) > 1 else [])
                taken.add(best)
            else:
                pools[ctx.request.case_id] = self._pool(ctx)
        by_id = {c.request.case_id: c for c in contexts}
        self._eliminate(pools, taken, out)                                # 2. elimination
        progress = True
        while progress:                                                   # 3. last-resort tiebreak
            progress = False
            for cid in sorted(pools, key=lambda c: by_id[c].request.number):
                if cid in out:
                    continue
                cands = [c for c in pools[cid] if c not in taken]
                if len(cands) < 2:
                    continue
                want = STATUS_RESULT.get(by_id[cid].request.reported_status)
                pref = [c for c in cands if self._result(c, by_id[cid]) == want]
                if 0 < len(pref) < len(cands):
                    self.tiebreak_uses.append(TiebreakUse(cid, tuple(cands), tuple(pref), len(pref) == 1))
                    pools[cid] = pref
                    if len(pref) == 1:
                        out[cid] = AccountAssignment(pref[0], "tiebreak", tuple(cands))
                        taken.add(pref[0])
                        self._eliminate(pools, taken, out)
                    progress = True
                    break
        guessed: set = set()                                               # accounts taken by a guess, not by evidence
        for cid in sorted(pools, key=lambda c: by_id[c].request.number):  # 4. ambiguity policy
            if cid in out:
                continue
            firm = [c for c in pools[cid] if c not in taken]               # candidates left without counting guesses
            live = [c for c in firm if c not in guessed]
            if not live:
                out[cid] = AccountAssignment(None, "none", ())
            elif len(firm) == 1:
                out[cid] = AccountAssignment(live[0], "elimination", tuple(firm))
                taken.add(live[0])
            elif may_guess(self.ambiguity, len(firm)):
                pick = live[0]
                note = f"{len(firm)} candidates; deterministic pick"
                if len(live) == 1:
                    note += " (the only one an earlier guess left free)"
                out[cid] = AccountAssignment(pick, "guess", tuple(firm), [note])
                guessed.add(pick)
            else:
                out[cid] = AccountAssignment(None, "ambiguous", tuple(firm))
        return out

    def _best_direct(self, ctx, direct: list) -> str:
        if len(direct) == 1:
            return direct[0]
        def key(rid):
            o = latest_observation(self.index, rid, ctx.request.audit_at)
            return (o is not None, o.obs_time if o else "", -file_number(o.file_id) if o else 0)
        return max(direct, key=key)

    def _eliminate(self, pools: dict, taken: set, out: dict):
        while True:
            singles = {}
            for cid, pool in pools.items():
                if cid in out:
                    continue
                cands = [c for c in pool if c not in taken]
                if len(cands) == 1:
                    singles.setdefault(cands[0], []).append(cid)
            fresh = {rid: cids for rid, cids in singles.items() if len(cids) == 1}
            if not fresh:
                return
            for rid, (cid,) in sorted(fresh.items()):
                out[cid] = AccountAssignment(rid, "elimination", (rid,))
                taken.add(rid)


# ------------------------------------------------------------------------------------------ anonymized analytics
CADENCE_MIN_COUNT = 5            # a gap must be seen at least this often between directly linked siblings
ANALYTICS_BEFORE_MIN = 35        # the anonymization event happens up to 35 minutes before reported_at ...
ANALYTICS_AFTER_MIN = 5          # ... or a few minutes after it


def learn_cadence(sibling_times: list) -> set:
    """sibling_times: for each case, the sorted worker-event times (ISO) of its directly linked compliant siblings.
    The cadence is the set of gaps (seconds) between consecutive events that occurs often enough to be systematic."""
    from collections import Counter
    from .timeutil import parse
    gaps = Counter()
    for times in sibling_times:
        for a, b in zip(times, times[1:]):
            gaps[int((parse(b) - parse(a)).total_seconds())] += 1
    return {g for g, c in gaps.items() if c >= CADENCE_MIN_COUNT}


def _cadence_sums(cadence: set) -> set:
    sums = set(cadence)
    for a in cadence:
        for b in cadence:
            sums.add(a + b)
            for c in cadence:
                sums.add(a + b + c)
    return sums


@dataclass
class CadenceUse:
    case_id: str
    before: tuple
    after: tuple


class AnalyticsMatcher:
    """Matches the identifier-free anonymized analytics profile of a case to an ANONYMIZE_RECORD worker event.

    A candidate must (a) have a successful anonymization event shortly before reported_at, (b) be observed as
    anonymized (no identifiers) in admissible evidence, and (c) not be claimed by another case. If the case has
    directly linked compliant siblings (support, flow, backup, tombstone), the learned worker cadence must connect
    the analytics event to the first sibling event, to the second. Leftover ties go to the ambiguity policy.
    """

    def __init__(self, activity: list, index: EvidenceIndex, cadence: set, ambiguity: str = "guess"):
        self.index = index
        self.ambiguity = ambiguity
        self.sums = _cadence_sums(cadence)
        self.events = {}                               # rid -> sorted event times (SUCCESS only)
        for r in activity:
            if r["event_type"] == "ANONYMIZE_RECORD" and r["reported_result"] == "SUCCESS":
                self.events.setdefault(r["resource_id"], []).append(r["event_time"])
        self.cadence_uses: list = []

    def _pool(self, ctx) -> list:
        out = []
        for rid, times in self.events.items():
            for t in times:
                if -ANALYTICS_AFTER_MIN <= minutes_between(ctx.request.reported_at, t) <= ANALYTICS_BEFORE_MIN:
                    o = latest_observation(self.index, rid, ctx.request.audit_at)
                    if o is not None and o.rtype == m.ANALYTICS and o.state == m.CLEAN and not o.tokens:
                        out.append((t, rid))
                    break
        return [rid for _t, rid in sorted(out)]

    def assign(self, contexts: list, has_analytics: set, sibling_times: dict) -> dict:
        """-> case_id -> AccountAssignment-like (resource_id, how, candidates). `has_analytics`: cases that need no id-less analytics (INCOMPLETE, or already linked)."""
        from .timeutil import parse
        pools = {c.request.case_id: self._pool(c) for c in contexts if c.request.case_id not in has_analytics}
        pools = {cid: p for cid, p in pools.items() if p}
        out, taken = {}, set()
        # (b) cadence: the event must sit exactly one/two/three cadence steps before the first sibling event
        for cid in sorted(pools, key=lambda c: int(c.split("_")[1])):
            sib = sibling_times.get(cid)
            if not sib or len(pools[cid]) < 2:
                continue
            first = sib[0]
            ok = [rid for rid in pools[cid]
                  if any(int((parse(first) - parse(t)).total_seconds()) in self.sums for t in self.events[rid])]
            if 0 < len(ok) < len(pools[cid]):
                self.cadence_uses.append(CadenceUse(cid, tuple(pools[cid]), tuple(ok)))
                pools[cid] = ok
        # elimination of unique, unconflicted candidates
        while True:
            singles = {}
            for cid, pool in pools.items():
                if cid in out:
                    continue
                cands = [c for c in pool if c not in taken]
                if len(cands) == 1:
                    singles.setdefault(cands[0], []).append(cid)
            fresh = {rid: cids for rid, cids in singles.items() if len(cids) == 1}
            if not fresh:
                break
            for rid, (cid,) in sorted(fresh.items()):
                out[cid] = AccountAssignment(rid, "elimination", (rid,))
                taken.add(rid)
        guessed: set = set()
        for cid in sorted(pools, key=lambda c: int(c.split("_")[1])):
            if cid in out:
                continue
            firm = [c for c in pools[cid] if c not in taken]
            live = [c for c in firm if c not in guessed]
            if not live:
                continue
            if len(firm) == 1:
                out[cid] = AccountAssignment(live[0], "elimination", tuple(firm))
                taken.add(live[0])
            elif may_guess(self.ambiguity, len(firm)):
                out[cid] = AccountAssignment(live[0], "guess", tuple(firm), [f"{len(firm)} candidates; deterministic pick"])
                guessed.add(live[0])
            else:
                out[cid] = AccountAssignment(None, "ambiguous", tuple(firm))
        return out
