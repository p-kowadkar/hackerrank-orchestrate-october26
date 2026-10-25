"""Sprint 4: the model interface, its four backends, the validators, the ledger and the run manifest.

No test makes a network call: the live backend is exercised with an injected fake transport, and the test suite sets
GHOSTAUDIT_OFFLINE=1 so the default transport would refuse to open a socket anyway."""
import contextlib
import copy
import hashlib
import io
import importlib.util
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from .support import CODE, dataset, pipeline_run
from ghostaudit import model as m
from ghostaudit.evidence.common import Sink
from ghostaudit.evidence.screens import (RECORD_TYPES, FACT_KEYS, ScreenError, row_state, screen_to_observations,
                                         validate_screen)
from llm.compare import compare_all, diff_readings, render as render_agreement
from llm.factory import make_backend, new_run_id
from llm.fixtures import FIXTURE_ROOT, parse_fixture, path_for, render_fixture
from llm.interface import (FixtureMissing, LLMError, LLMRequest, LLMResult, LLMUnavailable, LLMValidationError, Usage)
from llm.manifest import other_rows, parse_manifest, render_manifest, render_usage_report
from llm.off import OffBackend
from llm.offline import offline_reader, run_replay
from llm.openrouter import (KEY_ENV, NetworkDisabled, LiveNotConfigured, OpenRouterBackend, key_is_configured,
                            urllib_transport)
from llm.prompts import load_prompt
from llm.reader import IntentFallback, ScreenshotReader
from llm.record import RecordBackend
from llm.replay import ReplayBackend
from llm.schemas import validate
from llm.usage import COLUMNS, Ledger, LedgerError

STEP = "screenshot_transcribe"


