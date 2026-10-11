"""Owned legacy schema + real HTTP, independent of HS2 stage/approval state."""
from contextlib import contextmanager
import os
from pathlib import Path
import subprocess
import sys
import time

from run_legacy_owned import ROOT, fixture, prepare_fixture
from offline_support.process_runner import stop_group


@contextmanager
def legacy_runtime(logfile, browser=False):
    with fixture() as env:
        prepare_fixture(env)
        # Initializer ran explicitly. App imports may not schedule collection,
        # notifications, migrations or other boot jobs.
        env["SKIP_STARTUP_SCHEMA_INIT"] = "1"
        env.update(
            BLD_SERVICE_KEY="offline-test-bld",
            BLD_INSPECTION_SERVICE_KEY="offline-test-inspection",
            RTMS_SERVICE_KEY="offline-test-rtms",
            DATA_GO_KR_BROKER_API_KEY="offline-test-broker",
            RELAY_ENABLED="0", RELAY_USE_BLDG_HUB="0", RELAY_USE_RTMS="0",
            RELAY_USE_ONBID="0", RELAY_USE_JUSO="0",
            RELAY_TOKEN="offline-test-realtime", RELAY_TOKEN_BATCH="offline-test-batch",
            PYTHONUNBUFFERED="1",
            TEST_LIST_ONLY_AUCTION_ID="owned-list-only",
            TEST_LIST_ONLY_JIBUN="경기도 의정부시 의정부동 9000",
        )
        server = None
        with Path(logfile).open("w") as output:
            try:
                subprocess.run([sys.executable, str(ROOT / "tests/offline_support/seed_browser.py")],
                               cwd=ROOT, env=env, check=True, timeout=30,
                               stdout=output, stderr=subprocess.STDOUT)
                if browser:
                    port_file = Path(env["HOMENSTAY_LEGACY_SOCKET"]).parent / "http-port"
                    server = subprocess.Popen(
                        [sys.executable, str(ROOT / "tests/offline_support/legacy_http.py"),
                         "--port-file", str(port_file)], env=env,
                        cwd=env["HOMENSTAY_LEGACY_WORKSPACE"], stdout=output,
                        stderr=subprocess.STDOUT, start_new_session=True)
                    deadline = time.monotonic() + 30
                    while not port_file.is_file():
                        if server.poll() is not None or time.monotonic() >= deadline:
                            raise RuntimeError("FIXTURE_SETUP: owned HTTP did not start")
                        time.sleep(.05)
                    origin = f"http://127.0.0.1:{int(port_file.read_text())}"
                    env.update(BASE_URL=origin, TEST_BASE_URL=origin,
                               HOMENSTAY_OWNED_ORIGIN=origin, TEST_BUILDING_ID="1")
                    # Sanitizers reject data: URLs; use a valid owned HTTP
                    # image instead of weakening photo validation.
                    subprocess.run([sys.executable, "-c", """
import os,psycopg2
url=os.environ['TEST_BASE_URL']+'/__offline__/photo.svg'
with psycopg2.connect(os.environ['DATABASE_URL']) as conn,conn.cursor() as q:
    q.execute("UPDATE auction_photos SET url=%s",(url,))
    q.execute(\"\"\"UPDATE auction_items SET raw=jsonb_set(raw,
        '{list,thnlImgUrlAdr}',to_jsonb(%s::text)) WHERE
        raw->'list'->>'thnlImgUrlAdr' IS NOT NULL\"\"\",(url,))
"""], env=env, cwd=ROOT, check=True, timeout=15,
                                   stdout=output, stderr=subprocess.STDOUT)
                yield env
            finally:
                if server is not None:
                    stop_group(server)
