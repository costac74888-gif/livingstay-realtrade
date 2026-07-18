---
name: init_db schema-version fast path
description: Why boot-time DDL was slow and the SCHEMA_VERSION skip rule
---
Rule: db.py init_db() skips ALL DDL/seeds when app_meta.schema_version == db.SCHEMA_VERSION. Any schema/constraint/seed change in db.py MUST bump SCHEMA_VERSION or it silently never applies.

**Why:** `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` takes an ACCESS EXCLUSIVE lock even as a no-op. Every boot (app + every batch script) reran ~50 DDLs plus a transactions dedup DELETE, so while batch sync workflows held table locks, boot/init_db blocked >100s — making redeploys and restarts look "stuck".

**How to apply:** when editing db.py schema, bump SCHEMA_VERSION (dated string) in the same commit; the next boot runs the full DDL once and re-stamps. First deploy after a bump can still hit a one-time lock-contention window if multiple processes boot simultaneously (advisory lock would serialize it if that ever bites).