def load_cli():
    """code/main.py by path: `import main` would find code/evaluation/main.py first."""
    spec = importlib.util.spec_from_file_location("cli_main", CODE / "main.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def good_screen(**selected_facts):
    facts = {"enabled": None, "restore_blocked": None, "identifiable": None, "status": None, "expires_at": None}
    facts.update(selected_facts)
    return {"screen": "Test > Page", "rows": [
        {"record_type": "SEARCH", "resource_id": "search_1", "label": "A", "selected": True, "identifiers": ["a@example.org"],
         "facts": dict(facts)},
        {"record_type": "SEARCH", "resource_id": "search_2", "label": None, "selected": False, "identifiers": [],
         "facts": {k: None for k in FACT_KEYS}}]}


def api_payload(data, cost=0.0123, prompt=900, completion=140, model="vendor/model-x", with_usage=True):
    p = {"id": "gen-abc", "model": model, "choices": [{"message": {"content": json.dumps(data)}}]}
    if with_usage:
        p["usage"] = {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": prompt + completion}
        if cost is not None:
            p["usage"]["cost"] = cost
    return p


class FakeTransport:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def __call__(self, url, headers, body, timeout=120.0):
        self.calls.append((url, headers, json.loads(body)))
        status, payload = self.responses.pop(0)
        return status, payload if isinstance(payload, str) else json.dumps(payload)


def request(key="evidence_09", image=None):
    return LLMRequest(STEP, key, "system text", "task text", image)


class FixtureTests(unittest.TestCase):
    def test_one_transcribed_fixture_per_screenshot_and_each_validates(self):
        pngs = sorted(f for f, r in dataset().manifest.items() if r["file_path"].endswith(".png"))
        files = sorted(p.stem for p in (FIXTURE_ROOT / "transcribed" / STEP).glob("*.md"))
        self.assertEqual(files, pngs)
        self.assertEqual(len(pngs), 11)
        for fid in pngs:
            res = parse_fixture(path_for(FIXTURE_ROOT, "transcribed", STEP, fid).read_text(encoding="utf-8"), "transcribed")
            self.assertEqual((res.origin, res.usage, res.model), ("transcribed", None, ""))

    def test_transcribed_fixtures_carry_no_usage_numbers(self):
        for p in (FIXTURE_ROOT / "transcribed").rglob("*.md"):
            head = p.read_text(encoding="utf-8").split("\n---\n")[0]
            for k in ("prompt_tokens", "completion_tokens", "total_tokens", "cost_usd"):
                self.assertNotIn(k, head, p.name)

    def test_a_transcribed_fixture_with_usage_is_rejected(self):
        text = path_for(FIXTURE_ROOT, "transcribed", STEP, "evidence_09").read_text(encoding="utf-8")
        text = text.replace("origin: transcribed\n", "origin: transcribed\nprompt_tokens: 12\n", 1)
        with self.assertRaises(LLMValidationError):
            parse_fixture(text, "transcribed")

    def test_a_recorded_fixture_must_carry_usage_and_round_trips(self):
        res = LLMResult(STEP, "evidence_09", good_screen(), "recorded", "vendor/model-x", "openrouter", "gen-1",
                        Usage(10, 5, 15, 0.5, "api"))
        text = render_fixture(res, {"run_id": "run-1"})
        back = parse_fixture(text, "recorded")
        self.assertEqual((back.usage.total_tokens, back.usage.cost_usd, back.model), (15, 0.5, "vendor/model-x"))
        with self.assertRaises(LLMValidationError):
            parse_fixture(text.replace("total_tokens: 15\n", "").replace("prompt_tokens: 10\n", "").replace(
                "completion_tokens: 5\n", "").replace("cost_usd: 0.5\n", ""), "recorded")


class ReplayAndOffTests(unittest.TestCase):
    def test_replay_serves_the_transcription_without_usage(self):
        r = ReplayBackend().run(request("evidence_09"))
        self.assertEqual((r.origin, r.usage), ("transcribed", None))
        self.assertEqual(r.data["rows"][0]["resource_id"], "search_428")

    def test_replay_never_fabricates_a_missing_answer(self):
        with self.assertRaises(FixtureMissing):
            ReplayBackend().run(request("evidence_99"))
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FixtureMissing):
                ReplayBackend(Path(tmp)).run(request("evidence_09"))

    def test_off_backend_is_unavailable(self):
        with self.assertRaises(LLMUnavailable):
            OffBackend().run(request())

    def test_off_mode_leaves_every_screenshot_unread_and_the_run_still_completes(self):
        reader = ScreenshotReader(OffBackend())
        res = run_replay(dataset(), dataset().requests, images=reader)
        self.assertEqual(len(reader.unread), 11)
        self.assertEqual(res.results["case_35"].status, "COMPLETE")        # without the screenshot the answer is the old one

    def test_replay_mode_reads_all_screenshots_and_changes_the_hero_verdicts(self):
        reader = offline_reader()
        res = run_replay(dataset(), dataset().requests, images=reader)
        self.assertEqual((len(reader.calls), reader.unread, reader.problems), (11, [], []))
        self.assertEqual({c.origin for c in reader.calls}, {"transcribed"})
        steps = res.results["case_35"].steps
        self.assertEqual(res.results["case_35"].status, "INCOMPLETE")
        self.assertIn(("REPORT_REMAINING_RECORD", "search_428", "evidence_09"),
                      {(s["operation"], s["resource_id"], s["evidence_id"]) for s in steps})
        self.assertNotIn("search_1874", {s["resource_id"] for s in steps})        # the decoy row is never an observation


class ValidationTests(unittest.TestCase):
    def problems(self, data):
        with self.assertRaises(ScreenError) as cm:
            validate_screen(data)
        return " | ".join(cm.exception.problems)

    def test_a_good_structure_passes(self):
        self.assertEqual(validate_screen(good_screen())["screen"], "Test > Page")

    def test_every_kind_of_malformed_answer_is_rejected_with_a_reason(self):
        def mutate(f):
            d = good_screen()
            f(d)
            return d
        cases = {
            "not an object": ("[]", "not an object"),
            "unknown record type": (mutate(lambda d: d["rows"][0].update(record_type="WIDGET")), "record_type"),
            "two selected rows": (mutate(lambda d: d["rows"][1].update(selected=True)), "exactly one row must be selected"),
            "no selected row": (mutate(lambda d: d["rows"][0].update(selected=False)), "exactly one row must be selected"),
            "id does not fit the type": (mutate(lambda d: d["rows"][0].update(resource_id="account_5")), "does not fit"),
            "id is not an id": (mutate(lambda d: d["rows"][0].update(resource_id="CS-5034")), "not a resource id"),
            "extra key on a row": (mutate(lambda d: d["rows"][0].update(extra=1)), "keys must be exactly"),
            "extra top-level key": (mutate(lambda d: d.update(verdict="delete")), "unknown top-level keys"),
            "empty rows": ({"screen": "x", "rows": []}, "rows must be a non-empty list"),
            "bad expiry": (mutate(lambda d: d["rows"][0]["facts"].update(expires_at="25 Jun 2026")), "ISO-8601"),
            "fact of wrong type": (mutate(lambda d: d["rows"][0]["facts"].update(enabled="yes")), "wrong type"),
            "missing fact key": (mutate(lambda d: d["rows"][0]["facts"].pop("status")), "facts keys must be exactly"),
            "identifiers not strings": (mutate(lambda d: d["rows"][0].update(identifiers=[1])), "list of strings"),
            "selected OTHER": (mutate(lambda d: d["rows"][0].update(record_type="OTHER", resource_id=None)), "OTHER"),
            "data flow without enabled": (mutate(lambda d: d["rows"][0].update(record_type="DATA_FLOW", resource_id="data_flow_1")),
                                          "facts.enabled must be true or false"),
        }
        for name, (data, needle) in cases.items():
            with self.subTest(name):
                self.assertIn(needle, self.problems(data))

    def test_the_schema_step_validators_wrap_errors_as_llm_validation_errors(self):
        with self.assertRaises(LLMValidationError):
            validate(STEP, {"rows": []})
        with self.assertRaises(LLMValidationError):
            validate("intent_classify", {"label": "MAYBE", "reason": "x"})
        self.assertEqual(validate("intent_classify", {"label": "DELETE", "reason": "asks to erase"})["label"], "DELETE")
        with self.assertRaises(LLMValidationError):
            validate("no_such_step", {})


class MappingTests(unittest.TestCase):
    def row(self, rtype, **facts):
        f = {k: None for k in FACT_KEYS}
        f.update(facts)
        return {"record_type": rtype, "resource_id": None, "label": None, "selected": True, "identifiers": [], "facts": f}

    def test_facts_map_to_states_without_any_model_judgment(self):
        cap = "2026-06-18T12:00:00Z"
        cases = [(self.row("DATA_FLOW", enabled=True), m.ACTIVE), (self.row("DATA_FLOW", enabled=False), m.DISABLED),
                 (self.row("BACKUP", restore_blocked=False), m.RESTORABLE), (self.row("BACKUP", restore_blocked=True), m.BLOCKED),
                 (self.row("ANALYTICS", identifiable=True), m.EXPOSED), (self.row("ANALYTICS", identifiable=False), m.CLEAN),
                 (self.row("SUPPORT_TICKET", identifiable=True), m.EXPOSED), (self.row("TOMBSTONE", identifiable=False), m.CLEAN),
                 (self.row("EXPORT", expires_at="2026-06-25T06:42:00Z"), m.PRESENT),
                 (self.row("EXPORT", expires_at="2026-06-18T12:00:00Z"), m.ABSENT),     # expired exactly now
                 (self.row("EXPORT"), m.PRESENT), (self.row("SEARCH"), m.PRESENT), (self.row("MARKETING"), m.PRESENT),
                 (self.row("AUDIT"), m.PRESENT), (self.row("SUPPORT_ATTACHMENT"), m.PRESENT),
                 (self.row("ACCOUNT", status="Silver"), m.PRESENT), (self.row("ACCOUNT", status="Deleted"), m.ABSENT)]
        for row, want in cases:
            self.assertEqual(row_state(row, cap), want, row)

    def link(self, rid, email="p@example.org", user="user_1"):
        return m.LinkFact("activity_1", "2026-01-01T00:00:07Z", rid, "x", email, user, "evidence_1")

    def test_the_subject_row_takes_its_id_from_the_link_when_none_is_printed(self):
        data = good_screen()
        data["rows"][0].update(record_type="SUPPORT_ATTACHMENT", resource_id=None, label="delivery_confirmation_19.pdf")
        sink = Sink()
        problems = screen_to_observations(sink, "evidence_46", "2026-02-13T08:00:00Z", data, [self.link("object_19")])
        self.assertEqual(problems, [])
        o = sink.obs[0]
        self.assertEqual((o.resource_id, o.rtype, o.state), ("object_19", m.SUPPORT_ATTACHMENT, m.PRESENT))
        self.assertTrue({"p@example.org", "user_1"} <= o.tokens)

    def test_only_the_selected_row_becomes_an_observation(self):
        sink = Sink()
        screen_to_observations(sink, "evidence_09", "2026-09-01T06:00:00Z", good_screen(), [self.link("search_1")])
        self.assertEqual([o.resource_id for o in sink.obs], ["search_1"])

    def test_a_link_that_names_a_different_resource_is_reported_not_trusted(self):
        sink = Sink()
        problems = screen_to_observations(sink, "evidence_09", "2026-09-01T06:00:00Z", good_screen(), [self.link("search_999")])
        self.assertTrue(any("search_999" in p for p in problems))

    def test_a_subject_without_any_id_is_dropped_and_counted(self):
        data = good_screen()
        data["rows"][0].update(record_type="TOMBSTONE", resource_id=None, label="user_5")
        data["rows"][0]["facts"]["identifiable"] = False
        sink = Sink()
        screen_to_observations(sink, "evidence_42", "2026-03-10T06:00:00Z", data, [])
        self.assertEqual((sink.obs, sink.stats["evidence_42"]["unknown"]), ([], 1))


class LedgerTests(unittest.TestCase):
    def live_result(self, **kw):
        base = dict(step=STEP, key="evidence_09", data=good_screen(), origin="live", model="vendor/model-x",
                    provider="openrouter", request_id="gen-1", usage=Usage(100, 20, 120, 0.01, "api"))
        base.update(kw)
        return LLMResult(**base)

    def test_only_real_api_results_can_enter_the_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            led = Ledger(Path(tmp) / "ledger.md")
            for bad in (self.live_result(origin="transcribed", usage=None), self.live_result(origin="recorded"),
                        self.live_result(usage=None), self.live_result(usage=Usage(1, 1, 2, None, "estimate"))):
                with self.assertRaises(LedgerError):
                    led.record(bad, "run-1")
            self.assertFalse(led.path.exists())
            with self.assertRaises(LedgerError):
                led.record(self.live_result(), "run-1", outcome="maybe")

    def test_rows_are_appended_and_read_back_exactly(self):
        with tempfile.TemporaryDirectory() as tmp:
            led = Ledger(Path(tmp) / "ledger.md")
            led.record(self.live_result(), "run-1")
            led.record(self.live_result(key="evidence_14", usage=Usage(7, 3, 10, None, "api")), "run-1", "invalid")
            led.record(self.live_result(), "run-2")
            text = led.path.read_text(encoding="utf-8")
            self.assertTrue(text.startswith("# Usage ledger"))
            self.assertEqual(text.count("\n| run-"), 3)
            rows = led.rows("run-1")
            self.assertEqual([(r.key, r.total_tokens, r.cost_usd, r.outcome) for r in rows],
                             [("evidence_09", 120, 0.01, "ok"), ("evidence_14", 10, None, "invalid")])
            self.assertEqual(len(led.rows()), 3)
        self.assertEqual(len(COLUMNS), 12)


class LiveBackendTests(unittest.TestCase):
    KEY = "test-key-not-real"

    def backend(self, transport, tmp, model="vendor/model-x", allow=True, **kw):
        return OpenRouterBackend(model, Ledger(Path(tmp) / "ledger.md"), "run-test", transport=transport, allow_network=allow,
                                 sleep=lambda s: None, **kw)

    def env(self, key=KEY):
        return mock.patch.dict(os.environ, {KEY_ENV: key})

    def png(self, tmp):
        p = Path(tmp) / "x.png"
        p.write_bytes(b"\x89PNG fake bytes")
        return p

    def test_success_ledgers_the_provider_reported_usage_and_cost(self):
        with tempfile.TemporaryDirectory() as tmp, self.env():
            t = FakeTransport((200, api_payload(good_screen())))
            res = self.backend(t, tmp).run(request(image=self.png(tmp)))
            self.assertEqual((res.origin, res.model, res.provider, res.request_id), ("live", "vendor/model-x", "openrouter", "gen-abc"))
            self.assertEqual((res.usage.prompt_tokens, res.usage.completion_tokens, res.usage.total_tokens, res.usage.cost_usd, res.usage.source),
                             (900, 140, 1040, 0.0123, "api"))
            sent_url, headers, body = t.calls[0]
            self.assertEqual(headers["Authorization"], f"Bearer {self.KEY}")
            self.assertEqual((body["model"], body["temperature"], body["response_format"]), ("vendor/model-x", 0, {"type": "json_object"}))
            user = body["messages"][1]["content"]
            self.assertTrue(user[1]["image_url"]["url"].startswith("data:image/png;base64,"))
            rows = Ledger(Path(tmp) / "ledger.md").rows("run-test")
            self.assertEqual([(r.total_tokens, r.cost_usd, r.outcome) for r in rows], [(1040, 0.0123, "ok")])

    def test_a_response_without_cost_is_ledgered_with_cost_none_never_estimated(self):
        with tempfile.TemporaryDirectory() as tmp, self.env():
            self.backend(FakeTransport((200, api_payload(good_screen(), cost=None))), tmp).run(request())
            self.assertIsNone(Ledger(Path(tmp) / "ledger.md").rows()[0].cost_usd)

    def test_an_invalid_answer_is_paid_for_ledgered_and_repaired_once(self):
        bad = good_screen()
        bad["rows"][0]["selected"] = False
        with tempfile.TemporaryDirectory() as tmp, self.env():
            t = FakeTransport((200, api_payload(bad)), (200, api_payload(good_screen(), prompt=950)))
            res = self.backend(t, tmp).run(request())
            self.assertEqual(res.usage.prompt_tokens, 950)
            self.assertEqual([r.outcome for r in Ledger(Path(tmp) / "ledger.md").rows()], ["invalid", "ok"])
            self.assertIn("rejected", t.calls[1][2]["messages"][1]["content"])

    def test_a_persistently_invalid_answer_raises_after_ledgering_every_call(self):
        bad = {"screen": "x", "rows": []}
        with tempfile.TemporaryDirectory() as tmp, self.env():
            t = FakeTransport((200, api_payload(bad)), (200, api_payload(bad)))
            with self.assertRaises(LLMValidationError):
                self.backend(t, tmp).run(request())
            self.assertEqual(len(Ledger(Path(tmp) / "ledger.md").rows()), 2)

    def test_fenced_json_is_accepted(self):
        payload = api_payload(good_screen())
        payload["choices"][0]["message"]["content"] = "```json\n" + json.dumps(good_screen()) + "\n```"
        with tempfile.TemporaryDirectory() as tmp, self.env():
            self.assertEqual(self.backend(FakeTransport((200, payload)), tmp).run(request()).data["screen"], "Test > Page")

    def test_rate_limits_are_retried_and_other_errors_surface_without_the_key(self):
        with tempfile.TemporaryDirectory() as tmp, self.env():
            t = FakeTransport((429, "slow down"), (200, api_payload(good_screen())))
            self.backend(t, tmp).run(request())
            self.assertEqual(len(t.calls), 2)
            t2 = FakeTransport((401, '{"error":"bad key"}'))
            with self.assertRaises(LLMError) as cm:
                self.backend(t2, tmp).run(request())
            self.assertIn("401", str(cm.exception))
            self.assertNotIn(self.KEY, str(cm.exception))

    def test_a_response_without_usage_stops_the_run(self):
        with tempfile.TemporaryDirectory() as tmp, self.env():
            with self.assertRaises(LLMError):
                self.backend(FakeTransport((200, api_payload(good_screen(), with_usage=False))), tmp).run(request())

    def test_nothing_is_sent_without_explicit_permission_a_real_key_and_a_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = FakeTransport()
            with self.env("placeholder"), self.assertRaises(LiveNotConfigured):
                self.backend(t, tmp).run(request())
            with self.env(""), self.assertRaises(LiveNotConfigured):
                self.backend(t, tmp).run(request())
            with self.env(), self.assertRaises(LLMUnavailable):
                self.backend(t, tmp, allow=False).run(request())
            with self.env(), mock.patch.dict(os.environ, {"GHOSTAUDIT_MODEL": ""}), self.assertRaises(LiveNotConfigured):
                self.backend(t, tmp, model=None).run(request())
            with mock.patch.dict(os.environ, clear=False):
                os.environ.pop(KEY_ENV, None)
                with self.assertRaises(LiveNotConfigured):
                    self.backend(t, tmp).run(request())
            self.assertEqual(t.calls, [])

    def test_key_recognition(self):
        self.assertFalse(any(key_is_configured(k) for k in ("", "placeholder", "PLACEHOLDER", "your-key-here", None)))
        self.assertTrue(key_is_configured("abc123"))

    def test_the_default_transport_refuses_to_touch_the_network_in_the_test_suite(self):
        self.assertEqual(os.environ.get("GHOSTAUDIT_OFFLINE"), "1")
        with self.assertRaises(NetworkDisabled):
            urllib_transport("https://openrouter.ai/api/v1/chat/completions", {}, b"{}")


class RecordAndCompareTests(unittest.TestCase):
    def test_record_stores_a_recorded_fixture_and_replays_it_without_a_second_call(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {KEY_ENV: "test-key-not-real"}):
            root = Path(tmp) / "fx"
            t = FakeTransport((200, api_payload(good_screen())))
            live = OpenRouterBackend("vendor/model-x", Ledger(Path(tmp) / "l.md"), "run-r", transport=t, allow_network=True,
                                     sleep=lambda s: None)
            rec = RecordBackend(live, root)
            first = rec.run(request("evidence_09"))
            self.assertEqual(first.origin, "live")
            stored = path_for(root, "recorded", STEP, "evidence_09")
            self.assertTrue(stored.exists())
            back = parse_fixture(stored.read_text(encoding="utf-8"), "recorded")
            self.assertEqual((back.usage.total_tokens, back.model), (1040, "vendor/model-x"))
            second = rec.run(request("evidence_09"))
            self.assertEqual((second.origin, len(t.calls), len(Ledger(Path(tmp) / "l.md").rows())), ("recorded", 1, 1))
            self.assertFalse((root / "transcribed").exists())            # a recording never lands among the transcriptions

    def test_comparison_reports_disagreements_and_never_touches_transcriptions(self):
        before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (FIXTURE_ROOT / "transcribed").rglob("*.md")}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "transcribed" / STEP).mkdir(parents=True)
            a = good_screen(status="Indexed")
            (root / "transcribed" / STEP / "evidence_09.md").write_text(
                render_fixture(LLMResult(STEP, "evidence_09", a, "transcribed"), {}), encoding="utf-8")
            (root / "transcribed" / STEP / "evidence_14.md").write_text(
                render_fixture(LLMResult(STEP, "evidence_14", a, "transcribed"), {}), encoding="utf-8")
            same = LLMResult(STEP, "evidence_09", copy.deepcopy(a), "recorded", "vendor/model-x", "openrouter", "g1", Usage(1, 1, 2, None, "api"))
            path_for(root, "recorded", STEP, "evidence_09").parent.mkdir(parents=True)
            path_for(root, "recorded", STEP, "evidence_09").write_text(render_fixture(same, {}), encoding="utf-8")
            out = compare_all(root)
            self.assertEqual(out, {"evidence_09": [], "evidence_14": "no recorded reading"})
            other = copy.deepcopy(a)
            other["rows"][0]["facts"]["status"] = "Deleted"
            other["rows"][0]["identifiers"] = ["b@example.org"]
            diffs = diff_readings(a, other)
            self.assertEqual({d[0] for d in diffs}, {"selected row facts.status (free text)", "selected row identifiers"})
            text = render_agreement(out)
            self.assertIn("not ground truth", text)
        after = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (FIXTURE_ROOT / "transcribed").rglob("*.md")}
        self.assertEqual(before, after)


