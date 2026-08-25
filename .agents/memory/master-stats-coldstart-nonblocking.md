---
name: Master stats cold starts
description: Nonblocking rule for public statistics while per-worker master caches are empty.
---

When a worker's master statistics cache has no timestamp or data, public statistics endpoints must not run, wait for, or contend on the full master-stat rebuild. They should schedule background revalidation and return a small schema-compatible `warming` response (or the dedicated bounded summary). Full computation belongs only to the worker's background service or a revalidation thread.

**Why:** Gunicorn request workers can be killed while a first request performs the nationwide aggregation, and a global rebuild lock merely moves that delay to other request workers.

**How to apply:** Any new public endpoint that consumes a master-stat section needs an explicit cold-cache response before its legacy direct-aggregation fallback. Keep direct fallbacks for section failures or stale existing data, but do not use them for a truly empty cache.