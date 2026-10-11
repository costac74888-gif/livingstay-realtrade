"""Run every Python/script/JS/browser check with explicit offline safeguards.

Nonzero exit codes always remain failures: no baseline allowlist or xfail.
The preview workflow must also use the offline_support guard.
"""
import argparse
import ast
import json
import os
import signal
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from offline_support.process_runner import run_check
from offline_support.legacy_runtime import legacy_runtime
from offline_support.source_preservation import new_run_directory, SourcePreservation
from hs2_harness.isolated_browser import FIXTURE_CHECKS as BROWSER_CHECKS
from hs2_harness.isolated_postgres import FIXTURE_CHECKS as DB_CHECKS
from hs2_harness import core

PURE_UNIT_CHECKS = {
    "test_building_detail_enrichment.py": "tests/test_building_detail_enrichment.py",
    # This module creates its own guarded DB capability; do not nest it under
    # the app integration process's preloaded driver capability.
    "test_owned_offline_runtime.py": "tests/test_owned_offline_runtime.py",
}
NORMAL_HS2 = {key: check for key, check in core.load(core.CHECKS).items()
              if check["kind"] == "python" and check["file"].startswith("tests/test_hs2")
              and not check.get("isolation")}

def test_environment():
    # No inherited live DSNs, PG defaults, provider/delivery keys or dev origin.
    env = {key: os.environ[key] for key in ("PATH", "LANG") if key in os.environ}
    # WebKit's renderer requires its public Nix EGL manifest even when all
    # provider, database and notification capabilities are stripped.
    if "__EGL_VENDOR_LIBRARY_FILENAMES" in os.environ:
        env["__EGL_VENDOR_LIBRARY_FILENAMES"] = os.environ["__EGL_VENDOR_LIBRARY_FILENAMES"]
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
    env["PYTHONPATH"] = os.pathsep.join(dict.fromkeys(
        [str(ROOT / "tests/offline_support"), str(ROOT)]
        + [p for p in sys.path if p and Path(p).is_dir()]))
    env["NODE_OPTIONS"] = "--require=" + str(ROOT / "tests/offline_support/browser_guard.cjs")
    return env


def discover_checks():
    # These DB modules require independent schemas/roles, not the legacy schema.
    # They are executed separately below, never skipped or marked xfail.
    entries = [("Python pytest", [
        sys.executable, "-m", "pytest", "tests", "-q", "--tb=short", "-ra",
        *["--ignore=" + filename for filename in DB_CHECKS.values()],
        *["--ignore=" + check["file"] for check in NORMAL_HS2.values()],
        *["--ignore=" + filename for filename in PURE_UNIT_CHECKS.values()],
    ])]
    for path in sorted((ROOT / "tests").iterdir()):
        if path.suffix == ".py" and path.name not in {
                Path(__file__).name, "run_legacy_owned.py",
                "run_owned_regression.py", "run_pytest_isolated_modules.py",
                "prepare_owned_schema.py"}:
            # These are aggregate runners/bootstrap helpers, not regression
            # checks. Discovering the incoming owned runner recurses forever.
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
    for name, filename in DB_CHECKS.items():
        entries.append((Path(filename).name, [sys.executable, "-m", "unittest",
                                             "discover", "-s", "tests", "-p",
                                             Path(filename).name, "-v"]))
    for check in NORMAL_HS2.values():
        entries.append((Path(check["file"]).name, [sys.executable, "-m", "unittest",
                        "discover", "-s", "tests", "-p", Path(check["file"]).name, "-v"]))
    for name in PURE_UNIT_CHECKS:
        entries.append((name, [sys.executable, "-m", "unittest", "discover",
                              "-s", "tests", "-p", name, "-v"]))
    return entries


