"""Persistent synthetic preview. No inherited database, PG or delivery keys.

Restarting destroys the private PostgreSQL cluster. This is a reviewed fixture
application, not the production entrypoint or real-provider payment proof.
"""
import argparse
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def serve(port):
    # The parent-only bootstrap installs the guarded driver before this file.
    socket = Path(os.environ.get("HS2_FIXTURE_SOCKET", "/nonexistent"))
    if (os.environ.get("HS2_HARNESS_GUARD") != "1"
            or not str(socket).startswith("/tmp/hs2-pg-")
            or not (socket / ".hs2-fixture").is_file()
            or any(os.environ.get(key) for key in (
                "DATABASE_URL", "PROD_DATABASE_URL", "TOSS_TEST_CLIENT_KEY",
                "TOSS_TEST_SECRET_KEY", "RESEND_API_KEY", "SOLAPI_API_KEY"))):
        raise SystemExit("Owned credential-free preview required")
    from flask import redirect
    from hs2_admin.fixtures import create_fixture_app
    from hs2_workspace.fixtures import create_fixture_app as workspace_app
    from hs2_finance.fixture_http import seed_paid
    from socketserver import TCPServer, ThreadingMixIn
    from wsgiref.simple_server import WSGIServer, WSGIRequestHandler, make_server

    class PreviewServer(ThreadingMixIn, WSGIServer):
        daemon_threads = True

        def server_bind(self):
            # Literal inbound bind only: do not re-enable DNS or outbound
            # connect to satisfy Werkzeug's address-resolution convenience.
            if self.server_address[0] != "0.0.0.0":
                raise ValueError("Literal preview bind required")
            TCPServer.server_bind(self)
            self.server_name = "owned-preview"
            self.server_port = self.socket.getsockname()[1]
            self.setup_environ()

    app = create_fixture_app(app_factory=workspace_app)
    seed_paid(app)
    from scripts.hs2_seongsu_preview import install
    install(app)

    @app.get("/")
    def index():
        return redirect("/hs2/consumer")

    @app.get("/__development__/status")
    def status():
        return {
            "synthetic_data_only": True, "database": "owned_ephemeral",
            "payment_provider": "OwnedSandbox_mock", "actual_toss": False,
            "external_delivery": False, "production_entrypoint": False,
            "reset_on_restart": True,
            "demo": "seongsu", "synthetic_stays": 14,
            "synthetic_layers": {"sale": 3, "business": 3, "auction": 3},
        }

    @app.after_request
    def preview_notice(response):
        if response.mimetype == "text/html":
            response.direct_passthrough = False
            text = response.get_data(as_text=True)
            banner = (
                '<aside role="note" style="padding:12px;background:#fff3cd;'
                'color:#332701;font:14px/1.5 sans-serif">'
                '<b>개발용 가상 데이터 Preview</b> · 실제 개인정보를 입력하지 마세요.'
                ' 결제는 OwnedSandbox 모의 처리이며 실제 토스가 아닙니다.'
                ' 이메일·문자·지급은 차단됩니다. 재시작하면 데이터가 초기화됩니다.'
                ' 로그인·신원은 검사 fixture이며 운영 인증을 대체하지 않습니다.'
                '</aside>'
            )
            import re
            text = re.sub(r"(<body\b[^>]*>)", r"\1" + banner, text, count=1,
                          flags=re.IGNORECASE)
            response.set_data(text)
            response.headers.pop("ETag", None)
            response.headers.pop("Last-Modified", None)
        response.headers["Cache-Control"] = "no-store, private"
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return response

    with make_server("0.0.0.0", port, app, server_class=PreviewServer,
                     handler_class=WSGIRequestHandler) as http:
        print("Synthetic Preview ready; no production DSN or provider keys loaded.",
              flush=True)
        http.serve_forever()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()
    if args.serve:
        serve(args.port)
        return
    from hs2_harness.core import test_env
    from hs2_harness.owned_cluster import owned_cluster

    with tempfile.TemporaryDirectory(prefix="hs2-preview-", dir="/tmp") as tmp:
        env = test_env(Path(tmp))
        with owned_cluster(env, sys.stdout, "test_hs2_phase15_db.py") as env:
            env["PYTHONPATH"] = str(ROOT / "hs2_harness/isolated_guard") + os.pathsep + env["PYTHONPATH"]
            child = subprocess.Popen(
                [sys.executable, "-B", __file__, "--serve", "--port", str(args.port)],
                cwd=ROOT, env=env, start_new_session=True)
            def stop(*_):
                if child.poll() is None:
                    os.killpg(child.pid, signal.SIGTERM)
            signal.signal(signal.SIGTERM, stop)
            signal.signal(signal.SIGINT, stop)
            try:
                raise SystemExit(child.wait())
            finally:
                stop()
                try:
                    child.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait()


if __name__ == "__main__":
    main()
