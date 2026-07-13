---
name: Replit workflow tooling quirks
description: Non-obvious behaviors of configureWorkflow/removeWorkflow when stopping or disabling auto-start.
---

- `configureWorkflow({autoStart:false})` on an already-running workflow does NOT stop the
  running process. It only reconfigures the definition; the current run keeps going.
  **How to apply:** to actually STOP a running workflow, call `removeWorkflow` (it stops +
  removes). To keep the definition but stop it AND prevent auto-start on container wake:
  `removeWorkflow` then `configureWorkflow({autoStart:false})` to recreate it dormant
  (it lands in `finished`/`not_started`, won't auto-start).

- Workspace repls SLEEP when the user is away. All workflows auto-restart together when the
  container wakes (their log timestamps share the wake time). A "background" workflow does NOT
  run continuously overnight in the workspace — for true unattended runs use a Scheduled/Reserved
  Deployment.
  **Why:** matters for any long-running backfill/sync framed as "runs overnight". In the
  workspace it only runs while the repl is awake, and multiple auto-start workflows will contend
  for the same external API on wake.

- ORPHAN PROCESSES accumulate across restarts and are the first thing to suspect when
  (a) code edits don't take effect / routes randomly 404, or (b) every DB query & HTTP request
  times out (rc=124). Two flavors seen: `gunicorn --reuse-port` leaves old MASTERS bound to
  :5000 (kernel load-balances between old+new → stale code served intermittently as 404s); and
  a sync/backfill workflow can leave DUPLICATE `sync_batch.py` processes running concurrently
  (2x DB write load → total write contention, reads still OK).
  **How to apply:** `ps -eo pid,etime,cmd | grep -E "[g]unicorn|[s]ync_batch"`, `kill -9` the
  extra/older PIDs, then run verification in that clean window. For DB-heavy verification, kill
  the sync workers FIRST (they're idempotent/resumable), test, then `restart_workflow` them.
  Prefer Flask `test_client` in a SEPARATE process (needs `PYTHONPATH=/home/runner/workspace`)
  to sidestep the single busy gunicorn worker entirely.
