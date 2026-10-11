"""Pure format checks using fake strings, not real payment authentication."""
import json
import unittest
from scripts.check_toss_test_keys import check


class TestKeyFormat(unittest.TestCase):
    def test_empty_live_mixed_document_and_individual_pairs_fail(self):
        for client, secret in [
            ("", ""), ("live_gck_synthetic", "live_gsk_synthetic"),
            ("test_gck_synthetic", "live_gsk_synthetic"),
            ("test_gck_docs_synthetic", "test_gsk_docs_synthetic"),
            ("test_ck_synthetic", "test_sk_synthetic"),
        ]:
            with self.subTest(client=client):
                result = check({"TOSS_TEST_CLIENT_KEY": client,
                                "TOSS_TEST_SECRET_KEY": secret})
                self.assertFalse(result["ok"])
                self.assertNotIn("synthetic", json.dumps(result))
                self.assertTrue(all(type(v) is bool for v in result.values()))

    def test_test_shapes_do_not_claim_merchant_authentication(self):
        result = check({"TOSS_TEST_CLIENT_KEY": "test_gck_synthetic",
                        "TOSS_TEST_SECRET_KEY": "test_gsk_synthetic"})
        self.assertTrue(result["ok"])
        self.assertFalse(result["provider_called"])
        self.assertFalse(result["merchant_pair_verified"])
