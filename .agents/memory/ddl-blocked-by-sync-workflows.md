---
name: DDL blocked by long-running sync workflows
description: Schema changes referencing master_buildings queue behind sync workflow locks and stall app boot
---

Rule: an `ALTER TABLE ... ADD COLUMN ... REFERENCES master_buildings(id)` (or any DDL touching master_buildings) needs an AccessExclusive-ish lock; long-running sync workflows (Fast Sync / Verify Units / Backfill Retry) hold AccessShareLock for long stretches, so the DDL waits — and the *queued* exclusive lock then blocks every new reader, including gunicorn boot (init_db), so the app hangs too.

**Why:** observed init_db stall indefinitely after a SCHEMA_VERSION bump; pg_stat_activity showed 3 stacked DDL waiters behind one sync session's AccessShareLock.

**How to apply:** before applying schema changes with FK references to hot tables, check pg_locks/pg_blocking_pids; if blocked, `pg_terminate_backend` the sync session (scripts are retry-safe via failure queue) and kill stacked waiters, then run init_db manually and restart the app. Consider `SET lock_timeout` to fail fast instead of queueing.
