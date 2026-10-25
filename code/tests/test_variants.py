"""Sprint 3: the eight evidence variants no sample answer exercises (three replica layouts, five log dialects).

Each check is an invariant measured on the data itself or a cross-format consistency check, so the variants are held to
the same standard as the formats the samples cover."""
import unittest
from collections import Counter

from .support import dataset, pipeline_run
from coverage import (EVAL_ONLY_LOGS, EVAL_ONLY_REPLICAS, cross_format, family_of, ghost_check, replica_report,
                      worker_agreement)
from ghostaudit import model as m
from ghostaudit.evidence.logs import parse_line


def files_of(*families):
    ds = dataset()
    return [fid for fid, row in ds.manifest.items() if family_of(row["file_path"]) in families]


class LogDialectFileTests(unittest.TestCase):
    EXPECT = {"structured_service_events": "json", "syslog_archive": "syslog", "application_trace": "bracket",
              "operations_stream": "pipe", "cloud_runtime_export": "cloud"}

    def test_each_variant_family_has_exactly_one_dialect_and_the_five_differ(self):
        ds = dataset()
        seen = {}
        for fam, want in self.EXPECT.items():
            files = files_of(fam)
            self.assertTrue(files, fam)
            for fid in files:
                c = Counter()
                for line in ds.evidence_path(fid).read_text(encoding="utf-8").splitlines():
                    rec = parse_line(line)
                    self.assertIsNotNone(rec, f"{fid}: unparsable line {line[:80]!r}")
                    c[rec["dialect"]] += 1
                self.assertEqual(set(c), {want}, fid)
            seen[fam] = want
        self.assertEqual(len(set(seen.values())), 5)

    def test_every_variant_log_line_is_classified(self):
        res = pipeline_run()
        for fid in files_of(*EVAL_ONLY_LOGS):
            st = res.index.stats[fid]
            self.assertEqual(st["unknown"], 0, fid)
            self.assertGreater(st["parsed"], 0, fid)
            lines = len([ln for ln in dataset().evidence_path(fid).read_text(encoding="utf-8").splitlines() if ln.strip()])
            self.assertGreaterEqual(lines, st["parsed"] + st["ignored"], fid)     # nothing counted twice

    def test_trace_ids_do_not_mix_resources_in_the_variant_logs(self):
        """Tokens are shared inside a trace, so a trace that touched two resources would leak identity between them."""
        from collections import defaultdict
        ds = dataset()
        from ghostaudit.evidence.logs import NOISE, STARTED
        for fid in files_of(*EVAL_ONLY_LOGS):
            traces = defaultdict(set)
            for line in ds.evidence_path(fid).read_text(encoding="utf-8").splitlines():
                rec = parse_line(line)
                rid = rec["kv"].get("resource_id")
                if rec["event"] not in NOISE and rec["event"] not in STARTED and rid:
                    traces[rec["trace"]].add(rid)
            self.assertTrue(all(len(v) == 1 for v in traces.values()), fid)


class ReplicaLayoutTests(unittest.TestCase):
    def test_drift_means_the_same_thing_in_every_layout(self):
        rows, ghosts = replica_report(dataset())
        self.assertEqual(len(rows), 11)
        self.assertGreaterEqual(sum(r["eval_only"] for r in rows), 6)       # reporting x2, regional x3, failover x1
        for r in rows:
            self.assertEqual(r["content_diffs"], 0, r["fid"])               # shared rows are byte-identical
            self.assertEqual(r["late"], 0, r["fid"])                        # no row is dated after its snapshot
            self.assertLessEqual(set(r["ghost_kinds"]), {"customer_profiles"}, r["fid"])
        self.assertEqual(len(ghosts), sum(r["ghosts"] for r in rows))

    def test_every_ghost_account_is_reported_for_its_owner(self):
        ds = dataset()
        _rows, ghosts = replica_report(ds)
        checks = ghost_check(ds, pipeline_run(), ghosts)
        self.assertGreaterEqual(len(checks), 10)
        self.assertTrue(all(found for *_x, found in checks), [c for c in checks if not c[-1]])
        self.assertTrue(all(status == "INCOMPLETE" for _f, _r, _c, status, _found in checks))

    def test_ghost_in_the_eval_only_layouts_is_present_in_the_parsed_evidence(self):
        res = pipeline_run()
        ds = dataset()
        _rows, ghosts = replica_report(ds)
        eval_only = [g for g in ghosts if family_of(ds.manifest[g[0]]["file_path"]) in EVAL_ONLY_REPLICAS]
        self.assertGreaterEqual(len(eval_only), 6)
        for fid, _table, rid, _coll, _rec in eval_only:
            states = {o.state for o in res.index.by_rid[rid] if o.file_id == fid}
            self.assertEqual(states, {m.PRESENT}, (fid, rid))


class CrossFormatTests(unittest.TestCase):
    def test_formats_agree_on_the_same_resource(self):
        cf = cross_format(pipeline_run())
        agree = sum(c["agree"] for c in cf["stats"].values())
        differ = sum(c["differ"] for c in cf["stats"].values())
        self.assertGreater(agree, 150)
        self.assertGreaterEqual(agree / (agree + differ), 0.95)
        # the only disagreement is the support id seen as ticket in one file and attachment in a later-captured one
        kinds = {frozenset((e[2], e[5])) for ex in cf["examples"].values() for e in ex}
        self.assertEqual(kinds, {frozenset((m.SUPPORT_ATTACHMENT, m.SUPPORT_MESSAGE))})

    def test_worker_outcome_never_contradicts_a_variant_file_except_recreated_exposure(self):
        wa = worker_agreement(dataset(), pipeline_run())
        for fam, c in wa.items():
            self.assertEqual(c["differ"], 0, fam)
        # application_trace files exist only as late partner exports (identity use, they decide no case); the other
        # seven variants decide cases and are all covered by this independent check
        decided = [f for f in EVAL_ONLY_LOGS + EVAL_ONLY_REPLICAS if f != "application_trace"]
        for fam in decided:
            self.assertIn(fam, wa)
            self.assertGreater(sum(wa[fam].values()), 0, fam)

    def test_application_trace_logs_are_late_partner_files_only(self):
        res = pipeline_run()
        ds = dataset()
        used = {d.obs.file_id for r in res.results.values() for d in r.decisions if d.obs}
        for fid in files_of("application_trace"):
            self.assertNotIn(fid, used, fid)
            cap = ds.manifest[fid]["captured_at"]
            # every record in them is also visible in another, earlier file of the same batch or is identity-only
            audit_dates = {r.audit_at for r in ds.all_requests}
            self.assertFalse(any(a <= cap and (a >= cap[:10] + "T00:00:00Z") for a in audit_dates), fid)


if __name__ == "__main__":
    unittest.main()
