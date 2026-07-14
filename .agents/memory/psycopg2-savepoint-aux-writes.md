---
name: best-effort aux writes need SAVEPOINT
description: why any optional/non-blocking UPDATE inside a request transaction must be wrapped in a SAVEPOINT
---

When a request does a main write (e.g. INSERT a new row) and then a *best-effort* secondary write in the same transaction (e.g. geocode the address → UPDATE lat/lng), wrap the secondary write in `SAVEPOINT ... / RELEASE` and `ROLLBACK TO SAVEPOINT` on failure.

**Why:** in psycopg2, if any statement errors, the *entire* transaction enters an aborted state — every later statement, including the caller's `conn.commit()`, fails with "current transaction is aborted". So a try/except that merely swallows the exception is NOT enough to keep the failure non-blocking: the poisoned transaction still makes the main commit fail, and the main write is lost. Catching only the network call (e.g. the kakao API) misses the case where the *DB UPDATE itself* errors (bad value, constraint, type mismatch).

**How to apply:** `SAVEPOINT sp` before the aux `UPDATE`; on success `RELEASE SAVEPOINT sp`; on exception `ROLLBACK TO SAVEPOINT sp` (restores a clean transaction) then swallow/log. Verified: after ROLLBACK TO SAVEPOINT, the outer `conn.commit()` succeeds and the main row persists (aux columns left NULL). In livingstay this guards auto-geocoding of new master_buildings rows in submit_building() and POST /api/admin/buildings.

**Testing note:** direct write tests against master_buildings are flaky/timeout while Fast Sync / Backfill Retry workflows hold locks — verify the SAVEPOINT/abort behavior on a TEMP TABLE (lock-free) instead.
