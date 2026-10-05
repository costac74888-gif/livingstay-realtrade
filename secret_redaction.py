"""Helpers for removing credentials from logs and persisted error messages."""

import os
import re
from urllib.parse import quote, quote_plus, unquote


_SECRET_QUERY_PARAM_RE = re.compile(
    r"(?i)([?&](?:serviceKey|confmKey|apiKey|client_secret)=)([^&\s\"']+)"
)
PUBLIC_API_SECRET_NAMES = (
    "RELAY_TOKEN", "RELAY_TOKEN_BATCH", "BLD_SERVICE_KEY",
    "BLD_INSPECTION_SERVICE_KEY", "RTMS_SERVICE_KEY", "DATA_GO_KR_BROKER_API_KEY",
)
_RELAY_URL_RE = re.compile(r"https?://[^\s\"'<>]*/v1/fetch\?[^\s\"'<>]+", re.I)


def redact_env_secrets(text, env_names):
    """Redact raw and URL-encoded environment secret variants from text."""
    redacted = str(text)
    redacted = _RELAY_URL_RE.sub("[중계 요청 URL 숨김]", redacted)
    candidates = set()

    for name in set(env_names) | set(PUBLIC_API_SECRET_NAMES):
        value = os.environ.get(name, "")
        if not value:
            continue

        decoded = value
        candidates.add(value)
        for _ in range(2):
            decoded = unquote(decoded)
            candidates.add(decoded)

        for candidate in tuple(candidates):
            if candidate:
                candidates.add(quote(candidate, safe=""))
                candidates.add(quote_plus(candidate, safe=""))
                candidates.add(quote(quote(candidate, safe=""), safe=""))
                candidates.add(quote_plus(quote_plus(candidate, safe=""), safe=""))
                candidates.add(quote(quote_plus(candidate, safe=""), safe=""))
                candidates.add(quote_plus(quote(candidate, safe=""), safe=""))

    for candidate in sorted((item for item in candidates if item), key=len, reverse=True):
        redacted = redacted.replace(candidate, "***")

    # Protect known credential query parameters even when the environment value
    # and the representation in an exception differ (for example double encoding).
    return _SECRET_QUERY_PARAM_RE.sub(r"\1***", redacted)


def redact_exception(exc, env_names):
    """Return an exception message safe for logs and user-facing errors."""
    return redact_env_secrets(str(exc), env_names)


def log_redacted_exception(logger, level, message, exc, env_names, *args):
    """Log a sanitized exception message without emitting its unsafe traceback."""
    log_method = getattr(logger, level)
    log_method(
        f"{message}: %s",
        *args,
        redact_exception(exc, env_names),
        exc_info=False,
    )