---
name: Detached background jobs from gunicorn
description: Long-running admin-triggered jobs must run as detached processes with a DB heartbeat, not threads in a gunicorn worker
---

- Rule: never run long background work in a thread inside a gunicorn worker — the worker gets SIGKILLed on WORKER TIMEOUT (30s default), silently killing the thread and leaving DB status stuck in "running".
- **Why:** observed during the admin "실거래 동기화" feature: thread-based worker died with the gunicorn worker, completion record was lost.
- **How to apply:** spawn `subprocess.Popen([sys.executable, script], start_new_session=True)` + a daemon `proc.wait()` reaper thread; the runner writes a DB heartbeat (updated_at) every ~30s; status API treats heartbeat older than a few minutes as stale/failed.
- Fencing: include a random `run_id` in the status row; runner's heartbeat and final write are `WHERE run_id = ...` so an old runner can't overwrite a newer run's status.
- Global guards belong in the DB (atomic UPSERT ... WHERE on state/updated_at), because flask-limiter memory:// is per-worker/per-instance and not reliable on autoscale.
- Autoscale caveat: detached processes die if the instance scales down; heartbeat-stale detection lets the admin re-run.
