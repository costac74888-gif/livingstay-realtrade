---
name: Background stats DB priority
description: Connection-pool priority rules for master-statistics refresh work.
---

Master-statistics refresh work must run as a low-priority DB consumer: it may use
only the configured small background budget, never waits for a slot, and always
leaves at least one configured pool connection for user requests. The default
background cap is two concurrent leases; `DB_POOL_BACKGROUND_MAXCONN` may lower
or disable it.

**Why:** Map cluster searches share the application PostgreSQL pool with expensive
statistics rebuilds. Letting refresh work consume every connection causes visible
search failures under load.

**How to apply:** Any new DB access that runs as part of the statistics background
loop, revalidation thread, or section worker must execute under the background
priority context. If capacity is unavailable, retain the last healthy cache, signal
the next refresh attempt, and do not publish a partial replacement. User-serving
routes continue using normal-priority checkouts.