"""Owned temporary evidence only; external delivery is disabled and networking blocked."""
import contextlib
import fcntl
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ["DISABLE_EXTERNAL_NOTIFICATIONS"] = "1"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import check_test_artifact_capacity as monitor
from cleanup_test_artifacts import MARKER
from scheduled_artifact_cleanup import AUDIT_TREE

POLICY = {"version": 1, "keep_days": 30, "max_mib": 1, "interval_hours": 24}


class CapacityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        blocker = patch.object(socket.socket, "connect", side_effect=AssertionError("External I/O"))
        blocker.start()
        self.addCleanup(blocker.stop)
        no_delete = patch("cleanup_test_artifacts.shutil.rmtree",
                          side_effect=AssertionError("Monitor cannot delete"))
        no_delete.start()
        self.addCleanup(no_delete.stop)

    def evidence(self, name, *, completed=False, size=2 * 1048576, failed=False):
        path = self.root / "generated-artifacts/offline-suite" / name
        path.mkdir(parents=True)
        (path / "capture.png").write_bytes(b"x" * size)
        if completed:
            (path / MARKER).write_text(json.dumps({
                "version": 1, "state": "failed" if failed else "passed",
                "producer": "capacity-test", "failed_checks": ["capture"] if failed else [],
                "finished_at": time.time() - 60 * 86400,
                "owner": {"pid": 99999999, "boot_id": "old", "start_ticks": "1"},
            }))
        return path

    def check(self, now=100, **kwargs):
        return monitor.check_once(self.root, POLICY, now=now, **kwargs)

    def test_warn_on_actual_size_even_when_projected_cleanup_meets_limit(self):
        evidence = self.evidence("eligible", completed=True)
        result = self.check()
        self.assertEqual(result["event"], "warning")
        self.assertEqual(result["condition"], "over-limit")
        self.assertFalse(result["limit_unmet"])
        self.assertEqual(result["projected_bytes_after"], 0)
        self.assertTrue(evidence.exists())

    def test_latest_failure_and_unknown_are_not_deleted_to_fit_budget(self):
        failed = self.evidence("failed", completed=True, failed=True)
        unknown = self.evidence("unknown")
        result = self.check()
        self.assertTrue(result["limit_unmet"])
        self.assertEqual(result["condition"], "over-limit")
        self.assertTrue(failed.exists())
        self.assertTrue(unknown.exists())

    def test_unmeasured_below_limit_warns_does_not_follow_link(self):
        evidence = self.evidence("unknown", size=0)
        outside = self.root / "source.txt"
        outside.write_text("source")
        (evidence / "linked").symlink_to(outside)
        result = self.check()
        self.assertEqual(result["condition"], "unmeasured")
        self.assertFalse(result["over_limit"])
        self.assertEqual(result["unmeasured_runs"], [str(evidence.relative_to(self.root))])
        self.assertEqual(outside.read_text(), "source")

    def test_restart_dedup_recovery_and_new_incident(self):
        evidence = self.evidence("unknown")
        self.assertEqual(self.check()["event"], "warning")
        self.assertEqual(self.check(now=200)["event"], "suppressed")
        (evidence / "capture.png").write_bytes(b"small")  # operator-managed fixture
        recovered = self.check(now=300)
        self.assertEqual(recovered["event"], "recovered")
        healthy = self.check(now=400)
        self.assertEqual(healthy["event"], "none")
        self.assertEqual(healthy["last_transition"]["event"], "recovered")
        self.assertEqual(healthy["last_transition"]["at"], 300)
        (evidence / "capture.png").write_bytes(b"x" * (2 * 1048576))
        self.assertEqual(self.check(now=500)["event"], "warning")

    def test_policy_change_new_warning_and_persistent_interval(self):
        self.evidence("unknown")
        self.check()
        result = self.check(now=101, respect_interval=True)
        self.assertEqual(result["status"], "not-due")
        self.assertEqual(self.check(now=86500, respect_interval=True)["event"], "suppressed")
        changed = {**POLICY, "keep_days": 31}
        self.assertEqual(monitor.check_once(self.root, changed, now=86501,
                                          respect_interval=True)["event"], "warning")

    def test_scan_error_cannot_signal_recovery_and_is_deduplicated(self):
        self.evidence("unknown")
        self.check()
        with patch.object(monitor, "cleanup", side_effect=OSError("private path")):
            error = self.check(now=200)
            self.assertEqual(error["condition"], "check-error")
            self.assertEqual(error["event"], "warning")
            self.assertNotIn("private path", json.dumps(error))
            self.assertEqual(self.check(now=300)["event"], "suppressed")
        self.assertEqual(self.check(now=400)["event"], "warning")

    def test_corrupt_or_linked_state_refused_and_not_overwritten(self):
        self.check()
        state = self.root / "generated-artifacts" / AUDIT_TREE / monitor.STATE_FILE
        state.write_text("{broken")
        with self.assertRaises(ValueError):
            self.check(now=200)
        self.assertEqual(state.read_text(), "{broken")
        state.unlink()
        outside = self.root / "outside.json"
        outside.write_text("{}")
        state.symlink_to(outside)
        with self.assertRaises(OSError):
            self.check(now=300)
        self.assertEqual(outside.read_text(), "{}")

    def test_atomic_status_preserves_last_record_on_write_failure(self):
        self.check()
        state = self.root / "generated-artifacts" / AUDIT_TREE / monitor.STATE_FILE
        original = state.read_bytes()
        with patch.object(monitor, "write_record", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.check(now=200)
        self.assertEqual(state.read_bytes(), original)
        self.assertEqual(list(state.parent.glob(".capacity-*")), [])

    def test_cli_summary_exit_codes_and_watch_restart_visibility(self):
        policy = self.root / "policy.json"
        policy.write_text(json.dumps(POLICY))
        with patch.object(monitor, "ROOT", self.root), \
                patch.object(monitor, "POLICY_PATH", policy):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(monitor.main([]), 0)
            self.assertIn("[정상]", output.getvalue())
            self.evidence("unknown")
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(monitor.main([]), 2)
            self.assertIn("[경고]", output.getvalue())
            with contextlib.redirect_stdout(io.StringIO()) as output, \
                    patch.object(monitor.time, "sleep", side_effect=KeyboardInterrupt):
                self.assertEqual(monitor.main(["--watch"]), 0)
            self.assertIn("최근 점검", output.getvalue())
            self.assertIn("한도 초과", output.getvalue())

    def test_monitor_never_imports_delivery_or_database_modules(self):
        command = """
import os, sys
os.environ['DISABLE_EXTERNAL_NOTIFICATIONS'] = '1'
sys.path.insert(0, sys.argv[1])
import check_test_artifact_capacity
assert not {'app', 'db', 'email_util', 'sms_util', 'admin_action_center'} & set(sys.modules)
"""
        result = subprocess.run([sys.executable, "-c", command, str(ROOT / "scripts")],
                                capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode())

    def test_both_watchers_active_with_independent_control_locks(self):
        evidence = self.evidence("unknown")
        policy_path = self.root / "policy.json"
        policy_path.write_text(json.dumps(POLICY))
        command = """
import sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import importlib
module = importlib.import_module(sys.argv[2])
module.ROOT = Path(sys.argv[3])
module.POLICY_PATH = module.ROOT / 'policy.json'
sleep = time.sleep
def waiting(_):
    (module.ROOT / (sys.argv[2] + '.ready')).write_text('ready')
    while True:
        sleep(1)
module.time.sleep = waiting
sys.exit(module.main(sys.argv[4:]))
"""
        children = []
        try:
            for name, arguments in (
                    ("scheduled_artifact_cleanup", ["--enable", "--watch", "--dry-run"]),
                    ("check_test_artifact_capacity", ["--watch"])):
                child = subprocess.Popen(
                    [sys.executable, "-c", command, str(ROOT / "scripts"), name,
                     str(self.root), *arguments],
                    env={"PATH": os.environ["PATH"], "DISABLE_EXTERNAL_NOTIFICATIONS": "1"},
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                children.append(child)
                ready = self.root / (name + ".ready")
                deadline = time.monotonic() + 10
                while not ready.exists() and child.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertTrue(ready.exists(), f"{name} failed to enter its watch loop")
            self.assertTrue(all(child.poll() is None for child in children))
            state = self.root / "generated-artifacts" / AUDIT_TREE / monitor.STATE_FILE
            status = json.loads(state.read_text())
            self.assertEqual(status["condition"], "over-limit")
            self.assertEqual(status["event"], "warning")
            self.assertTrue(evidence.exists())
        finally:
            for child in children:
                child.terminate()
            for child in children:
                try:
                    child.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.communicate(timeout=5)

    def test_evidence_scan_lock_still_coordinates_with_cleaner(self):
        evidence = self.evidence("unknown")
        generated = self.root / "generated-artifacts"
        with (generated / ".artifact-cleanup.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = self.check()
        self.assertEqual(result["condition"], "check-error")
        self.assertEqual(result["error_type"], "BlockingIOError")
        self.assertEqual(self.check(now=200)["condition"], "over-limit")
        self.assertTrue(evidence.exists())


if __name__ == "__main__":
    unittest.main()
