import copy
import csv
import tempfile
import unittest
from pathlib import Path

from .support import CODE, dataset, pipeline_run
from ghostaudit import model as m
from ghostaudit.data import case_sort_key
from ghostaudit.output import dump_steps, validate_output, write_output
from ghostaudit.planner import CaseResult
from score import load_answers, load_derived, score, score_derived

DATASET = CODE.parent / "dataset"


class OrderingTests(unittest.TestCase):
    def test_natural_case_order(self):
        ids = ["case_100", "case_33", "case_550", "case_04"]
        self.assertEqual(sorted(ids, key=case_sort_key), ["case_04", "case_33", "case_100", "case_550"])

    def test_every_sample_answer_is_in_contract_order(self):
        for cid, (status, steps) in load_answers(DATASET / "sample_output.csv").items():
            keys = [(m.PHASES.index(s["phase"]), m.OPERATIONS.index(s["operation"]), s["system_id"], s["resource_id"]) for s in steps]
            self.assertEqual(keys, sorted(keys), cid)

    def test_operation_table_matches_the_contract(self):
        self.assertEqual(len(m.OPERATIONS), 15)
        self.assertEqual(m.OPERATIONS[0], "REPORT_REMAINING_RECORD")
        self.assertEqual(m.OPERATIONS[-1], "VERIFY_RESTORE_BLOCKED")


class WriterValidatorTests(unittest.TestCase):
    def _tmp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        return Path(d.name) / "o.csv"

    def test_full_run_is_valid_and_deterministic(self):
        ds = dataset()
        res = pipeline_run()
        results = {c: r for c, r in res.results.items() if c in {q.case_id for q in ds.requests}}
        a, b = self._tmp(), self._tmp()
        write_output(a, results)
        write_output(b, dict(reversed(list(results.items()))))
        self.assertEqual(a.read_bytes(), b.read_bytes())
        self.assertEqual(validate_output(a, ds.requests, ds.manifest), [])
        with open(a, newline="", encoding="utf-8") as fh:
            rows = list(csv.reader(fh))
        self.assertEqual(rows[0], ["case_id", "deletion_status", "steps_json"])
        self.assertEqual(len(rows) - 1, 518)

    def test_non_applicable_rows_are_empty_arrays(self):
        res = pipeline_run()
        na = [r for r in res.results.values() if r.status == "NOT_APPLICABLE"]
        self.assertEqual(len(na), 10)
        self.assertTrue(all(r.steps == [] for r in na))

    def test_validator_catches_each_kind_of_break(self):
        ds = dataset()
        res = pipeline_run()
        base = {c: r for c, r in res.results.items() if c in {q.case_id for q in ds.requests}}
        inc = next(c for c, r in base.items() if r.status == "INCOMPLETE" and len(r.steps) > 4)
        mutations = {
            "step_no": lambda s: s.__setitem__(1, dict(s[1], step_no=9)),
            "remediation evidence": lambda s: [x.update(evidence_id="evidence_01") for x in s if x["phase"] == "REMEDIATION"][:1],
            "order": lambda s: s.reverse(),
            "unknown evidence": lambda s: s[0].update(evidence_id="evidence_9999"),
        }
        for name, mut in mutations.items():
            broken = dict(base)
            r = base[inc]
            steps = copy.deepcopy(r.steps)
            mut(steps)
            broken[inc] = CaseResult(inc, r.status, steps)
            p = self._tmp()
            write_output(p, broken)
            self.assertTrue(validate_output(p, ds.requests, ds.manifest), name)

    def test_validator_rejects_missing_rows_and_bad_header(self):
        ds = dataset()
        p = self._tmp()
        p.write_text("case_id,status\ncase_33,COMPLETE\n", encoding="utf-8")
        self.assertGreaterEqual(len(validate_output(p, ds.requests, ds.manifest)), 2)

    def test_citations_never_point_after_audit_at(self):
        ds = dataset()
        for q in ds.all_requests:
            for s in pipeline_run().results[q.case_id].steps:
                if s["evidence_id"]:
                    self.assertLessEqual(ds.manifest[s["evidence_id"]]["captured_at"], q.audit_at, (q.case_id, s))


