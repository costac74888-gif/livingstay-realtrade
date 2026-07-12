---
name: flask-limiter on Replit — client IP keying + testing gotchas
description: How to key rate limits per-IP behind Replit's multi-hop proxy, and why "exact Nth=429" tests are flaky
---

# Rate limiting per-IP behind the Replit proxy

## Client IP keying (the important one)
The Replit proxy in front of the app is **multi-hop**. Observed `X-Forwarded-For` chain
reaching the app: `<real_client>, 10.x.x.x, 10.x.x.x, 127.0.0.1` (internal IPs + a final
localhost hop).

- **`ProxyFix(x_for=1)` + `get_remote_address` is WRONG here.** x_for=1 takes the *rightmost*
  XFF entry = `127.0.0.1` (the constant last hop), so **every user collapses to one key and
  shares a single rate-limit counter.** Do not use it.
- **Correct approach:** key on the **leftmost** XFF entry (the original client):
  `request.headers.get("X-Forwarded-For").split(",")[0].strip()`, falling back to
  `get_remote_address()` when no XFF.
- **Why leftmost is safe (not spoofable):** the Replit **edge strips/rewrites a
  client-supplied XFF** — verified by sending `X-Forwarded-For: 1.2.3.4` to the public
  `*.replit.dev` domain and seeing it absent from the chain the app received. Trust model
  assumes access only *through* the edge; a direct-to-port path would weaken it.
- **How to inspect the real chain:** temporarily add a route returning
  `request.remote_addr`, `request.headers.get("X-Forwarded-For")`, `list(request.access_route)`,
  then curl `https://$REPLIT_DEV_DOMAIN/...` (localhost curl shows no XFF, so it won't reveal
  the proxy chain). Remove the debug route afterward.

## Storage scope
`storage_uri="memory://"` is **per-process**. Fine with gunicorn's default single sync worker.
With `--workers>1` or autoscale/multi-instance, counters aren't shared — the effective limit
loosens (requests spread across workers), it does NOT mix users. Switch to Redis if scaling out.

## `--reuse-port` restart caveat
With `gunicorn --reuse-port`, a restart can leave the **old master alive alongside the new
one** (both bound to the port); requests round-robin so stale code briefly serves. Symptom seen:
a removed route still returned 200 after restart. Check `ps aux | grep gunicorn` and kill the
orphan master by pid if a restart doesn't fully take.

## Testing gotchas (memory storage)
1. **Counter persists across test bursts** — back-to-back manual bursts accumulate in the same
   window, so a later burst trips 429 earlier than expected. Restart to reset, or wait out the window.
2. **Fixed-window (the default) allows ~2x at boundaries** — a `3 per minute` limit can let
   ~4-6 through when requests straddle a minute boundary. Judge correctness by "excess is
   blocked with 429" (a ~15-request burst shows a clean cutover) and by *isolation* (saturate
   IP A, confirm fresh IP B still passes), not by "the 4th request exactly." Use moving/sliding
   window if you need a precise per-minute cap.
