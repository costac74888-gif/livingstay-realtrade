"""Post-merge checks with owned databases/HTTP and no preview dependency."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from run_offline_suite import execute
from offline_support.legacy_runtime import legacy_runtime
from offline_support.process_runner import run_check


def main():
    results = ROOT / ".local/suite-audit/post-merge"
    results.mkdir(parents=True, exist_ok=True)
    name = "frontend_distribution_test.py"
    result = execute(name, [sys.executable, str(ROOT / "tests" / name)],
                     60, results / (name + ".log"))
    print("Post-merge frontend:", result["exit_code"], flush=True)
    if result["exit_code"]:
        print((results / (name + ".log")).read_text())
        return result["exit_code"]
    name = "analysis_mobile_browser_test.js"
    log = results / (name + ".log")
    with legacy_runtime(results / (name + ".fixture.log"), browser=True) as env:
        # Keep the original browser test/assertions, but put relative captures
        # in the disposable workspace rather than overwriting original PNGs.
        workspace = Path(env["HOMENSTAY_LEGACY_WORKSPACE"])
        (workspace / "screenshots").mkdir(exist_ok=True)
        result = run_check(["node", str(ROOT / "tests" / name)],
                           cwd=workspace, env=env, timeout=90, logfile=log)
    print("Post-merge mobile:", result["exit_code"], flush=True)
    if result["exit_code"]:
        print(log.read_text())
    return result["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
