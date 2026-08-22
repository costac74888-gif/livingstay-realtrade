---
name: RealDictCursor scalar queries
description: Scalar PostgreSQL lock and aggregate results from the shared connection helper are mapping rows, not tuples.
---

When using the shared PostgreSQL connection helper for scalar lock or aggregate queries, give the expression a stable SQL alias and read the result by that key rather than by positional index.

**Why:** The helper uses `RealDictCursor`; positional access such as `row[0]` raises `KeyError`, even for common results such as `COUNT(*)`.

**How to apply:** For `COUNT(*)`, `pg_try_advisory_lock`, `pg_advisory_unlock`, and other scalar queries in app routes or batch scripts, select `... AS <name>` and use `row["<name>"]`.