"""Disposable local repositories only: no app, database, mail or browser access."""
from contextlib import redirect_stdout, redirect_stderr
import fcntl
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import scheduled_artifact_cleanup as scheduler
from cleanup_test_artifacts import MARKER, owner_alive
sys.path.insert(0, str(ROOT / "tests"))
from offline_support.artifact_lifecycle import owner_identity

POLICY = {"version": 1, "keep_days": 30, "max_mib": 2048, "interval_hours": 24}


class ScheduledCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)

    def run_dir(self, name, state="passed", age=60, checks=None):
        directory = self.root / "generated-artifacts/offline-suite" / name
        directory.mkdir(parents=True)
        (directory / "capture.png").write_bytes(b"capture")
        (directory / MARKER).write_text(json.dumps({
            "version": 1, "state": state, "producer": "capture.js",
            "finished_at": time.time() - age * 86400,
            "failed_checks": checks or [],
            "owner": {"pid": 99999999, "boot_id": "old-boot", "start_ticks": "1"},
        }))
        return directory

    def run_cleanup(self, **kwargs):
        return scheduler.run_once(self.root, POLICY, enabled=True, **kwargs)

    def audit_logs(self):
        return sorted((self.root / "generated-artifacts" / scheduler.AUDIT_TREE).glob("*.json"))

    def test_disabled_default_has_no_side_effect_even_with_apply(self):
        self.assertEqual(scheduler.run_once(self.root, None, apply=True)["status"], "disabled")
        self.assertFalse((self.root / "generated-artifacts").exists())
        with patch.object(scheduler, "ROOT", self.root), redirect_stdout(io.StringIO()):
            self.assertEqual(scheduler.main(["--apply"]), 0)
        self.assertFalse((self.root / "generated-artifacts").exists())

    def test_policy_requires_explicit_positive_integer_values(self):
        for key in ("keep_days", "max_mib", "interval_hours"):
            for value in (True, 0, -1, 1.5, None, float("nan"), "30"):
                policy = {**POLICY, key: value}
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    scheduler.run_once(self.root, policy, enabled=True)
        for policy in ({}, {**POLICY, "force": True}, {**POLICY, "version": True}):
            with self.assertRaises(ValueError):
                scheduler.validate_policy(policy)
        self.assertFalse((self.root / "generated-artifacts").exists())

    def test_preview_required_for_apply_and_exact_policy_including_interval(self):
        old = self.run_dir("old")
        for receipt in (None, "../../escape", "a" * 32):
            with self.assertRaises((ValueError, FileNotFoundError)):
                self.run_cleanup(apply=True, receipt=receipt)
        preview = self.run_cleanup()
        self.assertTrue(old.exists())
        for key in ("keep_days", "max_mib", "interval_hours"):
            with self.assertRaises(ValueError):
                scheduler.run_once(self.root, {**POLICY, key: POLICY[key] + 1},
                                   enabled=True, apply=True, receipt=preview["receipt"])
        applied = self.run_cleanup(apply=True, receipt=preview["receipt"])
        self.assertFalse(old.exists())
        self.assertEqual(applied["report"]["runs"][0]["action"], "deleted")
        with self.assertRaises(ValueError):
            self.run_cleanup(apply=True, receipt=applied["receipt"])
        logs = [json.loads(p.read_text()) for p in self.audit_logs()]
        self.assertEqual(len(logs), 2)
        self.assertEqual(logs[-1]["policy"], POLICY)
        self.assertEqual({r["status"] for r in logs}, {"finished"})

    def test_incomplete_and_error_receipts_cannot_authorize_deletion(self):
        old = self.run_dir("old")
        preview = self.run_cleanup()
        path = self.root / "generated-artifacts" / scheduler.AUDIT_TREE / (preview["receipt"] + ".json")
        for status in ("running", "error"):
            path.write_text(json.dumps({**preview, "status": status}))
            with self.assertRaises(ValueError):
                self.run_cleanup(apply=True, receipt=preview["receipt"])
        self.assertTrue(old.exists())

    def test_persistent_interval_and_separate_mode_clock(self):
        old = self.run_dir("old")
        preview = self.run_cleanup(now=100)
        result = self.run_cleanup(now=101)
        self.assertEqual(result["status"], "not-due")
        self.assertEqual(result["next_due_at"], 86500)
        applied = self.run_cleanup(now=101, apply=True, receipt=preview["receipt"])
        self.assertEqual(applied["status"], "finished")
        self.assertFalse(old.exists())
        self.assertEqual(self.run_cleanup(now=102, apply=True,
                                         receipt=preview["receipt"])["status"], "not-due")
        self.assertEqual(self.run_cleanup(now=86500)["status"], "finished")
        self.assertEqual(len(self.audit_logs()), 3)

    def test_errors_are_saved_before_raising_and_throttle_restarts(self):
        self.run_dir("old")
        with patch.object(scheduler, "cleanup", side_effect=RuntimeError("changed run")):
            with self.assertRaisesRegex(RuntimeError, "changed run"):
                self.run_cleanup(now=100)
        log = json.loads(self.audit_logs()[0].read_text())
        self.assertEqual(log["status"], "error")
        self.assertIn("changed run", log["error"])
        self.assertEqual(self.run_cleanup(now=101)["status"], "not-due")
        # Simulate forced termination leaving only the durable start record.
        log["status"] = "running"
        self.audit_logs()[0].write_text(json.dumps(log))
        self.assertEqual(self.run_cleanup(now=102)["status"], "not-due")

    def test_durable_start_record_exists_before_cleanup(self):
        def check_start(**kwargs):
            logs = [json.loads(p.read_text()) for p in self.audit_logs()]
            self.assertEqual(logs[0]["status"], "running")
            self.assertEqual(logs[0]["policy"], POLICY)
            raise RuntimeError("stop")
        with patch.object(scheduler, "cleanup", side_effect=check_start):
            with self.assertRaises(RuntimeError):
                self.run_cleanup()

    def test_scheduler_lock_excludes_second_process(self):
        command = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import scheduled_artifact_cleanup as s
