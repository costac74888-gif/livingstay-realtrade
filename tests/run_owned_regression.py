"""Repeat the original 115 checks with explicit, owned SQL/browser capabilities."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import socket
import time
import signal
from contextlib import contextmanager

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from run_legacy_owned import fixture
from run_offline_suite import discover_checks
from offline_support.process_runner import run_check
from hs2_harness import core
from hs2_harness.owned_cluster import owned_cluster


@contextmanager
def browser_server(env, logfile):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    env.update(OWNED_REGRESSION_PORT=str(port),
               OWNED_REGRESSION_ORIGIN=f"https://127.0.0.1:{port}",
               BASE_URL=f"https://127.0.0.1:{port}",
               TEST_BASE_URL=f"https://127.0.0.1:{port}",
               REPLIT_DEV_DOMAIN=f"127.0.0.1:{port}")
    proc = subprocess.Popen([sys.executable, str(ROOT / "tests/owned_legacy_http.py")],
                            cwd=env["HOMENSTAY_LEGACY_WORKSPACE"], env=env,
                            stdout=logfile, stderr=subprocess.STDOUT)
    try:
        deadline = time.monotonic() + 30
        while True:
            if proc.poll() is not None:
                raise RuntimeError("Owned browser server failed; no external fallback")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=.2):
                    break
            except OSError:
                if time.monotonic() > deadline:
                    raise RuntimeError("Owned browser server startup timed out")
                time.sleep(.1)
        yield
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", action="append")
    args = parser.parse_args()
    # Keep every historical check, including the helper CLI with its required arg.
    helpers = {"prepare_owned_schema.py", "run_owned_regression.py",
               "run_pytest_isolated_modules.py", "owned_legacy_http.py"}
    entries = [(n, c) for n, c in discover_checks() if n not in helpers]
    if args.only:
        unknown = set(args.only) - set(n for n, _ in entries)
        if unknown:
            parser.error(f"Unknown original checks: {sorted(unknown)}")
        entries = [(n, c) for n, c in entries if n in args.only]
    out = ROOT / ".local/suite-audit/owned-current"
    out.mkdir(parents=True, exist_ok=True)
    _, registry = core.configuration()
    by_file = {Path(c["file"]).name: (n, c) for n, c in registry.items()}
    results = []
    with fixture() as env, (out / "hs2-pg.log").open("w") as pg_log:
        with owned_cluster(env, pg_log, "full-offline-regression") as owned_env:
            owned_env["PYTHONPATH"] += ":" + str(ROOT / "tests")
            subprocess.run([sys.executable, "-c",
                "from hs2_data.repository import connect_fixture;"
                "c=connect_fixture();c.autocommit=True;"
                "c.cursor().execute('CREATE DATABASE owned_comparator');c.close()"],
                env=owned_env, cwd=ROOT, check=True, timeout=15)
            # A separate, disposable comparator for development fingerprint
            # safety tests. This is NOT the project's production connection.
            owned_env["PROD_DATABASE_URL"] = (
                "postgresql://hs2_fixture@/owned_comparator?host="
                + owned_env["HS2_FIXTURE_SOCKET"] + "&port=55439&sslmode=disable")
            owned_env["OWNED_COMPARATOR_DATABASE"] = "owned_comparator"
            owned_env["GIT_DIR"] = str(ROOT / ".git")
            owned_env["GIT_WORK_TREE"] = str(ROOT)
            subprocess.run([sys.executable, str(ROOT / "tests/prepare_owned_schema.py")],
                           cwd=env["HOMENSTAY_LEGACY_WORKSPACE"], env=owned_env,
                           check=True, timeout=90)
            with (out / "visitor-server.log").open("w") as server_log, browser_server(owned_env, server_log):
              for name, command in entries:
                print("RUN", name, flush=True)
                registered = by_file.get(name)
                if registered and registered[1].get("isolation") == "private-browser-fixture":
                    r = core.run_check(*registered)
                else:
                    if name == "Python pytest":
                        command = [sys.executable, str(ROOT / "tests/run_pytest_isolated_modules.py")]
                    if name == "run_legacy_owned.py":
                        command = [*command, "api"]
                    r = run_check(command, cwd=env["HOMENSTAY_LEGACY_WORKSPACE"],
                                  env=owned_env, timeout=900 if name == "Python pytest" else 300,
                                  logfile=out / (name + ".log"))
                    r["log"] = str((out / (name + ".log")).relative_to(ROOT))
                r["name"] = name
                results.append(r)
                core.atomic(out / "results.json", results)
                print("PASS" if r["exit_code"] == 0 else "FAIL", name, flush=True)
    raise SystemExit(any(r["exit_code"] for r in results))


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    main()
