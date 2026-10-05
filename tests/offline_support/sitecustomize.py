"""Explicit test-only egress guard inherited by Python test subprocesses."""
import os

if os.environ.get("HOMENSTAY_OFFLINE_TESTS") == "1":
    from urllib.parse import urlsplit
    import requests

    _original_request = requests.sessions.Session.request
    _local_hosts = {"localhost", "127.0.0.1", "::1", os.environ.get("REPLIT_DEV_DOMAIN", "")}

    def _offline_request(self, method, url, *args, **kwargs):
        if urlsplit(url).hostname not in _local_hosts:
            raise requests.RequestException("모의 테스트: 외부 HTTP 호출 차단")
        return _original_request(self, method, url, *args, **kwargs)

    requests.sessions.Session.request = _offline_request
