"""Owned ephemeral admin/registration UI regression. No inherited service keys."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def child(port_file):
    socket = Path(os.environ.get("HS2_FIXTURE_SOCKET", "/nonexistent"))
    if (os.environ.get("HS2_HARNESS_GUARD") != "1"
            or not str(socket).startswith("/tmp/hs2-pg-")
            or not (socket / ".hs2-fixture").is_file()
            or any(os.environ.get(k) for k in (
                "DATABASE_URL", "PROD_DATABASE_URL", "TOSS_TEST_SECRET_KEY"))):
        raise SystemExit("Owned credential-free fixture required")
    from hs2_admin.fixtures import create_fixture_app
    from hs2_workspace.fixtures import create_fixture_app as workspace_app
    from scripts.hs2_seongsu_preview import install
    from scripts.hs2_real_map_preview import install as maps
    from hs2_registration.fixture_http import LocalServer
    from wsgiref.simple_server import make_server
    from werkzeug.security import generate_password_hash
    from flask import jsonify
    app = create_fixture_app(app_factory=workspace_app)
    install(app)
    maps(app)
    # This account exists only inside this test process, never in Preview defaults.
    app.config["HS2_PREVIEW_ADMIN_HASH"] = generate_password_hash("synthetic-auth-fixture-only")
    app.add_url_rule("/__development__/status", "status", lambda: jsonify(
        database="owned_ephemeral", actual_toss=False, production_entrypoint=False))
    with make_server("127.0.0.1", 0, app, server_class=LocalServer) as server:
        Path(port_file).write_text(str(server.server_port))
        server.serve_forever()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--child")
    args = parser.parse_args()
    if args.child:
        return child(args.child)
    from hs2_harness.core import test_env
    from hs2_harness.owned_cluster import owned_cluster
    with tempfile.TemporaryDirectory(prefix="hs2-unified-", dir="/tmp") as temp:
        env = test_env(Path(temp))
        with owned_cluster(env, sys.stdout, "test_hs2_phase15_db.py") as env:
            env["PYTHONPATH"] = str(ROOT / "hs2_harness/isolated_guard") + os.pathsep + env["PYTHONPATH"]
            port_file = Path(temp) / "port"
            process = subprocess.Popen([sys.executable, "-B", __file__, "--child", str(port_file)], env=env)
            try:
                deadline = time.monotonic() + 25
                while not port_file.exists():
                    if process.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError("Owned test HTTP unavailable")
                    time.sleep(.05)
                env.update(HS2_FIXTURE_ORIGIN="http://127.0.0.1:" + port_file.read_text(),
                           HS2_CHROMIUM=shutil.which("chromium"))
                env["NODE_OPTIONS"] = "--require=" + str(ROOT / "hs2_harness/isolated_guard/browser.cjs")
                subprocess.run(["node", "scripts/verify_hs2_unified_fixture.cjs"],
                               env=env, check=True, timeout=180)
            finally:
                process.terminate()
                process.wait(timeout=10)


if __name__ == "__main__":
    main()