class ScorerTests(unittest.TestCase):
    def setUp(self):
        self.gold = load_answers(DATASET / "sample_output.csv")

    def test_golden_scores_perfectly_against_itself(self):
        sc = score(self.gold, self.gold)
        self.assertEqual((sc.status_correct, sc.exact_cases, sc.fp, sc.fn, len(sc.discrepancies)), (32, 32, 0, 0, 0))

    def test_dropping_a_step_lowers_recall_only(self):
        pred = copy.deepcopy(self.gold)
        st, steps = pred["case_11"]
        pred["case_11"] = (st, steps[:-1])
        sc = score(pred, self.gold)
        self.assertEqual((sc.fn, sc.fp), (1, 0))
        self.assertEqual(sc.status_correct, 32)
        self.assertTrue(any(d.kind == "MISSING" for d in sc.discrepancies))

    def test_wrong_evidence_is_a_field_error_not_a_missing_step(self):
        pred = copy.deepcopy(self.gold)
        st, steps = pred["case_05"]
        steps[0] = dict(steps[0], evidence_id="evidence_01")
        sc = score(pred, self.gold)
        self.assertTrue(any(d.kind == "FIELD" and "evidence_id" in d.detail for d in sc.discrepancies))
        self.assertEqual(sc.key_prf()[1], 1.0)          # identification still perfect
        self.assertLess(sc.field_hits["evidence_id"], sc.field_total["evidence_id"])

    def test_status_flip_is_reported(self):
        pred = copy.deepcopy(self.gold)
        pred["case_13"] = ("COMPLETE", pred["case_13"][1])
        sc = score(pred, self.gold)
        self.assertEqual(sc.status_correct, 31)
        self.assertTrue(any(d.kind == "STATUS" and d.case_id == "case_13" for d in sc.discrepancies))

    def test_order_swap_is_reported_as_an_ordering_error(self):
        pred = copy.deepcopy(self.gold)
        st, steps = pred["case_11"]
        steps[0], steps[1] = steps[1], steps[0]
        sc = score(pred, self.gold)
        self.assertTrue(any(d.kind == "ORDER" and d.case_id == "case_11" for d in sc.discrepancies))
        self.assertEqual(sc.key_prf()[2], 1.0)
        self.assertEqual(sc.exact_cases, 31)

    def test_derived_cases_are_scored_separately_and_labelled(self):
        derived = load_derived(CODE / "evaluation" / "derived_cases.md")
        self.assertEqual(len(derived), 12)
        rows = score_derived({c: (r.status, r.steps) for c, r in pipeline_run().results.items()}, derived)
        self.assertEqual(len(rows), 12)
        text = (CODE / "evaluation" / "derived_cases.md").read_text(encoding="utf-8")
        self.assertIn("UNVERIFIED", text)
        self.assertIn("never enter the headline", text)


class IntegrityTests(unittest.TestCase):
    def test_pipeline_never_reads_the_golden_answers(self):
        for path in (CODE / "ghostaudit").rglob("*.py"):
            self.assertNotIn("sample_output", path.read_text(encoding="utf-8"), str(path))
        self.assertNotIn("sample_output", (CODE / "main.py").read_text(encoding="utf-8"))

    def test_no_account_naming_convention_in_the_source(self):
        for path in (CODE / "ghostaudit").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("account_00", text, str(path))
            self.assertNotIn(":03d", text, str(path))

    def test_headline_excludes_derived_cases(self):
        text = (CODE / "evaluation" / "main.py").read_text(encoding="utf-8")
        self.assertIn("UNVERIFIED", text)
        self.assertIn("Headline numbers use **only**", text)


if __name__ == "__main__":
    unittest.main()