try:
    s.run_once(Path(sys.argv[2]), s.validate_policy(__import__('json').loads(sys.argv[3])), enabled=True)
except BlockingIOError:
    sys.exit(7)
sys.exit(8)
"""
        with scheduler.audit_lock(self.root):
            result = subprocess.run([sys.executable, "-c", command, str(ROOT / "scripts"),
                                     str(self.root), json.dumps(POLICY)], capture_output=True)
        self.assertEqual(result.returncode, 7, result.stderr.decode())
        self.assertEqual(self.audit_logs(), [])

    def test_manual_cleanup_lock_remains_effective_and_logged(self):
        old = self.run_dir("old")
        preview = self.run_cleanup()
        with (self.root / "generated-artifacts/.artifact-cleanup.lock").open("r+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):
                self.run_cleanup(apply=True, receipt=preview["receipt"])
        self.assertTrue(old.exists())
        self.assertIn("error", [json.loads(p.read_text())["status"] for p in self.audit_logs()])

    def test_apply_preserves_all_exclusions_and_latest_failure_per_check(self):
        old = self.run_dir("old")
        unknown = self.run_dir("unknown")
        (unknown / MARKER).unlink()
        live = self.run_dir("live")
        data = json.loads((live / MARKER).read_text())
        data["owner"] = owner_identity()
        self.assertTrue(owner_alive(data["owner"]))
        (live / MARKER).write_text(json.dumps(data))
        active_nested = self.run_dir("nested")
        nested = active_nested / "capture"
        nested.mkdir()
        (nested / MARKER).write_text(json.dumps(data))
        frozen = self.run_dir("frozen")
        (frozen / "frozen-baseline.json").write_text("{}")
        tracked = self.run_dir("tracked")
        subprocess.run(["git", "add", str(tracked.relative_to(self.root))], cwd=self.root, check=True)
        older_failure = self.run_dir("older-failure", state="failed", age=90, checks=["a"])
        latest_failure = self.run_dir("latest-failure", state="failed", age=80, checks=["a"])
        separate_failure = self.run_dir("separate-failure", state="failed", age=100, checks=["b"])
        original = self.root / "screenshots/original.png"
        original.parent.mkdir()
        original.write_bytes(b"original")
        preview = self.run_cleanup()
        result = self.run_cleanup(apply=True, receipt=preview["receipt"])
        self.assertEqual(result["status"], "finished")
        self.assertFalse(old.exists())
        self.assertFalse(older_failure.exists())
        for path in (unknown, live, active_nested, frozen, tracked, latest_failure, separate_failure):
            self.assertTrue(path.exists(), path)
        self.assertEqual(original.read_bytes(), b"original")
        self.assertTrue(self.audit_logs())

    def test_preview_list_is_not_reused_new_failure_is_protected(self):
        old = self.run_dir("old")
        preview = self.run_cleanup()
        data = json.loads((old / MARKER).read_text())
        data.update(state="failed", failed_checks=["a"])
        (old / MARKER).write_text(json.dumps(data))
        result = self.run_cleanup(apply=True, receipt=preview["receipt"])
        self.assertTrue(old.exists())
        self.assertEqual(result["report"]["runs"][0]["reason"], "latest failure evidence")

    def test_unmet_budget_is_reported_without_protection_override(self):
        unknown = self.run_dir("unknown")
        (unknown / MARKER).unlink()
        (unknown / "capture.png").write_bytes(b"x" * (2 * 1048576))
        policy = {**POLICY, "max_mib": 1}
        preview = scheduler.run_once(self.root, policy, enabled=True)
        result = scheduler.run_once(self.root, policy, enabled=True,
                                    apply=True, receipt=preview["receipt"])
        self.assertTrue(result["report"]["limit_unmet"])
        self.assertTrue(unknown.exists())

    def test_symlinked_audit_and_generated_roots_refused(self):
        outside = self.root / "outside"
        outside.mkdir()
        generated = self.root / "generated-artifacts"
        generated.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(OSError):
            self.run_cleanup()
        generated.unlink()
        generated.mkdir()
        (generated / scheduler.AUDIT_TREE).symlink_to(outside, target_is_directory=True)
        with self.assertRaises(OSError):
            self.run_cleanup()
        self.assertEqual(list(outside.iterdir()), [])

    def test_symlink_and_hardlinked_audit_files_refused(self):
        preview = self.run_cleanup()
        log = self.audit_logs()[0]
        outside = self.root / "copy.json"
        log.rename(outside)
        log.symlink_to(outside)
        with self.assertRaises(OSError):
            self.run_cleanup(apply=True, receipt=preview["receipt"])
        log.unlink()
        os.link(outside, log)
        with self.assertRaises(ValueError):
            self.run_cleanup(apply=True, receipt=preview["receipt"])

    def test_corrupt_audit_refuses_schedule(self):
        self.run_cleanup()
        self.audit_logs()[0].write_text("{broken")
        with self.assertRaises(ValueError):
            self.run_cleanup()

    def test_watch_stops_on_policy_edit_without_adopting_it(self):
        policy_path = self.root / "policy.json"
        policy_path.write_text(json.dumps(POLICY))
        def edit_policy(_):
            policy_path.write_text(json.dumps({**POLICY, "keep_days": 1}))
        with patch.object(scheduler, "ROOT", self.root), \
                patch.object(scheduler, "POLICY_PATH", policy_path), \
                patch.object(scheduler.time, "sleep", side_effect=edit_policy), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as stderr:
            self.assertEqual(scheduler.main(["--enable", "--watch"]), 1)
        self.assertIn("Policy changed", stderr.getvalue())
        self.assertEqual(len(self.audit_logs()), 1)

    def test_explicit_preview_bypasses_due_and_cli_invalid_modes(self):
        policy_path = self.root / "policy.json"
        policy_path.write_text(json.dumps(POLICY))
        with patch.object(scheduler, "ROOT", self.root), \
                patch.object(scheduler, "POLICY_PATH", policy_path), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(scheduler.main(["--enable", "--dry-run"]), 0)
            self.assertEqual(scheduler.main(["--enable", "--dry-run"]), 0)
            self.assertEqual(len(self.audit_logs()), 2)
            self.assertEqual(scheduler.main(["--enable", "--apply"]), 1)
            with self.assertRaises(SystemExit):
                scheduler.main(["--enable", "--apply", "--dry-run"])


if __name__ == "__main__":
    unittest.main()
