"""Exercise real lowest boundaries; assertions never depend on live services."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from run_offline_suite import test_environment as isolated_env, discover_checks, failure_kind


class OwnedOfflineRuntimeTests(unittest.TestCase):
    def test_environment_never_inherits_live_configuration(self):
        from unittest.mock import patch
        with patch.dict(os.environ, {"PROD_DATABASE_URL": "do-not-inherit",
                                     "RESEND_API_KEY": "do-not-inherit",
                                     "REPLIT_DEV_DOMAIN": "do-not-inherit",
                                     "PGSERVICE": "do-not-inherit"}):
            env = isolated_env()
        for name in ("PROD_DATABASE_URL", "RESEND_API_KEY", "REPLIT_DEV_DOMAIN", "PGSERVICE"):
            self.assertNotIn(name, env)

    def test_full_collection_dispatches_every_isolated_db_module_once(self):
        from hs2_harness.isolated_postgres import FIXTURE_CHECKS
        entries = discover_checks()
        pytest = dict(entries)["Python pytest"]
        for filename in FIXTURE_CHECKS.values():
            self.assertIn("--ignore=" + filename, pytest)
            self.assertEqual(sum(name == Path(filename).name for name, _ in entries), 1)
        from run_offline_suite import NORMAL_HS2, PURE_UNIT_CHECKS
        for filename in [*(check["file"] for check in NORMAL_HS2.values()),
                         *PURE_UNIT_CHECKS.values()]:
            self.assertIn("--ignore=" + filename, pytest)
            self.assertEqual(sum(name == Path(filename).name for name, _ in entries), 1)
        self.assertNotIn("run_legacy_owned.py", dict(entries))

    def test_no_capability_denies_native_driver_and_raw_tcp(self):
        script = """
import psycopg2, socket
for connect in (psycopg2.connect,psycopg2._connect,psycopg2._psycopg.connect):
    try: connect('dbname=postgres host=127.0.0.1')
    except RuntimeError as e: assert 'OFFLINE_ISOLATION' in str(e)
    else: raise AssertionError('DB guard escaped')
for method in ('connect','connect_ex'):
    with socket.socket() as s:
        try: getattr(s,method)(('127.0.0.1',9))
        except OSError as e: assert 'OFFLINE_ISOLATION' in str(e)
        else: raise AssertionError('Raw TCP guard escaped')
"""
        subprocess.run([sys.executable, "-c", script], env=isolated_env(),
                       cwd=ROOT, check=True, timeout=15)

    def test_owned_database_pair_is_distinct_and_baseline_is_read_only(self):
        from run_legacy_owned import fixture, prepare_fixture
        with fixture() as env:
            prepare_fixture(env)
            script = """
import os,psycopg2,socket
from email_util import send_email
from sms_util import send_sms
from unittest.mock import patch
with psycopg2.connect(os.environ['DATABASE_URL']) as development:
    with development.cursor() as q:
        q.execute('SELECT current_database()')
        assert q.fetchone()[0]=='postgres'
with psycopg2.connect(os.environ['PROD_DATABASE_URL']) as baseline:
    with baseline.cursor() as q:
        q.execute('SELECT current_database()')
        assert q.fetchone()[0]=='owned_baseline'
        try: q.execute('CREATE TABLE must_not_exist(id int)')
        except psycopg2.errors.ReadOnlySqlTransaction: baseline.rollback()
        else: raise AssertionError('Baseline accepted a write')
for connect in (psycopg2.connect,psycopg2._connect,psycopg2._psycopg.connect):
    try: connect('host=127.0.0.1 dbname=postgres')
    except RuntimeError as e: assert 'owned UNIX' in str(e)
    else: raise AssertionError('Foreign DB boundary escaped')
try: socket.getaddrinfo('api.resend.com',443)
except OSError as e: assert 'DNS denied' in str(e)
else: raise AssertionError('DNS boundary escaped')
with patch('requests.sessions.Session.request',side_effect=AssertionError('delivery transport reached')):
    assert send_email('offline@example.invalid','owned','owned')[0]
    assert send_sms('01000000000','owned')[0]
