---
name: Advisory locks with RealDictCursor
description: Scalar PostgreSQL advisory-lock results from the shared connection helper are mapping rows, not tuples.
---

When using the shared PostgreSQL connection helper for advisory locks, give scalar expressions a stable SQL alias and read the result by that key rather than by positional index.

**Why:** The helper uses `RealDictCursor`; positional access such as `row[0]` fails before the process can enforce its lock.

**How to apply:** For `pg_try_advisory_lock`, `pg_advisory_unlock`, and other scalar queries in batch scripts, select `... AS <name>` and use `row["<name>"]`.