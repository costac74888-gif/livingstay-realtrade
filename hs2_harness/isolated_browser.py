"""Exact reviewed UI suite, owned loopback fixture, credential-free Chromium."""
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from contextlib import ExitStack
from . import core

CHECK_ID="phase3-registration-ui"
TEST_FILE="tests/hs2_phase3_ui_test.cjs"
FIXTURE_CHECKS = {
    CHECK_ID: (TEST_FILE, "registration"),
    "phase4-mode-ui": ("tests/hs2_phase4_ui_test.cjs", "mode"),
    "phase5-consumer-ui": ("tests/hs2_phase5_ui_test.cjs", "consumer"),
    "phase6-listing-ui": ("tests/hs2_phase6_ui_test.cjs", "listings"),
    "phase7-calendar-ui": ("tests/hs2_phase7_ui_test.cjs", "calendar"),
    "phase8-supermap-ui": ("tests/hs2_phase8_ui_test.cjs", "supermap"),
}


def run_check(name,check,timeout):
    entry = FIXTURE_CHECKS.get(name)
    if not entry or check["file"] != entry[0]:raise core.GateError("Unreviewed browser capability")
    test_file, screen = entry
    core.GENERATED.mkdir(parents=True,exist_ok=True);log=core.GENERATED/f"{name}-{time.time_ns()}.log"
    start=time.monotonic();code=125
    with tempfile.TemporaryDirectory(prefix="hs2-browser-") as temp,log.open("w") as output, ExitStack() as stack:
        root=Path(temp);env=core.test_env(root);fixture=None;child=None
        env["HS2_FIXTURE_SCREEN"] = screen
        try:
            if screen in {"listings", "calendar", "supermap"}:
                from .owned_cluster import owned_cluster
                env = stack.enter_context(owned_cluster(env,output,
                    "test_hs2_phase8_db.py" if screen == "supermap" else
                    "test_hs2_phase7_db.py" if screen == "calendar" else "test_hs2_phase6_db.py"))
                env["PYTHONPATH"] = str(core.ROOT/"hs2_harness/isolated_guard")+os.pathsep+env["PYTHONPATH"]
            chromium=shutil.which("chromium")
            if not chromium:raise core.GateError("Local Chromium unavailable")
            port_file=root/"port"
            fixture=subprocess.Popen([sys.executable,"-B","scripts/hs2_fixture_http.py","--port-file",str(port_file)],
                                     cwd=core.ROOT,env=env,stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
            deadline=time.monotonic()+15
            while not port_file.is_file():
                if fixture.poll() is not None or time.monotonic()>deadline:raise core.GateError("Owned fixture HTTP failed")
                time.sleep(.05)
            port=int(port_file.read_text());assert 1024<=port<=65535
            env.update(HS2_FIXTURE_ORIGIN=f"http://127.0.0.1:{port}",HS2_CHROMIUM=chromium)
            # Ordinary Node suite guard unchanged. Specialized guard permits ONLY
            # this parent's literal loopback and exact Chromium executable.
            env["NODE_OPTIONS"]="--require="+str(core.ROOT/"hs2_harness/isolated_guard/browser.cjs")
            child=subprocess.Popen(["node",test_file],cwd=core.ROOT,env=env,stdout=output,
                                   stderr=subprocess.STDOUT,start_new_session=True)
            code=child.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            code=124
        except Exception as e:
            output.write(f"\nBROWSER_ISOLATION_FAILURE {type(e).__name__}: {e}\n")
        finally:
            for proc in (child,fixture):
                if proc and proc.poll() is None:
                    os.killpg(proc.pid,signal.SIGTERM)
                    try:proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
            output.write("\nIsolation: owned loopback, synthetic HTTP, no DSNs/keys, external browser requests aborted, fixture stopped.\n")
    if code==0 and "HS2_UI_PASS" not in log.read_text():code=125
    return dict(id=name,status="PASS" if code==0 else "FAIL",exit_code=code,
                seconds=round(time.monotonic()-start,3),command=["node",test_file],
                test_sha256=core.digest(core.ROOT/test_file),log=str(log.relative_to(core.ROOT)),
                log_sha256=core.digest(log),isolation="owned loopback synthetic HTTP + reviewed Chromium only")
