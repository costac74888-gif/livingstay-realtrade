"""Guard checks replace the network transport; no real HTTP is attempted."""
import os
from pathlib import Path
import subprocess
import sys
import unittest


class OfflineEgressGuardTests(unittest.TestCase):
    def _check(self, script):
        root = Path(__file__).resolve().parents[1]
        env = dict(os.environ, HOMENSTAY_OFFLINE_TESTS="1",
                   PYTHONPATH=str(root / "tests/offline_support") + os.pathsep + str(root))
        result = subprocess.run([sys.executable, "-c", script], env=env,
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_requests_local_redirect_cannot_escape_to_public_api(self):
        self._check("""
import requests, sitecustomize as guard
from unittest.mock import patch
def local_redirect(adapter, request, **kwargs):
    assert request.url.startswith("http://127.0.0.1/")
    response = requests.Response()
    response.status_code = 302
    response.url = request.url
    response.request = request
    response._content = b""
    response.headers["Location"] = "https://apis.data.go.kr/offline-only"
    return response
with patch.object(guard, "_original_adapter_send", local_redirect):
    try:
        requests.get("http://127.0.0.1/redirect")
    except requests.RequestException as exc:
        assert "외부 HTTP 호출 차단" in str(exc)
    else:
        raise AssertionError("Redirect escaped the guard")
""")

    def test_urllib_opener_and_redirect_transport_are_guarded(self):
        self._check("""
import urllib.request, sitecustomize as guard
from unittest.mock import patch
for method, original, url in [
    (urllib.request.HTTPHandler().http_open, "_original_http_open", "http://apis.data.go.kr/offline-only"),
    (urllib.request.HTTPSHandler().https_open, "_original_https_open", "https://apis.data.go.kr/offline-only"),
]:
    with patch.object(guard, original, side_effect=AssertionError("Network reached")):
        try:
            method(urllib.request.Request(url))
        except OSError as exc:
            assert "외부 HTTP 호출 차단" in str(exc)
        else:
            raise AssertionError("Opener escaped the guard")
""")


if __name__ == "__main__":
    unittest.main()
