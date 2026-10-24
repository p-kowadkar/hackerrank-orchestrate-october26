import unittest
from collections import Counter

from .support import dataset, index
from ghostaudit import model as m
from ghostaudit.evidence.logs import parse_line


def obs(file_id, rid):
    return [o for o in index().obs if o.file_id == file_id and o.resource_id == rid]


class CoverageTests(unittest.TestCase):
    def test_no_state_bearing_record_is_dropped_silently(self):
        unknown = {f: dict(c) for f, c in index().unknown.items() if any(not k.startswith("skipped") for k in c)}
        self.assertEqual(unknown, {})

    def test_only_screenshots_are_skipped(self):
        skipped = {f for f, c in index().stats.items() if c["skipped"]}
        pngs = {f for f, r in dataset().manifest.items() if r["file_path"].endswith(".png")}
        self.assertEqual(skipped, pngs)

    def test_every_non_image_file_yields_something(self):
        ds = dataset()
        idx = index()
        for fid, row in ds.manifest.items():
            if row["file_path"].endswith(".png"):
                continue
            st = idx.stats[fid]
            self.assertGreater(st["parsed"] + st["ignored"] + st["snapshots"], 0, fid)


class FormatFactTests(unittest.TestCase):
    def test_failover_only_row_is_present(self):                    # case_05 ghost: replica holds the row
        self.assertEqual({o.state for o in obs("evidence_54", "account_005")}, {m.PRESENT})

    def test_readback_404_is_absent_and_200_is_present(self):
        self.assertEqual(obs("evidence_92", "account_3136")[0].state, m.ABSENT)
        self.assertEqual(obs("evidence_92", "account_5334")[0].state, m.PRESENT)

    def test_nulled_analytics_is_clean_and_identified_is_exposed(self):
        self.assertEqual(obs("evidence_92", "analytics_1895")[0].state, m.CLEAN)
        self.assertEqual(obs("evidence_92", "analytics_5208")[0].state, m.EXPOSED)

    def test_ledger_text_rows(self):
        self.assertEqual(obs("evidence_03", "search_052")[0].state, m.PRESENT)
        self.assertEqual(obs("evidence_03", "support_864")[0].state, m.EXPOSED)
        self.assertEqual(obs("evidence_03", "data_flow_9522")[0].state, m.ACTIVE)
        self.assertEqual(obs("evidence_03", "backup_3870")[0].state, m.RESTORABLE)

    def test_upper_case_email_in_ledger_is_tokenised_lower_case(self):
        toks = obs("evidence_03", "account_1810")[0].tokens
        self.assertIn("choi.jihoon94@gmail.com", toks)

    def test_hash_only_link_is_found(self):                         # case_12: analytics linked only by an old email hash
        toks = {t for o in index().by_rid["analytics_9914"] for t in o.tokens}
        self.assertTrue(any(len(t) == 64 for t in toks))

    def test_search_document_names_its_source_account(self):
        link = [o for o in obs("evidence_57", "account_006") if o.state == m.LINK]
        self.assertTrue(link)

    def test_marketing_contact_under_analytics_id(self):
        o = [x for x in index().by_rid["analytics_9914"] if x.rtype == m.MARKETING]
        self.assertTrue(o)

    def test_pdf_and_link_events(self):
        self.assertEqual(obs("evidence_58", "support_001")[0].rtype, m.SUPPORT_ATTACHMENT)
        self.assertEqual(obs("evidence_55", "audit_record_003")[0].rtype, m.AUDIT)
        self.assertEqual(len(index().links), 12)
        self.assertEqual(obs("evidence_18", "export_1842")[0].state, m.PRESENT)

    def test_planted_later_record_keeps_its_own_time(self):         # evidence_36: FOUND dated after the file's capture
        times = sorted(o.obs_time for o in index().by_rid["account_5043"])
        self.assertGreater(times[-1], dataset().manifest["evidence_36"]["captured_at"])


class LogDialectTests(unittest.TestCase):
    LINES = {
        "kv": '2026-09-15T11:51:19Z level=INFO service=account_service trace_id=tr-1 resource_id=account_4092 event=profile_lookup_completed rows=0 http_status=404',
        "json": '2026-09-10T08:56:20Z {"service":"account_service","trace_id":"tr-2","resource_id":"account_6633","event":"profile_lookup_completed","rows":"1","http_status":"200"}',
        "syslog": '2026-08-22T10:51:17Z <15>1 node-1 account_service tr-3 - - level=DEBUG resource_id="account_1785" event="profile_lookup_completed" rows="1" http_status="200"',
        "bracket": '2026-07-28T05:51:21Z [INFO] [account_service] [tr-4] profile_lookup_completed: resource_id="account_7947" rows="0" http_status="404"',
        "pipe": '2026-07-03T07:51:32Z | DEBUG | security_service | tr-5 | audit_record_read_completed | resource_id="audit_record_4413" rows="1"',
        "cloud": '2026-09-30T11:51:03Z requestId=tr-6 level=DEBUG function=profile_service message="resource_id=\\"account_66777\\" event=\\"profile_lookup_completed\\" rows=\\"1\\" http_status=\\"200\\""',
    }

    def test_every_dialect_parses_to_event_trace_and_resource(self):
        want = {"kv": "account_4092", "json": "account_6633", "syslog": "account_1785", "bracket": "account_7947",
                "pipe": "audit_record_4413", "cloud": "account_66777"}
        for name, line in self.LINES.items():
            rec = parse_line(line)
            self.assertIsNotNone(rec, name)
            self.assertEqual(rec["kv"]["resource_id"], want[name], name)
            self.assertTrue(rec["trace"], name)
            self.assertIn(rec["event"], ("profile_lookup_completed", "audit_record_read_completed"), name)


class StateAgreementTests(unittest.TestCase):
    """Independent cross-check: for non-account resources the worker's result tracks the real state, so parsed
    states must agree with it in nearly every case, in every evidence format. The few disagreements are the
    deliberate "recreated after a successful run" traps: exposure observed *after* the successful action."""

    def test_parsed_state_agrees_with_worker_outcome(self):
        from .support import pipeline_run
        ev = {}
        for a in dataset().activity:
            ev.setdefault(a["resource_id"], []).append((a["event_type"], a["reported_result"], a["event_time"]))
        expect = {m.ANALYTICS: ("ANONYMIZE_RECORD", m.CLEAN, m.EXPOSED), m.SUPPORT_MESSAGE: ("REDACT_RECORD", m.CLEAN, m.EXPOSED),
                  m.TOMBSTONE: ("REDACT_RECORD", m.CLEAN, m.EXPOSED)}
        ok = tot = 0
        for res in pipeline_run().results.values():
            for d in res.decisions:
                if d.obs is None or d.rtype not in expect:
                    continue
                et, good, bad = expect[d.rtype]
                events = [(r, t) for e, r, t in ev.get(d.resource_id, ()) if e == et]
                if not events:
                    continue
                succeeded = [t for r, t in events if r == "SUCCESS"]
                want = good if succeeded else bad
                tot += 1
                if d.state == want:
                    ok += 1
                else:   # only allowed disagreement: exposed again after a successful action
                    self.assertEqual((d.state, bool(succeeded)), (m.EXPOSED, True), d.resource_id)
                    self.assertGreater(d.obs.obs_time, max(succeeded), d.resource_id)
        self.assertGreater(tot, 200)
        self.assertGreaterEqual(ok / tot, 0.95)


if __name__ == "__main__":
    unittest.main()
