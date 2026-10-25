"""Clock rules and last-resort tiebreak confinement, on synthetic evidence so each rule fails in isolation."""
import unittest

from .support import dataset, pipeline_run
from ghostaudit import model as m
from ghostaudit.evidence import EvidenceIndex
from ghostaudit.planner import PlanOptions
from ghostaudit.residual import AccountMatcher, STATUS_RESULT
from ghostaudit.state import absence_proof, admissible, decide, latest_observation

AUDIT = "2026-09-15T12:00:00Z"


def O(file_id, cap, t, rid, rtype, state, tokens=()):
    return m.Obs(file_id, cap, t, rid, rtype, state, frozenset(tokens))


def idx(*obs, snapshots=()):
    return EvidenceIndex(list(obs), list(snapshots), [], {}, {})


class ClockRuleTests(unittest.TestCase):
    def test_file_captured_after_audit_is_inadmissible(self):
        o = O("evidence_90", "2026-09-17T12:00:00Z", "2026-09-15T12:00:00Z", "account_1", m.ACCOUNT, m.PRESENT)
        self.assertFalse(admissible(o, AUDIT))

    def test_record_dated_after_audit_is_ignored_even_in_a_usable_file(self):
        gone = O("evidence_36", "2026-09-15T12:00:00Z", "2026-09-15T12:00:00Z", "account_1", m.ACCOUNT, m.ABSENT)
        back = O("evidence_36", "2026-09-15T12:00:00Z", "2026-09-17T12:00:00Z", "account_1", m.ACCOUNT, m.PRESENT)
        self.assertEqual(latest_observation(idx(gone, back), "account_1", AUDIT).state, m.ABSENT)

    def test_record_dated_exactly_at_audit_counts(self):
        o = O("evidence_1", "2026-09-15T12:00:00Z", AUDIT, "account_1", m.ACCOUNT, m.ABSENT)
        self.assertTrue(admissible(o, AUDIT))

    def test_latest_observation_wins_in_both_directions(self):
        a = O("evidence_1", "2026-09-10T00:00:00Z", "2026-09-10T00:00:00Z", "account_1", m.ACCOUNT, m.PRESENT)
        b = O("evidence_2", "2026-09-14T00:00:00Z", "2026-09-14T00:00:00Z", "account_1", m.ACCOUNT, m.ABSENT)
        self.assertEqual(latest_observation(idx(a, b), "account_1", AUDIT).state, m.ABSENT)      # removed
        c = O("evidence_3", "2026-09-14T00:00:00Z", "2026-09-14T00:00:00Z", "account_2", m.ACCOUNT, m.ABSENT)
        d = O("evidence_4", "2026-09-15T00:00:00Z", "2026-09-15T00:00:00Z", "account_2", m.ACCOUNT, m.PRESENT)
        self.assertEqual(latest_observation(idx(c, d), "account_2", AUDIT).state, m.PRESENT)     # came back

    def test_link_observations_never_decide_state(self):
        o = O("evidence_1", "2026-09-10T00:00:00Z", "2026-09-10T00:00:00Z", "account_1", m.ACCOUNT, m.LINK)
        self.assertIsNone(latest_observation(idx(o), "account_1", AUDIT))

    def test_account_without_admissible_evidence_defaults_to_absent_and_audit_to_present(self):
        d = decide(idx(), "account_9", AUDIT)
        self.assertEqual((d.state, d.defaulted), (m.ABSENT, True))
        self.assertEqual(decide(idx(), "audit_record_9", AUDIT).state, m.PRESENT)
        self.assertIsNone(decide(idx(), "search_9", AUDIT))       # nothing is invented for other types

    def test_absence_proof_is_latest_admissible_covering_snapshot(self):
        s1 = m.Snapshot("evidence_1", "2026-09-01T00:00:00Z", "account_service", "2026-09-01T00:00:00Z")
        s2 = m.Snapshot("evidence_2", "2026-09-10T00:00:00Z", "account_service", "2026-09-10T00:00:00Z")
        s3 = m.Snapshot("evidence_3", "2026-09-17T00:00:00Z", "account_service", "2026-09-17T00:00:00Z")
        self.assertEqual(absence_proof(idx(snapshots=[s1, s2, s3]), "account_service", AUDIT), "evidence_2")