class IntentFallbackTests(unittest.TestCase):
    class Fixed:
        name = "fixed"

        def __init__(self, label):
            self.label = label
            self.calls = []

        def run(self, req):
            self.calls.append(req)
            return LLMResult(req.step, req.key, {"label": self.label, "reason": "test"}, "live", "m", "p", "r",
                             Usage(1, 1, 2, None, "api"))

    def world(self):
        from custom_cases import World
        wd = World()
        wd.user("user_1", "Pat Doe", "pat.doe@example.org")
        wd.case("case_1", "pat.doe@example.org", "2026-01-01T00:00:00Z", "NOT_STARTED", "2026-01-02T00:00:00Z",
                "2026-01-10T12:00:00Z", "Hello, please help.", "NOT_APPLICABLE", [], "unclear text")
        return wd

    def run_with(self, fallback):
        with tempfile.TemporaryDirectory() as tmp:
            ds = self.world().write(Path(tmp))
            return run_replay(ds, ds.requests, intent_fallback=fallback)

    def test_an_unclear_text_uses_the_model_answer_when_there_is_one(self):
        fb = IntentFallback(self.Fixed("NON_DELETE"))
        res = self.run_with(fb)
        self.assertEqual(res.results["case_1"].status, "NOT_APPLICABLE")
        self.assertEqual(len(fb.calls), 1)
        self.assertTrue(any("model fallback" in w for w in res.warnings))

    def test_without_a_model_answer_the_default_is_deletion_with_a_warning(self):
        res = self.run_with(IntentFallback(ReplayBackend()))                    # no intent fixtures exist: nothing is invented
        self.assertEqual(res.results["case_1"].status, "COMPLETE")
        self.assertTrue(any("defaulting to DELETE" in w for w in res.warnings))
        res2 = self.run_with(None)
        self.assertEqual(res2.results["case_1"].status, "COMPLETE")

    def test_no_real_request_needs_the_fallback(self):
        reader = offline_reader()
        res = run_replay(dataset(), dataset().requests, images=reader, intent_fallback=IntentFallback(OffBackend()))
        self.assertFalse([w for w in res.warnings if "intent unclear" in w])


