---
name: Postgres ON CONFLICT + partial unique index
description: Why ON CONFLICT fails with a partial unique index, and when to use a full unique index for nullable dedup columns
---

`INSERT ... ON CONFLICT (col_a, col_b) DO NOTHING` will raise
"there is no unique or exclusion constraint matching the ON CONFLICT specification"
if the only matching unique index is **partial** (has a `WHERE` predicate) — unless
you restate the exact predicate in the statement: `ON CONFLICT (col_a, col_b) WHERE <predicate>`.

**Why:** Postgres only picks a partial index for arbiter inference when the statement's
WHERE matches the index predicate. A bare `ON CONFLICT (cols)` won't match a partial index.

**How to apply:** For dedup on a nullable column (e.g. `notifications (user_id, transaction_id)`
where transaction_id can be NULL for manually-created rows), prefer a **full** unique index
`(user_id, transaction_id)`. NULLs are distinct in Postgres unique indexes, so NULL-transaction
rows never collide (multiple allowed) while non-NULL rows still dedup — and a plain
`ON CONFLICT (user_id, transaction_id) DO NOTHING` matches it. `CREATE UNIQUE INDEX IF NOT EXISTS`
will NOT convert an existing partial index; drop it first if an intermediate build created one.
