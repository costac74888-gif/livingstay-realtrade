"""Scoped PostgreSQL for combined real HTTP/browser persistence checks."""
from contextlib import contextmanager
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time
from .core import GateError


@contextmanager
def owned_cluster(base_env, output, test_name):
    if test_name not in {"test_hs2_phase6_db.py", "test_hs2_phase7_db.py", "test_hs2_phase8_db.py", "test_hs2_phase9_db.py"}:
        raise GateError("Unreviewed combined DB capability")
    proc = None
    with tempfile.TemporaryDirectory(prefix="hs2-pg-", dir="/tmp") as temp:
        root = Path(temp)
        sock = root / "socket"
        sock.mkdir(mode=0o700)
        (sock / ".hs2-fixture").write_text("owned ephemeral cluster")
        env = dict(base_env)
        try:
            initdb, postgres = shutil.which("initdb"), shutil.which("postgres")
            if not initdb or not postgres:
                raise GateError("No local PostgreSQL; no external fallback")
            subprocess.run([initdb, "-D", str(root / "data"), "-U", "hs2_fixture",
                            "--auth-local=trust", "--auth-host=reject", "--no-locale", "-E", "UTF8"],
                           env=env, stdout=output, stderr=subprocess.STDOUT, check=True, timeout=30)
            proc = subprocess.Popen([postgres, "-D", str(root / "data"), "-h", "",
                                     "-k", str(sock), "-p", "55439"], env=env,
                                    stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
            deadline = time.monotonic() + 15
            while not (sock / ".s.PGSQL.55439").exists():
                if proc.poll() is not None or time.monotonic() > deadline:
                    raise GateError("Owned PostgreSQL start failure")
                time.sleep(.05)
            env.update(HS2_FIXTURE_SOCKET=str(sock), HS2_FIXTURE_TEST=test_name)
            yield env
        finally:
            if proc and proc.poll() is None:
                proc.send_signal(signal.SIGTERM)
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
            output.write("\nCombined browser PostgreSQL: UNIX only, no app DSN, deleted after test.\n")