class PromptTests(unittest.TestCase):
    def test_prompts_load_and_document_the_whole_schema(self):
        system, task = load_prompt("screenshot_transcribe")
        self.assertIn("single JSON object", system)
        for t in RECORD_TYPES:
            self.assertIn(f"`{t}`", task)
        for k in FACT_KEYS:
            self.assertIn(f"`{k}`", task)
        for k in ("screen", "rows", "record_type", "resource_id", "label", "selected", "identifiers", "facts"):
            self.assertIn(f"`{k}`", task)
        sys2, task2 = load_prompt("intent_classify")
        self.assertIn("DELETE", task2)
        self.assertIn("NON_DELETE", task2)

    def test_the_prompt_example_is_itself_valid(self):
        _system, task = load_prompt("screenshot_transcribe")
        block = re.search(r"```json\n(.*?)\n```", task, re.S).group(1)
        validate_screen(json.loads(block))


class MainAndManifestTests(unittest.TestCase):
    def test_live_modes_need_an_explicit_confirmation_flag(self):
        cli = load_cli()
        for mode in ("live", "record"):
            with self.assertRaises(SystemExit) as cm, contextlib.redirect_stderr(io.StringIO()):
                cli.main(["--llm", mode, "--out", "/nonexistent/out.csv"])
            self.assertEqual(cm.exception.code, 2)

    def test_a_live_run_that_cannot_read_the_screenshots_writes_no_output(self):
        cli = load_cli()
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ):
            os.environ.pop(KEY_ENV, None)
            out = Path(tmp) / "out.csv"
            with contextlib.redirect_stdout(io.StringIO()):
                code = cli.main(["--llm", "live", "--model", "vendor/model-x", "--confirm-live", "--out", str(out),
                                 "--report", str(Path(tmp) / "r.md")])
            self.assertEqual(code, 3)
            self.assertFalse(out.exists())

    def test_the_default_mode_is_replay_and_needs_no_key_or_network(self):
        cli = load_cli()
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ):
            os.environ.pop(KEY_ENV, None)
            out = Path(tmp) / "out.csv"
            with contextlib.redirect_stdout(io.StringIO()):
                code = cli.main(["--out", str(out), "--report", str(Path(tmp) / "r.md")])
            self.assertEqual(code, 0)
            self.assertTrue(out.exists())

    def test_the_committed_manifest_and_usage_report_describe_the_committed_output(self):
        root = CODE.parent
        manifest_path = CODE / "evaluation" / "run_manifest.md"
        mf = parse_manifest(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(mf["output_md5"], hashlib.md5((root / "output.csv").read_bytes()).hexdigest())
        self.assertEqual(mf["output_rows"], len(dataset().requests))
        ledger = Ledger()
        rows = ledger.rows(mf["run_id"])
        self.assertEqual(mf["api_calls"], len(rows))
        committed = (CODE / "evaluation" / "usage_report.md").read_text(encoding="utf-8")
        self.assertEqual(committed, render_usage_report(mf, rows, other_rows(ledger, mf["run_id"])))
        self.assertEqual(manifest_path.read_text(encoding="utf-8"), render_manifest(mf))

    def test_usage_report_totals_come_only_from_ledger_rows(self):
        from llm.usage import LedgerRow
        mf = {"command": "c", "output_file": "output.csv", "output_rows": 10, "output_md5": "x", "llm_mode": "live",
              "replay_origins": "transcribed", "run_id": "run-1", "model": "vendor/m", "api_calls": 2, "intent_calls": 0,
              "unclear_texts": 0, "screenshots": [{"file_id": "evidence_04", "origin": "live", "model": "vendor/m"}]}
        rows = [LedgerRow("run-1", "t", STEP, "evidence_04", "openrouter", "vendor/m", "g1", 100, 20, 120, 0.01, "ok"),
                LedgerRow("run-1", "t", STEP, "evidence_09", "openrouter", "vendor/m", "g2", 300, 40, 340, None, "ok")]
        text = render_usage_report(mf, rows)
        self.assertIn("| openrouter | vendor/m | 2 | 0 | 400 | 60 | 460 | 0.010000 |", text)
        self.assertIn("| average total tokens per request (10 requests) | 46.00 |", text)
        self.assertIn("reported no cost for 1 of 2 calls", text)
        self.assertIn("real API call in this run", text)
        other = [LedgerRow("run-0", "t", STEP, "evidence_04", "openrouter", "vendor/m", "g0", 50, 5, 55, 0.002, "ok")]
        text2 = render_usage_report(mf, rows, other)
        self.assertIn("Other runs in the ledger", text2)
        self.assertIn("1 API calls in 1 other run(s), 55 tokens, 0.002000 USD", text2)
        self.assertIn("| openrouter | vendor/m | 2 | 0 | 400 | 60 | 460 | 0.010000 |", text2)       # totals unchanged by other runs

    def test_no_secret_or_key_shaped_string_is_in_the_repository(self):
        pattern = re.compile(r"sk-or-[A-Za-z0-9]{8,}|Bearer [A-Za-z0-9\-_]{20,}")
        for p in CODE.parent.rglob("*"):
            if p.is_file() and ".git" not in p.parts and p.suffix in (".py", ".md", ".txt", ".csv", ".json", ".sql", ".log", ".yml", ""):
                if "dataset" in p.parts or "__pycache__" in p.parts:
                    continue
                try:
                    text = p.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
                self.assertIsNone(pattern.search(text), p)

    def test_modes_and_run_ids(self):
        self.assertEqual(new_run_id("replay"), "offline-replay")
        self.assertEqual(new_run_id("off"), "offline-off")
        self.assertTrue(new_run_id("live").startswith("run-"))
        with self.assertRaises(ValueError):
            make_backend("sideways")
        self.assertEqual(make_backend("off").name, "off")
        self.assertEqual(make_backend("replay").name, "replay")


if __name__ == "__main__":
    unittest.main()
