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
