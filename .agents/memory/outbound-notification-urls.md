---
name: Outbound notification URLs
description: Trust boundary for URLs included in externally delivered SMS and email.
---

Any URL sent to a user or partner by SMS or email must be built from a configured,
validated canonical HTTPS origin, with a fixed production-origin fallback. Do not
derive an outbound URL from the current request's host, URL root, or forwarded host
headers.

**Why:** A request Host header can be attacker-controlled. Reflecting it into a
trusted service notification can turn an otherwise legitimate short-link message
into a phishing link.

**How to apply:** Use the canonical-origin helper for notification and other
externally shared URLs. Regression tests for outbound links should exercise an
untrusted request host and verify that the emitted link still uses the canonical
origin.