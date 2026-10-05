"""No network/DB required: prove deadline and normal-exit child cleanup."""
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from offline_support.process_runner import run_check
from offline_support.frontend_workspace import frontend_workspace
from unittest.mock import patch


class OfflineRunnerTests(unittest.TestCase):
    def test_isolated_builder_child_imports_and_offline_guard_without_runner(self):
        root = Path(__file__).resolve().parents[1]
        script = """
import importlib.util, os, pathlib, requests
from unittest.mock import patch
assert pathlib.Path(importlib.util.find_spec('app').origin) == pathlib.Path(%r)
assert os.environ['DISABLE_EXTERNAL_NOTIFICATIONS'] == '1'
assert os.environ['SKIP_APP_BOOT_TASKS'] == '1'
# No real transport, even if the guard regresses.
with patch.object(requests.adapters.HTTPAdapter, 'send',
                  side_effect=AssertionError('transport must not be reached')):
    try:
        requests.get('https://apis.data.go.kr/offline-regression-fixture')
    except requests.RequestException as error:
        assert '외부 HTTP 호출 차단' in str(error)
    else:
        raise AssertionError('External request was not rejected')
""" % str(root / "app.py")
        with patch.dict(os.environ, {
            "PYTHONPATH": "/missing-fixture-path",
            "HOMENSTAY_OFFLINE_TESTS": "0",
        }):
            with frontend_workspace(root) as builder:
                subprocess.run([sys.executable, "-c", script],
                               cwd=builder.ROOT, check=True, timeout=15)
            self.assertEqual(os.environ["PYTHONPATH"], "/missing-fixture-path")
            self.assertEqual(os.environ["HOMENSTAY_OFFLINE_TESTS"], "0")

    def _run(self, parent_wait, timeout):
        with tempfile.TemporaryDirectory() as owned:
            folder = Path(owned)
            script = """
import os, pathlib, subprocess, sys, time
child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
pathlib.Path('child.pid').write_text(str(child.pid))
pathlib.Path('temp.path').write_text(os.environ['TMPDIR'])
pathlib.Path(os.environ['TMPDIR'], 'payload').write_text('fixture')
time.sleep(%s)
""" % parent_wait
            result = run_check(
                [sys.executable, "-c", script], cwd=folder,
                env=os.environ.copy(), timeout=timeout, logfile=folder / "output.log")
            child_pid = int((folder / "child.pid").read_text())
            proc = Path(f"/proc/{child_pid}/stat")
            self.assertTrue(not proc.exists() or proc.read_text().split()[2] == "Z",
                            "Descendant is still executing")
            self.assertFalse(Path((folder / "temp.path").read_text()).exists())
            self.assertTrue(result["process_group_cleaned"])
            self.assertTrue(result["temporary_directory_cleaned"])
            return result

    def test_deadline_kills_descendant_and_removes_temporary_data(self):
        result = self._run(60, 1)
        self.assertEqual(result["exit_code"], 124)
        self.assertTrue(result["timed_out"])

    def test_normal_parent_exit_also_cleans_leaked_child(self):
        result = self._run(0, 5)
        self.assertEqual(result["exit_code"], 0)
        self.assertFalse(result["timed_out"])

    def test_managed_python_deadline_unwinds_finally(self):
        root = Path(__file__).resolve().parents[1]
        env = dict(os.environ, HOMENSTAY_OFFLINE_TESTS="1",
                   PYTHONPATH=str(root / "tests/offline_support") + os.pathsep + str(root))
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            script = """
import pathlib, time
try:
    pathlib.Path('started').touch()
    time.sleep(60)
finally:
    pathlib.Path('rollback.done').touch()
"""
            result = run_check([sys.executable, "-c", script], cwd=folder, env=env,
                               timeout=2, logfile=folder / "output.log")
            self.assertEqual(result["exit_code"], 124)
            self.assertTrue((folder / "started").exists())
            self.assertTrue((folder / "rollback.done").exists())


if __name__ == "__main__":
    unittest.main()
