import os
import unittest
from unittest.mock import Mock, patch
from urllib.parse import quote, quote_plus

import requests

import building_registry
from secret_redaction import (
    log_redacted_exception,
    redact_env_secrets,
    redact_exception,
)


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

    def test_redacts_prepared_request_exception_raw_and_encoded_values(self):
        secret = "sample+/= credential"
        prepared = requests.Request(
            "GET",
            "https://example.test/api",
            params={"serviceKey": secret, "page": 1},
        ).prepare()
        error = requests.exceptions.ConnectTimeout(
            f"timed out for url: {prepared.url}",
            request=prepared,
        )

        with patch.dict(os.environ, {"TEST_SERVICE_KEY": secret}, clear=False):
            result = redact_exception(error, ("TEST_SERVICE_KEY",))

        self.assertNotIn(secret, result)
        self.assertNotIn(quote_plus(secret), result)
        self.assertIn("serviceKey=***", result)

    def test_building_registry_reraises_timeout_without_service_key(self):
        secret = "building+/= secret"
        prepared = requests.Request(
            "GET",
            building_registry.BLD_TITLE_URL,
            params={"serviceKey": secret},
        ).prepare()
        error = requests.exceptions.ConnectTimeout(
            f"timed out for url: {prepared.url}",
            request=prepared,
        )

        with (
            patch.dict(os.environ, {"BLD_SERVICE_KEY": secret}, clear=False),
            patch.object(building_registry, "_RETRY_MAX", 0),
            patch("building_registry.requests.get", side_effect=error),
        ):
            with self.assertRaises(building_registry.BuildingRegistryRequestError) as raised:
                building_registry._get_with_retry(
                    building_registry.BLD_TITLE_URL,
                    {"serviceKey": secret},
                    timeout=1,
                )

        message = str(raised.exception)
        self.assertNotIn(secret, message)
        self.assertNotIn(quote_plus(secret), message)
        self.assertIn("serviceKey=***", message)

    def test_building_registry_reraises_http_error_without_service_key(self):
        secret = "http+/= secret"
        response = requests.Response()
        response.status_code = 429
        response.url = requests.Request(
            "GET",
            building_registry.BLD_TITLE_URL,
            params={"serviceKey": secret, "pageNo": 1},
        ).prepare().url

        with (
            patch.dict(os.environ, {"BLD_SERVICE_KEY": secret}, clear=False),
            patch("building_registry.requests.get", return_value=response),
        ):
            with self.assertRaises(building_registry.BuildingRegistryRequestError) as raised:
                building_registry._get_with_retry(
                    building_registry.BLD_TITLE_URL,
                    {"serviceKey": secret},
                    timeout=1,
                )

        message = str(raised.exception)
        self.assertNotIn(secret, message)
        self.assertNotIn(quote_plus(secret), message)
        self.assertIn("serviceKey=***", message)

    def test_log_helper_never_emits_unsafe_traceback(self):
        secret = "logging+/= secret"
        error = RuntimeError(
            f"timeout: https://example.test/api?serviceKey={quote_plus(secret)}"
        )
        logger = Mock()

        with patch.dict(os.environ, {"TEST_SERVICE_KEY": secret}, clear=False):
            log_redacted_exception(
                logger,
                "warning",
                "external request failed (id=%s)",
                error,
                ("TEST_SERVICE_KEY",),
                42,
            )

        logger.warning.assert_called_once()
        args, kwargs = logger.warning.call_args
        rendered = args[0] % args[1:]
        self.assertNotIn(secret, rendered)
        self.assertNotIn(quote_plus(secret), rendered)
        self.assertIn("serviceKey=***", rendered)
        self.assertIs(kwargs["exc_info"], False)


if __name__ == "__main__":
    unittest.main()