class TiebreakConfinementTests(unittest.TestCase):
    def test_status_mapping_is_the_documented_one(self):
        self.assertEqual(STATUS_RESULT, {"COMPLETE": "SUCCESS", "PARTIALLY_COMPLETE": "PARTIAL", "NOT_STARTED": "FAILED"})

    def test_tiebreak_never_touches_a_case_decided_by_evidence_or_elimination(self):
        run = pipeline_run()
        used = {u.case_id for u in run.tiebreak_uses}
        for cid in used:
            self.assertNotIn(run.assignments[cid].how, ("evidence",), cid)
        self.assertTrue(used)
        for cid, a in run.assignments.items():
            if a.how == "evidence":
                self.assertNotIn(cid, used)

    def test_tiebreak_is_ignored_when_it_would_remove_every_candidate(self):
        run = pipeline_run()
        for u in run.tiebreak_uses:
            self.assertTrue(0 < len(u.after) < len(u.before), u.case_id)

    def test_every_use_is_recorded_with_before_and_after(self):
        for u in pipeline_run().tiebreak_uses:
            self.assertTrue(set(u.after) <= set(u.before))
            self.assertEqual(u.resolved, len(u.after) == 1)

    def test_omit_policy_never_guesses_and_guess_policy_never_omits_a_pool(self):
        omit = pipeline_run("omit")
        self.assertFalse([a for a in omit.assignments.values() if a.how == "guess"])
        guess = pipeline_run("guess")
        self.assertFalse([a for a in guess.assignments.values() if a.how == "ambiguous"])

    def test_no_account_is_assigned_to_two_cases(self):
        run = pipeline_run()
        rids = [a.resource_id for a in run.assignments.values() if a.resource_id]
        self.assertEqual(len(rids), len(set(rids)))


class AuditWindowTests(unittest.TestCase):
    """The audit-record identity window is wider than the case window; state rules are untouched."""

    @classmethod
    def setUpClass(cls):
        from collections import defaultdict
        from .support import index, resolver
        cls.per_user = defaultdict(set)
        res = resolver()
        for o in index().obs:
            if o.rtype == m.AUDIT:
                for t in o.tokens:
                    users = res.token_users.get(t, ())
                    if len(users) == 1:
                        cls.per_user[next(iter(users))].add(o.resource_id)
        for lk in index().links:
            if lk.resource_id.startswith("audit_record"):
                cls.per_user[lk.user_id].add(lk.resource_id)

    def test_a_user_has_at_most_one_audit_record_in_all_the_evidence(self):
        self.assertGreater(len(self.per_user), 400)
        self.assertEqual(max(len(v) for v in self.per_user.values()), 1)

    def test_samples_neither_need_nor_contradict_the_wider_window(self):
        """Unlimited-window attribution equals the golden audit set for every sample, except the two ids no file contains."""
        import json, csv
        from .support import resolver
        from ghostaudit.paths import DATASET_DIR
        gold = {r["case_id"]: {s["resource_id"] for s in json.loads(r["steps_json"]) if s["resource_id"].startswith("audit_record")}
                for r in csv.DictReader(open(DATASET_DIR / "sample_output.csv", encoding="utf-8"))}
        differs = []
        for r in dataset().sample_requests:
            uid, _ = resolver().resolve(r.email)
            if self.per_user.get(uid, set()) != gold[r.case_id]:
                differs.append(r.case_id)
        self.assertEqual(sorted(differs), ["case_18", "case_20"])

    def test_late_audit_record_is_attributed_but_never_gives_state(self):
        run = pipeline_run()
        d = next(x for x in run.results["case_33"].decisions if x.resource_id == "audit_record_8486")
        self.assertIsNone(d.obs)                       # no admissible observation: state defaulted, not read from late evidence
        self.assertTrue(d.defaulted)
        step = next(s for s in run.results["case_33"].steps if s["resource_id"] == "audit_record_8486")
        self.assertEqual((step["operation"], step["evidence_id"]), ("VERIFY_RECORD_PRESENT", ""))

    def test_complete_answer_never_lists_an_uncitable_audit_step(self):
        run = pipeline_run()
        for cid, r in run.results.items():
            if r.status == "COMPLETE":
                for s in r.steps:
                    self.assertTrue(s["evidence_id"], (cid, s))


if __name__ == "__main__":
    unittest.main()