def execute(name, command, timeout, logfile):
    artifact_dir = (logfile.parent / "captures" / name
                    if logfile.parent.resolve().is_relative_to(ROOT / "generated-artifacts")
                    else new_run_directory() / name)
    if name in PURE_UNIT_CHECKS:
        # App integration tests leave enrichment workers running. Pure parser
        # checks need a private process so those workers cannot consume mocks.
        return run_check(command, cwd=ROOT, env=test_environment(), timeout=timeout, logfile=logfile)
    # Dispatch exact fixture tests without calling stage execution, state writes,
    # release, payments, production collectors or Phase 18 approval.
    for key, (filename, _screen) in BROWSER_CHECKS.items():
        if name == Path(filename).name:
            from hs2_harness.isolated_browser import run_check as browser_check
            result = browser_check(key, {"file": filename}, timeout,
                                   artifact_dir=artifact_dir)
            shutil.copyfile(ROOT / result["log"], logfile)
            return result
    for key, filename in DB_CHECKS.items():
        if name == Path(filename).name:
            from hs2_harness.isolated_postgres import run_check as db_check
            result = db_check(key, {"file": filename}, timeout)
            shutil.copyfile(ROOT / result["log"], logfile)
            return result
    for key, check in NORMAL_HS2.items():
        if name == Path(check["file"]).name:
            result = core.run_check(key, check, timeout)
            shutil.copyfile(ROOT / result["log"], logfile)
            return result
    if command[0] == "node" and "playwright" not in Path(command[1]).read_text():
        return run_check(command, cwd=ROOT, env=test_environment(),
                         timeout=timeout, logfile=logfile)
    try:
        if name == "Python pytest":
            command = [*command, "--junitxml=" + str(logfile.with_suffix(".xml"))]
        with legacy_runtime(logfile.with_suffix(".fixture.log"),
                            browser=command[0] == "node") as env:
            env["HOMENSTAY_OFFLINE_ARTIFACT_DIR"] = str(artifact_dir)
            result = run_check(command, cwd=env["HOMENSTAY_LEGACY_WORKSPACE"]
                             if name in {"smoke_test.py", "api_test.py"} else ROOT,
                             env=env, timeout=timeout, logfile=logfile)
            result["command"] = command
            if name == "Python pytest" and logfile.with_suffix(".xml").is_file():
                cases = ET.parse(logfile.with_suffix(".xml")).findall(".//testcase")
                result["test_cases"] = len(cases)
                result["skipped_cases"] = [
                    {"name": case.get("classname", "") + "." + case.get("name", ""),
                     "reason": case.find("skipped").get("message", "")}
                    for case in cases if case.find("skipped") is not None]
                result["failed_cases"] = [
                    {"name": case.get("classname", "") + "." + case.get("name", ""),
                     "detail": "".join(case.itertext())}
                    for case in cases if case.find("failure") is not None
                    or case.find("error") is not None]
            return result
    except Exception as exc:
        logfile.write_text(f"FIXTURE_SETUP: {type(exc).__name__}: {exc}\n")
        return {"exit_code": 125, "seconds": 0, "timed_out": False}


def failure_kind(result, logfile):
    if result["exit_code"] == 0:
        return None
    text = logfile.read_text(errors="replace")
    if result.get("timed_out") or result["exit_code"] == 124:
        return "timeout"
    if "FIXTURE_SETUP:" in text or "ISOLATION_FAILURE" in text:
        return "fixture_setup"
    if ("OFFLINE_ISOLATION:" in text or "only owned" in text.lower()
            or "Owned legacy test:" in text):
        return "isolation_boundary"
    # This is intentionally a candidate, not a declaration that product code
    # is faulty. Individual assertion/fixture evidence is preserved in the log.
    return "assertion_or_fixture_contract"


def main():
    def cancel_suite(_signal, _frame):
        raise SystemExit("Offline suite cancelled; cleaning up active check")
    signal.signal(signal.SIGTERM, cancel_suite)
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, default=ROOT / "generated-artifacts/offline-suite",
                        help="Parent inside generated-artifacts; each invocation creates a new run")
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
    args.results = new_run_directory(args.results)
    print("SUITE_RUN_DIR: " + str(args.results), flush=True)
    with SourcePreservation(args.results) as preservation:
        preservation.exit_code = execute_entries(entries, args)
        return preservation.exit_code


def execute_entries(entries, args):
    results = []
    for name, command in entries:
        print("RUN " + name, flush=True)
        logfile = args.results / (name.replace("/", "_") + ".log")
        # Retain the failing check identity even if setup/execution raises.
        results.append({"name": name, "exit_code": 1, "completed": False})
        (args.results / "summary.json").write_text(
            json.dumps(results, ensure_ascii=False, indent=2))
        result = execute(name, command, args.timeout, logfile)
        result.update(name=name, log=os.path.relpath(logfile, ROOT),
                      capture_dir=os.path.relpath(args.results / "captures" / name, ROOT),
                      deadline_seconds=args.timeout,
                      failure_kind=failure_kind(result, logfile))
        results[-1] = result
        (args.results / "summary.json").write_text(
            json.dumps(results, ensure_ascii=False, indent=2))
        label = "FAIL " if result["exit_code"] else (
            "PASS_WITH_SKIPS " if result.get("skipped_cases") else "PASS ")
        print(label + name
              + f" ({result['seconds']}s)", flush=True)
    failed = [entry["name"] for entry in results if entry["exit_code"]]
    print(json.dumps({"checks": len(results), "passed": len(results) - len(failed),
                      "failed": failed,
                      "skipped": [case for entry in results for case in entry.get("skipped_cases", [])]},
                     ensure_ascii=False), flush=True)
    return bool(failed)


if __name__ == "__main__":
    def cancel_suite(_signal, _frame):
        raise SystemExit("Offline suite cancelled; cleaning up active check")
    signal.signal(signal.SIGTERM, cancel_suite)
    raise SystemExit(main())
