"""The two dataset-construction heuristics are switchable, counted, and never change what evidence decides."""
import unittest
from collections import Counter

from .support import dataset
from ghostaudit.pipeline import run
from ghostaudit.planner import PlanOptions


def go(**kw):
    ds = dataset()
    return run(ds, ds.all_requests, PlanOptions(**kw))


def verdicts(res):
    return {cid: r.status for cid, r in res.results.items()}


class SwitchTests(unittest.TestCase):
    def test_defaults_use_both_heuristics_and_count_them(self):
        res = go()
        self.assertTrue(res.tiebreak_uses)
        self.assertTrue(res.cadence_uses)
        self.assertTrue(res.cadence)

    def test_cadence_can_be_switched_off(self):
        on, off = go(), go(use_cadence=False)
        self.assertEqual((off.cadence, off.cadence_uses), (set(), []))
        guesses = lambda r: sum(1 for a in r.analytics.values() if a.how == "guess")   # noqa: E731
        self.assertGreater(guesses(off), guesses(on))             # the heuristic is what removes those guesses
        self.assertEqual(verdicts(on), verdicts(off))              # and it never moves a case-level verdict

    def test_tiebreak_can_be_switched_off(self):
        on, off = go(), go(use_tiebreak=False)
        self.assertEqual(off.tiebreak_uses, [])
        self.assertNotIn("tiebreak", Counter(a.how for a in off.assignments.values()))
        self.assertEqual(verdicts(on), verdicts(off))

    def test_tiebreak_never_overrides_evidence(self):
        on, off = go(), go(use_tiebreak=False)
        for cid, a in on.assignments.items():
            if a.how == "evidence":
                self.assertEqual(off.assignments[cid].resource_id, a.resource_id)

    def test_hybrid_guesses_only_with_two_or_fewer_candidates(self):
        res = go(ambiguity="hybrid")
        for table in (res.assignments, res.analytics):
            for cid, a in table.items():
                if a.how == "guess":
                    self.assertLessEqual(len(a.candidates), 2, cid)
                if a.how == "ambiguous":
                    self.assertGreaterEqual(len(a.candidates), 3, cid)

    def test_every_residual_candidate_is_verified_absent(self):
        """Why the choice cannot matter: a candidate that no evidence names has no admissible observation, so it is absent."""
        from ghostaudit.state import decide
        res = go(ambiguity="hybrid")
        reqs = {r.case_id: r for r in dataset().all_requests}
        checked = 0
        for cid, a in res.assignments.items():
            if a.how in ("guess", "ambiguous"):
                for cand in a.candidates:
                    d = decide(res.index, cand, reqs[cid].audit_at)
                    self.assertFalse(d.violating, (cid, cand))
                    checked += 1
        self.assertGreater(checked, 100)

    def test_candidate_choice_never_changes_a_verdict(self):
        """Residual accounts are verified absent whichever candidate is picked, so omit/hybrid/guess agree on every verdict."""
        base = verdicts(go(ambiguity="hybrid"))
        for pol in ("omit", "guess"):
            self.assertEqual(verdicts(go(ambiguity=pol)), base, pol)


if __name__ == "__main__":
    unittest.main()
