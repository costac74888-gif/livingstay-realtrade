"""Post-merge checks with owned databases/HTTP and no preview dependency."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from run_offline_suite import execute
from offline_support.legacy_runtime import legacy_runtime
from offline_support.process_runner import run_check
from offline_support.source_preservation import new_run_directory, SourcePreservation


def main():
    results = new_run_directory(ROOT / "generated-artifacts/post-merge")
    print("POST_MERGE_RUN_DIR:", results, flush=True)
    with SourcePreservation(results) as preservation:
        preservation.exit_code = checks(results)
        return preservation.exit_code


def checks(results):
    summary = []

    def record(name, result=None):
        # Mark a check pending *before* fixture setup/execution so exceptions
        # also retain its identity rather than sharing a generic failure key.
        if result is None:
            summary.append({"name": name, "exit_code": 1, "completed": False})
        else:
            summary[-1].update(exit_code=result["exit_code"], completed=True)
        temporary = results / "summary.json.tmp"
        temporary.write_text(json.dumps(summary, indent=2) + "\n")
        temporary.replace(results / "summary.json")

    name = "frontend_distribution_test.py"
    record(name)
    result = execute(name, [sys.executable, str(ROOT / "tests" / name)],
                     60, results / (name + ".log"))
    record(name, result)
    print("Post-merge frontend:", result["exit_code"], flush=True)
    if result["exit_code"]:
        print((results / (name + ".log")).read_text())
        return result["exit_code"]
    name = "analysis_mobile_browser_test.js"
    record(name)
    log = results / (name + ".log")
    with legacy_runtime(results / (name + ".fixture.log"), browser=True) as env:
        env["HOMENSTAY_OFFLINE_ARTIFACT_DIR"] = str(results / "captures" / name)
        # Captures survive disposal of the owned fixture workspace.
        workspace = Path(env["HOMENSTAY_LEGACY_WORKSPACE"])
        result = run_check(["node", str(ROOT / "tests" / name)],
                           cwd=workspace, env=env, timeout=90, logfile=log)
    record(name, result)
    print("Post-merge mobile:", result["exit_code"], flush=True)
    if result["exit_code"]:
        print(log.read_text())
    return result["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
