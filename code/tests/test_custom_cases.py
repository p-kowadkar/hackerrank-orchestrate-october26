"""The hand-built evaluation cases (code/evaluation/custom_cases.py) run end to end and match their hand-derived answers."""
import unittest
from unittest import mock

from .support import dataset  # noqa: F401  (sets sys.path for the evaluation package)
from custom_cases import evaluate
from ghostaudit import model as m


class CustomCaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = evaluate()

    def test_every_custom_case_matches_its_hand_derived_answer(self):
        sc = self.result["score"]
        self.assertEqual(sc.exact_cases, sc.n_cases, [(d.case_id, d.kind, d.detail) for d in sc.discrepancies])
        self.assertEqual(sc.n_cases, 12)

    def test_the_cases_cover_the_three_layouts_and_five_dialects(self):
        notes = " ".join(self.result["world"].notes.values())
        for layout in ("Reporting-replica", "Regional-replicas", "Failover layout"):
            self.assertIn(layout, notes)
        for dialect in ("json", "syslog", "bracket", "pipe", "cloud", "kv"):
            self.assertIn(f"Log dialect `{dialect}`", notes)

    def test_every_dialect_gives_the_same_answer_shape(self):
        shapes = {tuple((s["phase"], s["operation"], s["state"], s["system_id"], bool(s["evidence_id"]))
                        for s in self.result["pred"][f"case_{n}"][1]) for n in range(905, 911)}
        self.assertEqual(len(shapes), 1)

    def test_the_clock_rule_case_really_exercises_the_rule(self):
        """Mutation check: with the clock gates switched off the planted later record and later file change the answer."""
        ungated = lambda o, audit_at: o.state != m.LINK                                   # noqa: E731
        with mock.patch("ghostaudit.state.admissible", ungated):
            mutated = evaluate()
        self.assertNotEqual(mutated["pred"]["case_911"], self.result["pred"]["case_911"])
        self.assertEqual(mutated["pred"]["case_911"][0], "INCOMPLETE")

    def test_non_deletion_requests_produce_empty_arrays(self):
        for cid in ("case_912", "case_913"):
            self.assertEqual(self.result["pred"][cid], ("NOT_APPLICABLE", []))


if __name__ == "__main__":
    unittest.main()
