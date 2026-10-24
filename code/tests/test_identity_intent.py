import unittest

from .support import dataset, resolver
from ghostaudit.intent import DELETE, NON_DELETE, classify_text


class IdentityTests(unittest.TestCase):
    def test_every_request_email_resolves_to_one_user(self):
        ds, res = dataset(), resolver()
        forms = [res.resolve(r.email)[1] for r in ds.all_requests]
        self.assertEqual(len(forms), 550)
        self.assertEqual((forms.count("current"), forms.count("historical")), (447, 103))

    def test_upper_case_email_still_resolves(self):
        ds, res = dataset(), resolver()
        some = ds.identities[0]["email"]
        self.assertEqual(res.resolve(some.upper())[0], ds.identities[0]["user_id"])

    def test_no_token_is_shared_between_users(self):
        res = resolver()
        self.assertEqual([t for t, u in res.token_users.items() if len(u) > 1], [])

    def test_historical_email_maps_to_the_same_user_as_the_current_one(self):
        ds, res = dataset(), resolver()
        row = next(a for a in ds.audit_log if a["field_name"] == "email")
        self.assertEqual(res.resolve(row["old_value"])[0], row["user_id"])
        self.assertEqual(res.resolve(row["old_value"])[1], "historical")


class IntentTests(unittest.TestCase):
    def test_exactly_ten_eval_cases_are_not_deletion_requests(self):
        ds = dataset()
        non = sorted(r.number for r in ds.requests if classify_text(r.request_text).label != DELETE)
        self.assertEqual(non, list(range(533, 543)))

    def test_all_samples_are_deletion_requests(self):
        self.assertTrue(all(classify_text(r.request_text).label == DELETE for r in dataset().sample_requests))

    def test_negation_is_scoped_to_the_verb(self):
        cases = {
            "I want my account removed, but do not delete my invoices.": DELETE,
            "Please do not close the account.": NON_DELETE,
            "I still need the account and my order history, so I am not asking for deletion.": NON_DELETE,
            "Please remove me from marketing lists only.": NON_DELETE,
            "Please remove my name and contact details, but keeping an internal deleted-account reference is fine.": DELETE,
            "Je demande la suppression définitive du compte.": DELETE,
            "このメールアドレスに関連するアカウントの完全な削除を依頼します。": DELETE,
        }
        for text, want in cases.items():
            self.assertEqual(classify_text(text).label, want, text)

    def test_classify_events_map_to_exactly_the_non_deletion_cases(self):
        ds = dataset()
        events = [a for a in ds.activity if a["event_type"] == "CLASSIFY_REQUEST"]
        non = [r for r in ds.requests if classify_text(r.request_text).label == NON_DELETE]
        self.assertEqual(len(events), len(non))
        self.assertEqual(len(ds.requests) - len(non), 508)
        run = __import__("tests.support", fromlist=["x"]).pipeline_run()
        for r in non:
            self.assertTrue(run.intents[r.case_id][2], f"{r.case_id} lacks CLASSIFY corroboration")


if __name__ == "__main__":
    unittest.main()
