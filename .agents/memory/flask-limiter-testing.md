---
name: flask-limiter in-memory testing gotcha
description: Why "exactly the Nth request returns 429" tests are flaky with flask-limiter memory storage
---

# flask-limiter memory-storage testing

Rate limits use `storage_uri="memory://"` (per-process, no external infra). Two things make
"fire N requests, expect the Nth to be 429" tests non-deterministic:

1. **Counter persists across test runs.** Every burst you fire counts toward the same
   per-IP window. Back-to-back manual test bursts accumulate, so a later burst trips 429
   earlier than expected. To get a clean run, **restart the app** (clears the in-memory store)
   and fire immediately, or wait out the full window.

2. **Fixed-window strategy (the default) allows up to ~2x at window boundaries.** A `3 per
   minute` limit can briefly let 4-6 through when requests straddle a minute boundary. So the
   exact request index that first returns 429 varies; the *protection* is correct even when
   the index drifts.

**How to apply:** Judge correctness by "excess requests are blocked with 429" (a saturating
burst of ~15 shows a clean cutover), not by "the 4th request exactly." For a crisp demo,
restart first. For deterministic tests in code, use a moving-window strategy or mock the clock.

**Note:** App runs behind the Replit proxy, so `ProxyFix(app.wsgi_app, x_for=1)` is required
for `get_remote_address` to key on the real client IP instead of the proxy IP.
