---
name: Pooled DB connection ownership
description: Safe compatibility and ownership rules for the process-local PostgreSQL connection pool.
---

`get_conn()` may preserve legacy callers through a wrapper whose `close()` returns the
lease to the pool, while new code can use `release_conn()` explicitly. Flask request
teardown reclaims legacy request leases, and every newly introduced checkout still needs
deterministic ownership: close cursors and return the connection in `finally`.

**Why:** a connection's raw object can be returned to the pool and subsequently leased
to another request. A garbage-collection finalizer or any stale wrapper that releases
by raw-object identity can accidentally roll back or return that later request's active
lease.

**How to apply:** never release a lease from a finalizer by raw-connection identity
alone. A legacy fallback may release only when its unique per-checkout token still owns
the registry entry. Keep the pool process-local and fork-safe, and use an explicit
`try/finally` or the connection context manager whenever a new checkout path is introduced.