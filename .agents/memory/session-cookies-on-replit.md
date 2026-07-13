---
name: Session cookies & auth on Replit (livingstay)
description: Non-obvious quirks when setting Flask session cookie flags and testing auth behind the Replit proxy
---

# Session cookies & auth testing on Replit

## SESSION_COOKIE_SECURE=True breaks localhost-http curl tests
When Flask sets `SESSION_COOKIE_SECURE=True`, the session cookie is only sent over
HTTPS. `curl` respects the `Secure` attribute, so a cookie set over
`http://localhost:5000` will NOT be echoed back on subsequent http requests →
session appears lost, login flow tests fail spuriously.

**How to apply:** verify authenticated flows over `https://$REPLIT_DEV_DOMAIN`, not
`http://localhost:5000`. The dev domain is HTTPS and proxies to the app.

## The Replit preview proxy rewrites Set-Cookie SameSite → None
Even if Flask is configured with `SESSION_COOKIE_SAMESITE="Lax"`, the Set-Cookie
observed through `$REPLIT_DEV_DOMAIN` comes back as `SameSite=None` (proxy rewrites
it for iframe-preview compatibility; requires Secure, which is set).

**Why it doesn't matter for OAuth:** both `Lax` and `None` allow the cookie on the
top-level GET redirect back from an OAuth provider (e.g. Kakao callback), so the
`state` (CSRF) value stored in the session survives the round-trip. Do NOT use
`SameSite=Strict` — Strict would drop the cookie on the provider→app redirect and
break state validation.

## Session key separation (members vs admin)
General members use `session['user_id']`; admins use `session['admin']`. Member
logout must pop only `user_id` so an admin session in the same browser is
preserved. Keep these keys distinct — do not merge into one "logged in" flag.

## FLASK_SECRET_KEY must be fail-fast
`app.secret_key` falling back to `""` lets anyone forge signed session cookies
(member AND admin). App raises RuntimeError on boot if the secret is missing rather
than running with an empty signing key.
