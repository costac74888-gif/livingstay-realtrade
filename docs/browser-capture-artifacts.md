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

No scheduled job is installed and no existing evidence is deleted when adding
this command. `--dry-run` is also accepted explicitly; it cannot be combined
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
