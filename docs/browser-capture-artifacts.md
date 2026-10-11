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
