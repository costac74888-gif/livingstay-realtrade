# Browser capture outputs and reference images

Browser checks write PNG/JPEG, PDF and trace evidence into `generated-artifacts/`.
This directory is excluded from Git and deployment by `.gitignore` and
`.replitignore`. No existing reference image is untracked or removed.

## Running checks

```sh
python tests/run_offline_suite.py
# A focused run, with the same isolation and source-preservation checks:
python tests/run_offline_suite.py --only rental_redesign_browser_test.js
```

Each invocation creates a fresh `generated-artifacts/offline-suite/run-*` folder.
It contains logs, `summary.json`, per-check `captures/`, and
`source-before.json`, `source-after.json`, `source-preservation.json`.
`--results` selects a parent **inside generated-artifacts**, not a fixed run
folder. Reusing a parent never reuses a run. A failing check or interrupted
managed run still records the post-run fingerprint.

Original tracked files (including source, PNGs and frozen baselines) and any
additional PNGs under `screenshots/` are hashed before and after the suite.
Any changed, missing or newly added original reference PNG fails preservation;
files are not silently restored. Test failures remain failures independently.

Direct browser invocations also create a unique output folder and print
`CAPTURE_ARTIFACT_DIR`. Checks using an owned fixture still require their usual
fixture/transport setup. Capture flags and assertions are unchanged. An explicit
`HOMENSTAY_OFFLINE_ARTIFACT_DIR` must point at a child of `generated-artifacts`;
the orchestrator supplies this parent for each check. The helper always creates
a fresh `capture-*` subfolder, even when a configured parent is reused.
Post-merge checks use a fresh `generated-artifacts/post-merge/run-*` and the
same fingerprint protection. Captures remain after fixture cleanup.

Hash-reviewed HS2 tests remain byte-identical, including their literal capture
paths. Their owned browser runner loads `capture_preload.cjs` to redirect page
captures at runtime. It stays lazy and does not relax network/process isolation
or update the approved-check registry.

## Deliberate reference/baseline changes (separate from running tests)

1. Run the relevant browser check and locate its printed capture directory.
2. Inspect the new capture and the existing reference side by side. Confirm the
   product change is intended; a passing check alone is not approval.
3. In a separate, explicitly approved baseline-change operation, copy only the
   reviewed capture to the named reference file. Do not copy a whole output tree.
4. Review the image diff and any independently required frozen-baseline update.
   Commit these changes explicitly; never have a test update or accept them.
5. Run checks again. The preservation report must now show no changes relative
   to the approved new originals.

This capture-location change does not modify assertions or frozen baselines,
and adds no automatic baseline-update mode.

## Safe cleanup of old test runs

Run the separate command from the project workspace:

```sh
# Default: report only; completed evidence older than 30 days is eligible.
python scripts/cleanup_test_artifacts.py
# Age-only policy:
python scripts/cleanup_test_artifacts.py --keep-days 14
# Size-only policy (MiB, oldest eligible runs first):
python scripts/cleanup_test_artifacts.py --max-mib 2048
# Combined policy: age expiry OR enough removals to meet the size budget:
python scripts/cleanup_test_artifacts.py --keep-days 30 --max-mib 2048
# Inspect the JSON report first, then explicitly authorize actual deletion:
python scripts/cleanup_test_artifacts.py --keep-days 30 --max-mib 2048 --apply
```

The separate command does not install or enable any scheduled job.
`--dry-run` is also accepted explicitly; it cannot be combined
with `--apply`. Reports show each whole run's action, keep/delete reason and
logical file bytes before/after (not filesystem block usage). `bytes_after` is
the projected size during dry-run. There is no arbitrary-path or force override.

Only immediate run directories under `generated-artifacts/offline-suite`,
`generated-artifacts/browser-checks`, and `generated-artifacts/post-merge` are
considered. Nested captures/logs/PDFs/traces are removed only with their outer
run, never selectively. Custom `--results` destinations outside these three
trees and other generated output trees are deliberately not cleaned.

