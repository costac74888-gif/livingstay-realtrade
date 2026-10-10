"""Parent-owned ephemeral PostgreSQL; never reads DSNs or production secrets."""
import contextlib
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time

from . import core

CHECK_ID = "phase2-data-contracts"
TEST_FILE = "tests/test_hs2_phase2_data.py"
FIXTURE_CHECKS = {
    CHECK_ID: TEST_FILE,
    "phase3-registration-db": "tests/test_hs2_phase3_db.py",
    "phase4-auth-db": "tests/test_hs2_phase4_auth_db.py",
    "phase5-consumer-db": "tests/test_hs2_phase5_db.py",
    "phase6-listing-db": "tests/test_hs2_phase6_db.py",
    "phase7-calendar-db": "tests/test_hs2_phase7_db.py",
    "phase8-supermap-db": "tests/test_hs2_phase8_db.py",
    "phase9-detail-db": "tests/test_hs2_phase9_db.py",
}


def run_check(name, check, timeout):
    test_file=FIXTURE_CHECKS.get(name)
    if not test_file or check["file"] != test_file:
        raise core.GateError("Isolated DB capability requires exact reviewed fixture suite")
    core.GENERATED.mkdir(parents=True, exist_ok=True)
    log = core.GENERATED / f"{name}-{time.time_ns()}.log"
    command = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", Path(test_file).name, "-v"]
    start = time.monotonic()
    code, server = 125, None
    with log.open("w") as output, tempfile.TemporaryDirectory(prefix="hs2-pg-", dir="/tmp") as temp:
        root = Path(temp)
        sock = root / "socket"
        sock.mkdir(mode=0o700)
        (sock / ".hs2-fixture").write_text("owned ephemeral cluster")
        env = core.test_env(root)
        try:
            initdb, postgres = shutil.which("initdb"), shutil.which("postgres")
            if not initdb or not postgres:
                raise core.GateError("Local PostgreSQL binaries unavailable; no external DB fallback")
            subprocess.run([initdb, "-D", str(root / "data"), "-U", "hs2_fixture",
                            "--auth-local=trust", "--auth-host=reject", "--no-locale", "-E", "UTF8"],
                           env=env, stdout=output, stderr=subprocess.STDOUT, check=True, timeout=30)
            server = subprocess.Popen([postgres, "-D", str(root / "data"), "-h", "",
                                       "-k", str(sock), "-p", "55439"],
                                      env=env, stdout=output, stderr=subprocess.STDOUT,
                                      start_new_session=True)
            deadline = time.monotonic() + 15
            while not (sock / ".s.PGSQL.55439").exists():
                if server.poll() is not None or time.monotonic() >= deadline:
                    raise core.GateError("Isolated UNIX-socket PostgreSQL failed to start")
                time.sleep(0.05)
            env.update(HS2_FIXTURE_SOCKET=str(sock), HS2_FIXTURE_TEST=Path(test_file).name)
            env["PYTHONPATH"] = str(core.ROOT / "hs2_harness/isolated_guard") + os.pathsep + env["PYTHONPATH"]
            child = subprocess.Popen(command, cwd=core.ROOT, env=env, stdout=output,
                                     stderr=subprocess.STDOUT, start_new_session=True)
            try:
                code = child.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
                code = 124
        except Exception as exc:
            output.write(f"\nISOLATION_FAILURE {type(exc).__name__}: {exc}\n")
            code = 125
        finally:
            if server is not None and server.poll() is None:
                os.killpg(server.pid, signal.SIGTERM)
                try:
                    server.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(server.pid, signal.SIGKILL)
                    server.wait()
            output.write("\nIsolation: TCP disabled; owned /tmp UNIX socket; cluster cleaned; no app DB/provider.\n")
    if code == 0:
        text = log.read_text()
        if "Ran 0 tests" in text or "skipped=" in text or "expected failures=" in text or "\nOK\n" not in text:
            code = 125
    return dict(id=name, status="PASS" if code == 0 else "FAIL", exit_code=code,
                seconds=round(time.monotonic()-start, 3), command=command,
                test_sha256=core.digest(core.ROOT / test_file),
                log=str(log.relative_to(core.ROOT)), log_sha256=core.digest(log),
                isolation="fresh PostgreSQL /tmp cluster, UNIX socket only, deleted after suite")
