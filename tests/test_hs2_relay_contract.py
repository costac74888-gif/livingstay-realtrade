"""Safe relay regression: mocked transport + static admin guard, no Flask boot."""
import ast
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import requests
import public_api_client as relay

TARGET = "https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo"


class SafeRelayContract(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.object(relay, "_STATUS_DIR", Path(directory)))
        self.enterContext(patch.dict(os.environ, {
            "RELAY_ENABLED": "1", "RELAY_USE_BLDG_HUB": "1",
            "RELAY_BASE_URL": "https://relay.example.test",
            "RELAY_TOKEN": "fake-realtime", "RELAY_TOKEN_BATCH": "fake-batch",
        }))
        self.get = self.enterContext(patch.object(relay.requests, "get"))
        response = requests.Response()
        response.status_code = 200
        response._content = b"<response/>"
        self.get.return_value = response

    def test_realtime_and_batch_token_headers_and_timeout(self):
        for purpose, token in [("realtime", "fake-realtime"), ("batch", "fake-batch")]:
            relay.public_api_get(TARGET, {"serviceKey": "fake-key"}, (5, 10), purpose=purpose)
            args, kwargs = self.get.call_args
            self.assertEqual(args[0], "https://relay.example.test/v1/fetch")
            self.assertEqual(kwargs["headers"]["X-Relay-Token"], token)
            self.assertEqual(kwargs["headers"]["X-Relay-Purpose"], purpose)
            self.assertEqual(kwargs["timeout"], (20, 20))
            self.assertFalse(kwargs["allow_redirects"])

    def test_on_failure_no_direct_fallback(self):
        self.get.side_effect = requests.ConnectTimeout("fake")
        with self.assertRaises(relay.RelayRetryableError):
            relay.public_api_get(TARGET, {}, 5)
        self.get.assert_called_once()

    def test_off_is_direct_exactly(self):
        with patch.dict(os.environ, {"RELAY_ENABLED": "0"}):
            relay.public_api_get(TARGET, {"page": 1}, 7)
        self.get.assert_called_once_with(TARGET, params={"page": 1}, timeout=7)

    def test_invalid_spoofed_host_is_not_called(self):
        with self.assertRaises(relay.RelayError):
            relay.public_api_get(TARGET.replace("apis.data.go.kr", "evil.example.test"), {}, 5)
        self.get.assert_not_called()

    def test_missing_batch_token_is_fail_closed(self):
        with patch.dict(os.environ, {"RELAY_TOKEN_BATCH": ""}):
            with self.assertRaises(relay.RelayError):
                relay.public_api_get(TARGET, {}, 5, purpose="batch")
        self.get.assert_not_called()

    def test_response_url_has_no_auth_query(self):
        result = relay.public_api_get(TARGET, {"serviceKey": "fake-secret"}, 5)
        self.assertEqual(result.url, TARGET)

    def test_admin_status_keeps_require_admin_decorator(self):
        tree = ast.parse((Path(__file__).resolve().parents[1] / "app.py").read_text())
        function = next(n for n in ast.walk(tree)
                        if isinstance(n, ast.FunctionDef) and n.name == "admin_public_api_relay_status")
        self.assertIn("require_admin", [ast.unparse(d) for d in function.decorator_list])
        self.assertTrue(any("/api/admin/public-api-relay/status" in ast.unparse(d)
                            for d in function.decorator_list))


if __name__ == "__main__":
    unittest.main()
