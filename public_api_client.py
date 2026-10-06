"""Opt-in public API relay transport. Parsing, quotas and retries belong to callers."""

import json
import logging
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import fcntl
import requests
from requests.exceptions import ConnectTimeout, RequestException, Timeout


SERVICE_PATHS = {
    "bldg_hub": ("/1613000/BldRgstHubService/",),
    "rtms": tuple(
        f"/1613000/RTMSDataSvc{name}/"
        for name in ("NrgTrade", "RHTrade", "SHTrade", "LandTrade")
    ),
    "onbid": ("/B010003/",),
}
SERVICE_SWITCHES = {
    "bldg_hub": "RELAY_USE_BLDG_HUB",
    "rtms": "RELAY_USE_RTMS",
    "onbid": "RELAY_USE_ONBID",
}
ERROR_STATUS = {
    "RELAY_AUTH": 401, "RELAY_FORBIDDEN": 403, "RELAY_QUOTA": 429,
    "CIRCUIT_OPEN": 503, "RELAY_BUSY": 503, "UPSTREAM_TIMEOUT": 504,
    "UPSTREAM_CONNECT": 502, "RELAY_INTERNAL": 500,
}
RETRYABLE_CODES = frozenset(("UPSTREAM_TIMEOUT", "UPSTREAM_CONNECT", "RELAY_BUSY"))
_STATUS_DIR = Path(tempfile.gettempdir()) / "homenstay-public-api-relay"
_LOGGER = logging.getLogger(__name__)


class RelayError(RuntimeError):
    """Safe relay error: never retain the request, response, URL or remote message."""

    def __init__(self, code, status_code=None):
        self.code = code if code in ERROR_STATUS else "RELAY_INTERNAL"
        self.status_code = status_code or ERROR_STATUS[self.code]
        self.retryable = self.code in RETRYABLE_CODES
        super().__init__(f"공공 API 중계 오류: {self.code}")


class RelayRetryableError(RelayError, ConnectTimeout):
    """Use the existing ConnectTimeout retry budget, without an extra retry loop."""


def _enabled(service):
    switch = SERVICE_SWITCHES.get(service)
    return bool(switch) and os.environ.get("RELAY_ENABLED", "") == "1" and os.environ.get(switch, "") == "1"


@contextmanager
def _status_lock():
    _STATUS_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (_STATUS_DIR / "status.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _read_status():
    try:
        raw = (_STATUS_DIR / "status.json").read_text()
        return json.loads(raw) if len(raw) <= 4096 else {}
    except (OSError, ValueError):
        return {}


def _record_status(service, error_code=None):
    # Cross-worker/local-batch telemetry only; no database/schema writes.
    try:
        with _status_lock():
            data = _read_status()
            row = data.setdefault(service, {})
            if error_code:
                row["last_error_code"] = error_code
            else:
                row["last_success_at"] = datetime.now(timezone.utc).isoformat()
            temporary = _STATUS_DIR / "status.new"
            temporary.write_text(json.dumps(data))
            temporary.replace(_STATUS_DIR / "status.json")
    except (OSError, TypeError, AttributeError):
        _LOGGER.warning("중계 상태 기록을 저장하지 못했습니다.")


def relay_status():
    """Only non-sensitive switch state and bounded transport telemetry."""
    try:
        with _status_lock():
            saved = _read_status()
    except OSError:
        saved = {}
    result = {}
    for service in SERVICE_PATHS:
        row = saved.get(service, {}) if isinstance(saved, dict) else {}
        row = row if isinstance(row, dict) else {}
        success = row.get("last_success_at")
        try:
            success = datetime.fromisoformat(success).isoformat() if isinstance(success, str) else None
        except ValueError:
            success = None
        error = row.get("last_error_code")
        result[service] = {
            "enabled": _enabled(service),
            "last_success_at": success,
            "last_error_code": error if isinstance(error, str) and error in ERROR_STATUS else None,
        }
    return result


def _fail(service, code, status=None):
    _record_status(service, code)
    error_class = RelayRetryableError if code in RETRYABLE_CODES else RelayError
    raise error_class(code, status) from None


def _valid_target(url):
    parsed = urlsplit(url)
    return (
        parsed.scheme == "https" and parsed.hostname == "apis.data.go.kr"
        and parsed.netloc == "apis.data.go.kr"
        and not parsed.fragment and "%" not in parsed.path and ".." not in parsed.path
        and any(parsed.path.startswith(prefix) for paths in SERVICE_PATHS.values() for prefix in paths)
        and len(url) <= 8192
    )


def public_api_get(url, params, timeout, purpose="realtime"):
    """One HTTP attempt; OFF/disallowed APIs retain requests.get's exact call."""
    try:
        path = urlsplit(url).path
    except ValueError:
        path = ""
    service = next(
        (name for name, prefixes in SERVICE_PATHS.items() if any(path.startswith(p) for p in prefixes)),
        None,
    )
    if service is None or not _enabled(service):
        return requests.get(url, params=params, timeout=timeout)

    if purpose not in ("realtime", "batch"):
        _fail(service, "RELAY_FORBIDDEN")
    token_name = "RELAY_TOKEN_BATCH" if purpose == "batch" else "RELAY_TOKEN"
    token = os.environ.get(token_name, "").strip()
    if not token:
        _fail(service, "RELAY_AUTH")
    base = os.environ.get("RELAY_BASE_URL", "").strip().rstrip("/")
    try:
        parsed_base = urlsplit(base)
        if (parsed_base.scheme != "https" or not parsed_base.hostname
                or parsed_base.username or parsed_base.password
                or parsed_base.query or parsed_base.fragment):
            _fail(service, "RELAY_INTERNAL")
        if not _valid_target(url):
            _fail(service, "RELAY_FORBIDDEN")
        target = requests.Request("GET", url, params=params).prepare().url
        if not _valid_target(target):
            _fail(service, "RELAY_FORBIDDEN")
    except (ValueError, RequestException):
        _fail(service, "RELAY_FORBIDDEN")

    relay_timeout = (
        tuple(max(float(value), 20) for value in timeout)
        if isinstance(timeout, tuple) else max(float(timeout or 20), 20)
    )
    try:
        response = requests.get(
            base + "/v1/fetch", params={"url": target},
            headers={"X-Relay-Token": token, "X-Relay-Purpose": purpose},
            timeout=relay_timeout, allow_redirects=False,
        )
    except Timeout:
        _fail(service, "UPSTREAM_TIMEOUT")
    except RequestException:
        _fail(service, "UPSTREAM_CONNECT")
    if response.headers.get("X-Relay-Error") == "1":
        try:
            payload = response.json()
            code = payload.get("code") if isinstance(payload, dict) else None
        except (ValueError, TypeError):
            code = None
        _fail(service, code if isinstance(code, str) and code in ERROR_STATUS else "RELAY_INTERNAL", response.status_code)
    # Existing raise_for_status() callers must not print the encoded relay URL.
    response.url = "https://apis.data.go.kr" + urlsplit(target).path
    if 200 <= response.status_code < 300:
        _record_status(service)
    return response