New Python runs and Node captures write `.artifact-run.json` with completion
state, producer, timestamps, and Linux process identity (PID, boot ID and start
ticks). Source preservation failures, returned nonzero results and exceptions
are failures, not successes. A successful run does **not** supersede the latest
failure: the newest failed evidence for each check/producer in each tree stays
protected, including failed nested captures and ties. A live owner, live nested
capture, interrupted run or unrecognized/missing/corrupt metadata is kept.
The suite and post-merge runner record each pending check before executing it,
so even fixture/setup exceptions preserve the failing check's name. A failed
generic Python run with no identifiable check is kept conservatively.
**Older results created before this metadata existed are kept**; completion
cannot safely be inferred from a PNG, log or source fingerprint. Review those
manually rather than fabricating a success marker to make them deletable.

The command never follows symlinks, deletes hard-linked evidence, or removes a
run containing tracked files or paths named `frozen`/`baseline` (including names
containing those words). Original `screenshots/`, source files and frozen
baselines outside the allowlisted output trees are never traversed or deleted.
Concurrent cleanup is locked; immediately before removal the command rechecks
eligibility and file identities/modification times. A changed run aborts removal.
Apply uses symlink-resistant fd-based directory removal and refuses platforms
without that support. A dry-run report is never reused as deletion permission.

Safety exclusions may prevent the requested budget being reached; the report
then sets `limit_unmet`, with no protection override. Unsafe/unreadable runs
whose size cannot be measured appear in `unmeasured_runs`; byte totals are a
lower bound in that case. A size policy with unmeasured runs also reports the
limit as unmet. Command/configuration or safety errors return a nonzero exit
code; a safely reported unmet budget is not an execution error.

Local regression checks (no production/database/email access):

```sh
python -m unittest discover -s tests -p 'test_artifact_cleanup.py' -v
python -m unittest discover -s tests -p 'test_capture_artifacts.py' -v
```

## Opt-in periodic cleanup (disabled by default)

The operator explicitly selected **30 days, 2048 MiB, every 24 hours**.
The versioned policy is `docs/test-artifact-retention-policy.json`. The age and
size rules combine with OR, exactly as in the separate command above. A size
budget is not permission to weaken any safety exclusion.

`scripts/scheduled_artifact_cleanup.py` delegates all eligibility and removal
to the existing cleanup command; it never imports the app, accesses a database
or sends notifications. No auto-start, deployment hook or Project run-button
task is installed. The workspace's existing workflow count exceeds its new
registration limit, so no dedicated workflow was added and none was removed
or repurposed. Run the watcher from a terminal, or register it as a separate
console workflow when capacity is available. Its default command has no
`--enable` and exits without cleaning even if started on workspace wake.

### Inspect, then enable

```sh
# Disabled: no scan, deletion, or audit directory creation.
python scripts/scheduled_artifact_cleanup.py
# Explicit preview: bypasses the interval, deletes nothing, saves a receipt.
python scripts/scheduled_artifact_cleanup.py --enable --dry-run
```

Inspect the returned JSON `report.runs`, keep/delete reasons, `limit_unmet` and
`unmeasured_runs`. Every attempt has a unique receipt and a private, fsynced log
under `generated-artifacts/artifact-cleanup-audit/<receipt>.json`. Read the
actual dry-run log before granting deletion approval. There is no automatic
approval. Receipts remain valid only for exactly the same policy (including
interval); changes require a new preview and explicit confirmation.

To monitor without deleting, run this command (or use it as a future dedicated
console workflow command):

```sh
python -u scripts/scheduled_artifact_cleanup.py --enable --watch --dry-run
```

To authorize actual periodic removal after inspecting a successful dry-run,
replace `RECEIPT` with its 32-character receipt ID and explicitly start:

```sh
python -u scripts/scheduled_artifact_cleanup.py --enable --watch --apply --confirm-dry-run RECEIPT
```

For a one-shot due check, omit `--watch`. Apply without a valid successful
dry-run receipt for the exact policy fails closed. The receipt confirms policy
review, **not a frozen deletion list**: every invocation recomputes the plan,
and the underlying cleaner rechecks each run immediately before removal.
No command in this change has applied cleanup to existing workspace evidence.

### Timing, stopping, and audit safety

- The first attempt in each mode/policy is due immediately; later attempts
  are due 24 hours after the last start. Dry-run and apply have separate clocks.
- The watcher polls once a minute. It holds a nonblocking scheduler lock for
  its lifetime; duplicate schedulers/preview commands refuse to run. The
  underlying cleanup lock also excludes concurrent manual removal.
