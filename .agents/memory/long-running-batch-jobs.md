---
name: Long-running batch jobs on Replit
description: How to run multi-hour batch scripts (data collection, backfills) that outlive a single tool call.
---

# Running long batch jobs

`nohup ... &` background processes launched from the bash tool are **reaped when the
launching tool call returns** — they do not survive to the next turn. Symptom: process
gone within seconds, log shows only startup lines, no completion summary, no error.

**Use a Replit workflow instead** (`configureWorkflow` with `outputType: "console"`,
no `waitForPort`, `autoStart: true`). Workflows are managed processes that persist
across tool calls and across turns. A batch script that exits cleanly shows state
`finished` (it is NOT auto-restarted like a server).

**How to apply:** for anything longer than the ~120s bash tool timeout, write a wrapper
`.sh` that runs the steps sequentially and `touch`es a `/tmp/*_DONE` marker at the end,
set it as a console workflow, then poll progress from the DB / marker file between turns.

**Why:** the bash tool caps at 120s and background processes get reaped, so neither
direct bash nor nohup can carry a multi-hour job. Only a workflow can.

# Monitoring a batch job by row count: commit visibility trap

If a long backfill commits **only once at the very end**, its inserted rows stay
inside the open transaction and are **invisible to any other DB connection** (e.g. a
`psql COUNT(*)` you run to watch progress). Symptom: the job is healthy and clearly
making API calls, but your external row-count measurements read `+0` for many
minutes — looking exactly like a stall/deadlock when nothing is actually wrong.

**How to apply:** for any multi-region / multi-batch backfill, `conn.commit()` at the
end of **each batch (per region, per N rows)**, not once at the end. This makes
progress observable from a separate connection, and means a crash/restart loses at
most one batch instead of the whole run. When a job looks stalled, first confirm
whether monitoring reads committed data before assuming the job itself is stuck.

**Why:** a single terminal commit cost hours of debugging a non-existent stall — the
`sync_batch.py` 60-month backfill was fetching and inserting correctly the whole time;
row count only moved once per-region commits were added.
