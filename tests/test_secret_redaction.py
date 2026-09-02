import os
import unittest
from unittest.mock import patch
from urllib.parse import quote, quote_plus

from secret_redaction import redact_env_secrets


class SecretRedactionTest(unittest.TestCase):
    def test_redacts_raw_and_encoded_secret_variants(self):
        secret = "sample+/= credential"
        variants = (
            secret,
            quote(secret, safe=""),
            quote_plus(secret),
            quote(quote(secret, safe=""), safe=""),
        )
        with patch.dict(os.environ, {"TEST_SERVICE_KEY": secret}, clear=False):
            for variant in variants:
                with self.subTest(variant=variant):
                    result = redact_env_secrets(
                        f"https://example.test/api?serviceKey={variant}&page=1",
                        ("TEST_SERVICE_KEY",),
                    )
                    self.assertNotIn(secret, result)
                    self.assertNotIn(variant, result)
                    self.assertIn("serviceKey=***", result)

    def test_redacts_known_secret_query_parameter_without_env_match(self):
        result = redact_env_secrets(
            "request failed: /api?confmKey=unexpected-encoded-value&page=1",
            (),
        )
        self.assertEqual(
            result,
            "request failed: /api?confmKey=***&page=1",
        )

    def test_does_not_redact_noncredential_query_parameters(self):
        text = "/api?key=building-pnu&numOfRows=100"
        self.assertEqual(redact_env_secrets(text, ()), text)


if __name__ == "__main__":
    unittest.main()