- Logs persist across restarts, including error and interrupted (`running`)
  attempts; these count toward the interval to avoid rapid retries. Errors
  stop the watcher with a nonzero exit; no retry loop hides safety failures.
- A policy edit during watching stops the process. Stop the workflow, edit the
  policy, create/inspect a new preview, and update its receipt before restarting.
- To disable a terminal watcher, press Ctrl-C. If registered as a workflow,
  **stop** it, then restore its default command without `--enable`. Merely
  changing its command does not stop a running process.
- Symlinked audit roots/files and hard-linked audit files are refused. The
  log is saved before deletion starts, with policy, mode, start/end times,
  confirmation receipt and the full report (or error). Audit logs are outside
  the cleaner's allowlist and are not automatically pruned. Abrupt termination
  leaves a `running` log; it is not evidence of successful completion.
- Byte budgets cover only the three result trees, not retained audit logs.
  Safely unmet budgets remain visible in each log and never enable a force mode.

This watcher runs **only while the workspace is awake**. It does not promise
overnight or production scheduling, and does not alter the website deployment.
On restart it performs at most one overdue attempt, never a catch-up burst.
For fully unattended execution, separately configure scheduling in the
environment that actually owns these local artifact directories.

```sh
python -m unittest discover -s tests -p 'test_scheduled_artifact_cleanup.py' -v
```

### Read-only capacity warnings

For read-only periodic monitoring, run in a Shell:

```sh
python -u scripts/check_test_artifact_capacity.py --watch
```

It checks the approved policy (`docs/test-artifact-retention-policy.json`:
2048 MiB, every 24 hours) while the process and workspace are awake. Restarting
displays the last known summary without repeating its warning; the persisted
clock prevents restart loops. This is not an always-on production monitor, and
does not schedule or authorize deletion. A dedicated console workflow could not
be registered because the workspace already exceeds its workflow registration
limit; no existing workflow was removed or repurposed. Periodic execution is
therefore opt-in via the command above, not automatically enabled.

For an immediate check, ignoring the interval:

```sh
python scripts/check_test_artifact_capacity.py
```

This reports **current measured bytes**, not the estimated size after a proposed
cleanup. It warns when current bytes exceed the limit, any run cannot be measured,
or the scan fails. Unmeasured runs mean the measured number is only a lower bound;
do not treat it as proof that usage is within budget. `limit_unmet` also identifies
whether the conservative cleanup plan would still leave the budget unmet.
Only the three evidence trees are counted; the audit tree, original screenshots,
and other workspace files are outside this approved budget.

The human-readable console summary is the operator notification channel. A
machine-readable current status and last warning/recovery transition are atomically
saved to `generated-artifacts/artifact-cleanup-audit/capacity-status.json`.
Same-condition warnings are suppressed across process restarts, regardless of
small byte/count changes. A changed condition or policy raises a new warning;
returning to fully measured, within-limit usage prints `정상 복구`. Every due
check still prints its current summary, including when a repeat alert is suppressed.
One-shot exit codes: `0` healthy, `2` over-limit/unmeasured/scan failure, `1` monitor
setup/state error. Watch mode stays running for capacity/scan warnings but stops
on unsafe state, lock, or changed policy.

The existing administrator action centre uses production DB events and an email
outbox. Workspace-only test evidence is intentionally **not** sent there: this
monitor imports neither the app nor DB/email/SMS modules, and never sends external
notifications. It always calls the cleanup planner with `apply=False`; protected,
active, unknown, latest-failure and reference evidence remain untouched. State
writes and lock files are limited to the local audit/cleanup control area. A
separate `.capacity.lock` serializes monitor state updates, so the monitor can
run alongside the scheduler's long-lived `.scheduler.lock`. Both still use the
cleaner's per-scan `.artifact-cleanup.lock`; an overlapping deletion/scan produces
a check-error warning, never a false healthy result. A malformed or linked status
file is refused instead of silently resetting alert
history; inspect it before restarting. Audit files are never automatically pruned.

Regression checks use owned temporary Git roots, block socket connections,
disable external email/SMS, and fail on any attempted evidence deletion:

```sh
python -m unittest discover -s tests -p 'test_artifact_capacity.py' -v
```
