"""Run every Python/script/JS/browser check with explicit offline safeguards.

Nonzero exit codes always remain failures: no baseline allowlist or xfail.
The preview workflow must also use the offline_support guard.
"""
import argparse
import ast
import json
import os
import signal
from pathlib import Path
import sys

from offline_support.process_runner import run_check

ROOT = Path(__file__).resolve().parents[1]


def test_environment():
    env = os.environ.copy()
    env.update({
        "HOMENSTAY_OFFLINE_TESTS": "1", "DISABLE_EXTERNAL_NOTIFICATIONS": "1",
        "SKIP_STARTUP_SCHEMA_INIT": "1", "SKIP_APP_BOOT_TASKS": "1",
        "RELAY_ENABLED": "0", "RELAY_USE_BLDG_HUB": "0", "RELAY_USE_RTMS": "0",
        "RELAY_USE_ONBID": "0", "RELAY_USE_JUSO": "0",
        "RELAY_TOKEN": "offline-test-realtime", "RELAY_TOKEN_BATCH": "offline-test-batch",
        "BLD_SERVICE_KEY": "offline-test-bld",
        "BLD_INSPECTION_SERVICE_KEY": "offline-test-inspection",
        "RTMS_SERVICE_KEY": "offline-test-rtms",
        "DATA_GO_KR_BROKER_API_KEY": "offline-test-broker",
        "PYTHONUNBUFFERED": "1",
    })
    env["PYTHONPATH"] = str(ROOT / "tests/offline_support") + os.pathsep + str(ROOT)
    env["NODE_OPTIONS"] = "--require=" + str(ROOT / "tests/offline_support/browser_guard.cjs")
    return env


def discover_checks():
    entries = [("Python pytest", [sys.executable, "-m", "pytest", "tests", "-q", "--tb=short"])]
    for path in sorted((ROOT / "tests").iterdir()):
        if path.suffix == ".py" and path.name != Path(__file__).name:
            tree = ast.parse(path.read_text())
            unittest_suite = any(
                isinstance(node, ast.ClassDef)
                and any("TestCase" in ast.unparse(base) for base in node.bases)
                for node in tree.body
            )
            script = any(
                isinstance(node, ast.If) and "__name__" in ast.unparse(node.test)
                and "__main__" in ast.unparse(node.test) for node in tree.body
            )
            if script and not unittest_suite:
                entries.append((path.name, [sys.executable, str(path)]))
        elif path.suffix in (".js", ".cjs"):
            entries.append((path.name, ["node", str(path)]))
    return entries


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, default=ROOT / ".local/suite-audit/after")
    parser.add_argument("--only", action="append", help="Exact check name; may be repeated")
    parser.add_argument("--timeout", type=float, default=300,
                        help="Deadline per check (seconds), never a pass on expiry")
    args = parser.parse_args()
    args.results = args.results.resolve()
    entries = discover_checks()
    if args.only:
        unknown = set(args.only) - {name for name, _ in entries}
        if unknown:
            parser.error(f"Unknown checks: {sorted(unknown)}")
        entries = [(name, cmd) for name, cmd in entries if name in args.only]
    args.results.mkdir(parents=True, exist_ok=True)
    results = []
    for name, command in entries:
        print("RUN " + name, flush=True)
        logfile = args.results / (name.replace("/", "_") + ".log")
        result = run_check(command, cwd=ROOT, env=test_environment(),
                           timeout=args.timeout, logfile=logfile)
        result.update(name=name, log=os.path.relpath(logfile, ROOT),
                      deadline_seconds=args.timeout)
        results.append(result)
        (args.results / "summary.json").write_text(
            json.dumps(results, ensure_ascii=False, indent=2))
        print(("PASS " if result["exit_code"] == 0 else "FAIL ") + name
              + f" ({result['seconds']}s)", flush=True)
    failed = [entry["name"] for entry in results if entry["exit_code"]]
    print(json.dumps({"checks": len(results), "passed": len(results) - len(failed),
                      "failed": failed}, ensure_ascii=False), flush=True)
    return bool(failed)


if __name__ == "__main__":
    def cancel_suite(_signal, _frame):
        raise SystemExit("Offline suite cancelled; cleaning up active check")
    signal.signal(signal.SIGTERM, cancel_suite)
    raise SystemExit(main())
