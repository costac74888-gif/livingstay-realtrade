"""Run existing Python/JS suites without provider calls or outbound notifications.

The preview server must use the same offline_support guard during browser tests.
No collector entrypoints or scheduled jobs are executed.
"""
import ast
import json
import os
import signal
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    env = os.environ.copy()
    env.update({
        "HOMENSTAY_OFFLINE_TESTS":"1", "DISABLE_EXTERNAL_NOTIFICATIONS":"1",
        "RELAY_ENABLED":"0", "RELAY_USE_BLDG_HUB":"0", "RELAY_USE_RTMS":"0",
        "RELAY_TOKEN":"offline-test-realtime", "RELAY_TOKEN_BATCH":"offline-test-batch",
        "BLD_SERVICE_KEY":"offline-test-bld", "BLD_INSPECTION_SERVICE_KEY":"offline-test-inspection",
        "RTMS_SERVICE_KEY":"offline-test-rtms", "DATA_GO_KR_BROKER_API_KEY":"offline-test-broker",
    })
    env["PYTHONPATH"] = str(ROOT/"tests/offline_support")+os.pathsep+str(ROOT)
    env["NODE_OPTIONS"] = "--require="+str(ROOT/"tests/offline_support/browser_guard.cjs")
    entries = [("Python pytest", [sys.executable,"-m","pytest","tests","-q","--tb=short"])]
    for path in sorted((ROOT/"tests").iterdir()):
        if path.suffix == ".py" and path.name != Path(__file__).name:
            tree = ast.parse(path.read_text())
            unittest_suite = any(
                isinstance(node,ast.ClassDef) and any("TestCase" in ast.unparse(base) for base in node.bases)
                for node in tree.body
            )
            script = any(
                isinstance(node,ast.If) and "__name__" in ast.unparse(node.test)
                and "__main__" in ast.unparse(node.test) for node in tree.body
            )
            if script and not unittest_suite:
                entries.append((path.name,[sys.executable,str(path)]))
        elif path.suffix in (".js",".cjs"):
            entries.append((path.name,["node",str(path)]))
    folder = ROOT/".local/relay-test-results"
    folder.mkdir(parents=True,exist_ok=True)
    results=[]
    for name,command in entries:
        started = time.monotonic()
        print("RUN "+name,flush=True)
        process = subprocess.Popen(
            command,cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            text=True,start_new_session=True,
        )
        try:
            stdout,stderr = process.communicate(timeout=180)
            code = process.returncode
            output = stdout+stderr
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGKILL)
            stdout,stderr = process.communicate()
            code = 124
            output = "Test exceeded 180 seconds; test process group stopped.\n"+stdout+stderr
        logfile = folder/(name.replace("/","_")+".log")
        logfile.write_text(output)
        result={"name":name,"exit_code":code,"seconds":round(time.monotonic()-started,2),"log":str(logfile.relative_to(ROOT))}
        results.append(result)
        (folder/"summary.json").write_text(json.dumps(results,ensure_ascii=False,indent=2))
        print(("PASS " if code==0 else "FAIL ")+name+f" ({result['seconds']}s)",flush=True)
    failed = [entry["name"] for entry in results if entry["exit_code"]]
    print(json.dumps({"checks":len(results),"passed":len(results)-len(failed),"failed":failed},ensure_ascii=False),flush=True)
    return bool(failed)


if __name__ == "__main__":
    raise SystemExit(main())
