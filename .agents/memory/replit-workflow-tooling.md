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
