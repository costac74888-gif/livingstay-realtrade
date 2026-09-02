"""Helpers for removing credentials from logs and persisted error messages."""

import os
import re
from urllib.parse import quote, quote_plus, unquote


_SECRET_QUERY_PARAM_RE = re.compile(
    r"(?i)([?&](?:serviceKey|confmKey|apiKey|client_secret)=)([^&\s\"']+)"
)


def redact_env_secrets(text, env_names):
    """Redact raw and URL-encoded environment secret variants from text."""
    redacted = str(text)
    candidates = set()

    for name in env_names:
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

    for candidate in sorted((item for item in candidates if item), key=len, reverse=True):
        redacted = redacted.replace(candidate, "***")

    # Protect known credential query parameters even when the environment value
    # and the representation in an exception differ (for example double encoding).
    return _SECRET_QUERY_PARAM_RE.sub(r"\1***", redacted)