---
name: Password reset security
description: Security constraints for email password-reset links and their request delivery path.
---

# Password reset security

Never store a usable password-reset bearer token in the database. Store only a
SHA-256 digest, place the raw `token_urlsafe(32)` value exclusively in the
canonical-site reset URL, and lock the matching row while consuming it.

**Why:** A database read, backup, or accidental operational query must not be
enough to reset a member's password. Concurrent submissions must still consume
only one token.

**How to apply:** Keep reset-link generation on the validated public-origin
helper; compare digest values during redemption; maintain short expiry and
`used_at` state in the same password-update transaction. Do not call an
external mail provider inline only for existing accounts, because its network
latency can reveal account existence. Use the bounded delivery path for every
request and keep both normalized-email and IP limits in front of it.