"""
            subprocess.run([sys.executable, "-c", script], cwd=ROOT, env=env,
                           check=True, timeout=20)

    def test_failure_classification_does_not_turn_failures_into_success(self):
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp) / "failure.log"
            for text, code, expected in [
                ("FIXTURE_SETUP: missing server", 125, "fixture_setup"),
                ("OFFLINE_ISOLATION: denied", 1, "isolation_boundary"),
                ("AssertionError: actual UI differs", 1, "assertion_or_fixture_contract"),
                ("deadline", 124, "timeout"),
            ]:
                log.write_text(text)
                result = {"exit_code": code}
                self.assertEqual(failure_kind(result, log), expected)
                self.assertNotEqual(result["exit_code"], 0)

    def test_browser_proxy_denies_redirects_and_page_route_continue(self):
        # An unrelated local TCP listener is just as forbidden as a live host.
        # Start it outside the guarded Node process and count arrivals.
        import http.server
        import threading
        hits = []
        class Trap(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                hits.append(self.path); self.send_response(200); self.end_headers()
            def log_message(self, *args):
                pass
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Trap)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        script = r"""
const assert=require('node:assert/strict');
const http=require('node:http');
const {chromium}=require('playwright');
const trap=process.argv[1];
(async()=>{
  // This server is owned by the test and gets an explicit port capability.
  const fixture=http.createServer((req,res)=>{
    if(req.url==='/redirect'){res.writeHead(302,{Location:trap});res.end();}
    else {res.end('<h1>owned fixture</h1>');}
  });
  await new Promise(resolve=>fixture.listen(0,'127.0.0.1',resolve));
  const origin='http://127.0.0.1:'+fixture.address().port;
  const browser=await chromium.launch({executablePath:process.env.CHROMIUM,args:['--no-sandbox']});
  try {
    const page=await browser.newPage();
    await page.goto(origin);
    assert.equal(await page.locator('h1').textContent(),'owned fixture');
    assert.equal((await page.context().request.get(origin)).status(),200);
    // Caller-supplied routes cannot authorize a foreign socket.
    await page.route('**/*',r=>r.continue());
    await page.goto(trap).catch(()=>{});
    await page.goto(origin+'/redirect').catch(()=>{});
    let forbidden;
    try { forbidden=await page.context().request.get(trap); }
    catch(error) { assert.match(String(error),/403|socket|closed/i); }
    if(forbidden) assert.equal(forbidden.status(),403);
    assert.throws(()=>http.get(trap),/OFFLINE_ISOLATION/);
  } finally {await browser.close();await new Promise(resolve=>fixture.close(resolve));}
})().catch(e=>{console.error(e);process.exit(1)});
"""
        import shutil
        env = isolated_env()
        env["CHROMIUM"] = shutil.which("chromium") or ""
        try:
            subprocess.run(["node", "-e", script, f"http://127.0.0.1:{server.server_port}/trap"],
                           cwd=ROOT, env=env, check=True, timeout=40)
            self.assertEqual(hits, [], "Browser/Node escaped owned-origin proxy")
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=5)
    def test_incoming_https_capability_keeps_browser_and_preparation_owned(self):
        import http.server
        import shutil
        import threading
        from werkzeug.serving import generate_adhoc_ssl_context

        hits = []
        class Trap(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                hits.append(self.path)
                self.send_response(200); self.end_headers()
            def log_message(self, *args):
                pass
        trap = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Trap)
        trap_url = f"http://127.0.0.1:{trap.server_port}/foreign"
        class Owned(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/redirect":
                    self.send_response(302); self.send_header("Location", trap_url)
                    self.end_headers()
                else:
                    self.send_response(200); self.end_headers()
                    self.wfile.write(b"<h1>owned TLS fixture</h1>")
            def log_message(self, *args):
                pass
        # Numeric HTTPServer bind avoids even a getaddrinfo call; don't weaken
        # the parent's no-capability DNS guard to bootstrap an owned listener.
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Owned)
        server.socket = generate_adhoc_ssl_context().wrap_socket(
            server.socket, server_side=True)
        threads = [threading.Thread(target=s.serve_forever, daemon=True)
                   for s in (trap, server)]
        for thread in threads:
            thread.start()
        env = isolated_env()
        env.update(OWNED_REGRESSION_ORIGIN=f"https://127.0.0.1:{server.server_port}",
                   CHROMIUM=shutil.which("chromium") or "")
        script = r"""
const assert=require('node:assert/strict');
const {chromium,request}=require('playwright');
(async()=>{
 const origin=process.env.OWNED_REGRESSION_ORIGIN, foreign=process.argv[1];
 const api=await request.newContext();
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM,args:['--no-sandbox']});
 try {
   assert.equal((await api.get(origin)).status(),200);
   const page=await browser.newPage();
   await page.goto(origin);
   assert.equal(await page.locator('h1').textContent(),'owned TLS fixture');
   assert.equal((await page.context().request.get(origin)).status(),200);
   assert.throws(()=>api.get(foreign),/outside owned/);
   await page.route('**/*',r=>r.continue());
   await page.goto(origin+'/redirect').catch(()=>{});
   await page.goto(foreign).catch(()=>{});
   assert.throws(()=>require('node:http').get(foreign),/outside owned/);
 } finally {await api.dispose();await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
"""
        try:
            subprocess.run(["node", "-e", script, trap_url], cwd=ROOT, env=env,
                           check=True, timeout=40)
            self.assertEqual(hits, [], "HTTPS capability escaped to a foreign socket")
        finally:
            for s in (trap, server):
                s.shutdown(); s.server_close()
            for thread in threads:
                thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
