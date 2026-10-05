"""Explicit test-only egress guard inherited by Python test subprocesses."""
import os

if os.environ.get("HOMENSTAY_OFFLINE_TESTS") == "1":
    import faulthandler
    import signal
    from urllib.parse import urlsplit
    import urllib.request
    import requests

    _original_request = requests.sessions.Session.request
    _local_hosts = {"localhost", "127.0.0.1", "::1", os.environ.get("REPLIT_DEV_DOMAIN", "")}

    def _offline_request(self, method, url, *args, **kwargs):
        if urlsplit(url).hostname not in _local_hosts:
            raise requests.RequestException("모의 테스트: 외부 HTTP 호출 차단")
        return _original_request(self, method, url, *args, **kwargs)

    requests.sessions.Session.request = _offline_request

    # Redirects use Session.send/adapters directly, not Session.request again.
    _original_adapter_send = requests.adapters.HTTPAdapter.send

    def _offline_adapter_send(self, request, *args, **kwargs):
        if urlsplit(request.url).hostname not in _local_hosts:
            raise requests.RequestException("모의 테스트: 외부 HTTP 호출 차단")
        return _original_adapter_send(self, request, *args, **kwargs)

    requests.adapters.HTTPAdapter.send = _offline_adapter_send

    _original_urlopen = urllib.request.urlopen

    def _offline_urlopen(url, *args, **kwargs):
        target = url.full_url if isinstance(url, urllib.request.Request) else url
        if urlsplit(target).hostname not in _local_hosts:
            raise OSError("모의 테스트: 외부 HTTP 호출 차단")
        return _original_urlopen(url, *args, **kwargs)

    urllib.request.urlopen = _offline_urlopen
    # OpenerDirector redirects likewise bypass the public urlopen wrapper.
    _original_http_open = urllib.request.HTTPHandler.http_open
    _original_https_open = urllib.request.HTTPSHandler.https_open

    def _offline_http_open(self, request):
        if urlsplit(request.full_url).hostname not in _local_hosts:
            raise OSError("모의 테스트: 외부 HTTP 호출 차단")
        return _original_http_open(self, request)

    def _offline_https_open(self, request):
        if urlsplit(request.full_url).hostname not in _local_hosts:
            raise OSError("모의 테스트: 외부 HTTP 호출 차단")
        return _original_https_open(self, request)

    urllib.request.HTTPHandler.http_open = _offline_http_open
    urllib.request.HTTPSHandler.https_open = _offline_https_open

    # A bounded runner asks for a stack dump before terminating. SystemExit
    # unwinds Python finally blocks (DB rollback/tempfile cleanup); SIGKILL is
    # reserved for descendants that do not stop during the grace period.
    faulthandler.register(signal.SIGUSR1, all_threads=True)
    if os.environ.get("HOMENSTAY_MANAGED_TEST") == "1":
        def _terminate_test(_signal, _frame):
            raise SystemExit("Offline test deadline/cancellation; cleaning up")
        signal.signal(signal.SIGTERM, _terminate_test)
