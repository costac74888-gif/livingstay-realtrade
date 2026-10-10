"""Only the registered Phase 2 fixture suite may use its private UNIX socket.

All original network, application-import and child-process prohibitions remain.
This is defense-in-depth for reviewed tests, not a hostile-code sandbox.
"""
import importlib.util
import os
from pathlib import Path
import sys
import psycopg2

native_connect = psycopg2._connect
original = Path(__file__).parents[1] / "guard" / "sitecustomize.py"
spec = importlib.util.spec_from_file_location("hs2_original_guard", original)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture_only(dsn=None, *args, **kwargs):
    host = os.environ.get("HS2_FIXTURE_SOCKET", "")
    expected = dict(host=host, port=55439, user="hs2_fixture", dbname="postgres",
                    password="", connect_timeout=5, sslmode="disable")
    if (dsn is not None or args or kwargs != expected
            or not host.startswith("/tmp/hs2-pg-")
            or not Path(host, ".hs2-fixture").is_file()):
        raise RuntimeError("HS2 Phase 2: only owned fixture UNIX socket is permitted")
    # No defaults, inherited libpq service, URL, host or production credentials.
    return native_connect(psycopg2.extensions.make_dsn(**expected))


if os.environ.get("HS2_FIXTURE_TEST") != "test_hs2_phase2_data.py":
    raise RuntimeError("HS2 isolated guard requires registered fixture suite")
psycopg2.connect = fixture_only
psycopg2._connect = fixture_only
psycopg2._psycopg.connect = fixture_only
