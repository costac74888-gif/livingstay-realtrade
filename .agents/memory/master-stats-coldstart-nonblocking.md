---
name: Master stats cold starts
description: Nonblocking statistics requests and refresh scheduling while worker caches are empty or rebuilding.
---

When a worker's master statistics cache has no timestamp or data, public and admin statistics endpoints must not run, wait for, or contend on the full master-stat rebuild. They should schedule background revalidation and return a small schema-compatible `warming` response (or the dedicated bounded summary). Do not eagerly rebuild nationwide statistics in every Gunicorn `post_fork`; start only the on-demand background service and let the first statistics request trigger single-flight revalidation.

**Why:** Gunicorn request workers can be killed while a first request performs the nationwide aggregation, and a global rebuild lock merely moves that delay to other request workers. Per-worker eager rebuilds also duplicate CPU, memory, and DB load during deployment and can make `/` return 500 until both workers time out.

**How to apply:** Any new public endpoint that consumes a master-stat section needs an explicit cold-cache response before its legacy direct-aggregation fallback. Keep direct fallbacks for section failures or stale existing data, but do not use them for a truly empty cache. Worker lifecycle hooks may start the refresh loop, but must not launch a full rebuild merely because a worker forked. Exact, low-cost counters that users compare across reloads (such as a map legend) should query the shared DB directly rather than a per-worker cache; otherwise load balancing can alternate between cache generations.

Refresh scheduling must use a short-lived coordination lock separate from the long-lived rebuild/publication lock.

**Why:** Even a background-only rebuild made administrator statistics appear frozen when subsequent cold requests acquired the same lock merely to check whether a refresh was already running. With synchronous web workers, those waiting requests can also delay unrelated building-list requests.

**How to apply:** Protect single-flight scheduling independently of heavy computation. Administrator views should show explicit warming summaries and bounded retries, not silently remove failed tables. Auxiliary dashboard panels should update independently without redrawing charts or overwriting a different menu after navigation.