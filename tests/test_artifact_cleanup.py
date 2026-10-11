"""Retention tests use only disposable local folders; never service fixtures."""
import importlib.util
from contextlib import nullcontext
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from offline_support.artifact_lifecycle import MARKER, owner_identity, start_run
from offline_support.source_preservation import SourcePreservation

spec = importlib.util.spec_from_file_location("artifact_cleanup", ROOT / "scripts/cleanup_test_artifacts.py")
cleaner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cleaner)


class ArtifactCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)

    def run_dir(self, name, age=50, state="passed", checks=None, tree="offline-suite"):
        directory = self.root / "generated-artifacts" / tree / name
        directory.mkdir(parents=True)
        (directory / "capture.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 512)
        (directory / MARKER).write_text(json.dumps({
            "version": 1, "state": state, "started_at": time.time() - age * 86400 - 1,
            "finished_at": time.time() - age * 86400, "producer": "test.js",
            "failed_checks": checks or [],
            "owner": {"pid": 99999999, "boot_id": "old-boot", "start_ticks": "1"},
        }))
        return directory

    def report(self, **kwargs):
        return cleaner.cleanup(self.root, **kwargs)

    def test_default_dry_run_and_apply_leave_originals_and_baselines_unchanged(self):
        old = self.run_dir("run-old")
        recent = self.run_dir("run-recent", age=1)
        originals = self.root / "screenshots"
        originals.mkdir()
        (originals / "original.png").write_bytes(b"original")
        baseline = self.root / "frozen-baseline"
        baseline.mkdir()
        (baseline / "manifest.json").write_text("{}")
        frozen = self.run_dir("run-frozen")
        (frozen / "frozen-baseline.json").write_text("baseline")
        tracked = self.run_dir("run-tracked")
        subprocess.run(["git", "add", str(tracked.relative_to(self.root))], cwd=self.root, check=True)
        before = {p: p.read_bytes() for p in (originals / "original.png", baseline / "manifest.json",
                                             frozen / "frozen-baseline.json", tracked / MARKER)}
        report = self.report()
        self.assertEqual(report["mode"], "dry-run")
        self.assertEqual(next(r for r in report["runs"] if r["path"].endswith("run-old"))["action"], "delete")
        self.assertTrue(old.exists())
        applied = self.report(apply=True)
        self.assertFalse(old.exists())
        self.assertTrue(recent.exists())
        self.assertEqual(next(r for r in applied["runs"] if r["path"].endswith("run-old"))["action"], "deleted")
        self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_latest_failure_per_check_and_tree_survives_later_success(self):
        older = self.run_dir("run-old-fail", age=80, state="failed", checks=["a"])
        latest = self.run_dir("run-new-fail", age=60, state="failed", checks=["a"])
        other = self.run_dir("run-other-fail", age=90, state="failed", checks=["b"])
        post = self.run_dir("run-post", age=70, state="failed", tree="post-merge")
        self.run_dir("run-success", age=40)
        self.report(days=0, max_bytes=0, apply=True)
        self.assertFalse(older.exists())
        self.assertTrue(all(p.exists() for p in (latest, other, post)))
        self.assertTrue(self.report(days=0, max_bytes=0)["limit_unmet"])

    def test_capacity_only_oldest_first_and_combined_policy(self):
        old = self.run_dir("run-old", age=80)
        middle = self.run_dir("run-middle", age=45)
        newest = self.run_dir("run-new", age=1)
        total = self.report(days=None)["bytes_before"]
        old_bytes = cleaner.inventory(old)[1]
        report = self.report(days=None, max_bytes=total - old_bytes)
        actions = {r["path"].split("/")[-1]: r["action"] for r in report["runs"]}
        self.assertEqual(actions, {"run-old": "delete", "run-middle": "keep", "run-new": "keep"})
        self.assertFalse(report["limit_unmet"])
        self.report(days=30, max_bytes=total, apply=True)
        self.assertFalse(old.exists())
        self.assertFalse(middle.exists())
        self.assertTrue(newest.exists())

    def test_equal_latest_failure_timestamps_keep_all_tied_evidence(self):
        first = self.run_dir("run-fail-first", state="failed", checks=["same"])
        second = self.run_dir("run-fail-second", state="failed", checks=["same"])
        data = json.loads((first / MARKER).read_text())
        (second / MARKER).write_text(json.dumps(data))
        self.report(days=0, apply=True)
        self.assertTrue(first.exists())
        self.assertTrue(second.exists())

    def test_unmeasured_evidence_makes_size_budget_unconfirmed(self):
        run = self.run_dir("run-unsafe")
        (run / "symlink").symlink_to(self.root, target_is_directory=True)
        report = self.report(days=None, max_bytes=99999999)
        self.assertTrue(report["limit_unmet"])
        self.assertEqual(report["unmeasured_runs"], [str(run.relative_to(self.root))])

    def test_missing_output_tree_is_a_noop(self):
        report = self.report(apply=True)
        self.assertEqual(report["runs"], [])
        self.assertFalse((self.root / "generated-artifacts").exists())

    def test_active_unknown_interrupted_and_invalid_runs_are_preserved(self):
        for index, marker in enumerate((None, "broken", "[]", "{}")):
            path = self.run_dir(f"run-invalid-{index}")
            if marker is None:
                (path / MARKER).unlink()
            else:
                (path / MARKER).write_text(marker)
        active = self.run_dir("run-active")
        data = json.loads((active / MARKER).read_text())
        data["owner"] = owner_identity()
        (active / MARKER).write_text(json.dumps(data))
        interrupted = self.run_dir("run-interrupted", state="running")
        paths = list(active.parent.iterdir())
        report = self.report(days=0, max_bytes=0, apply=True)
        self.assertTrue(all(p.exists() for p in paths))
        self.assertTrue(all(r["action"] == "keep" for r in report["runs"]))
        self.assertTrue(interrupted.exists())

    def test_nested_active_and_nested_latest_failure_protect_outer_run(self):
        outer = self.run_dir("run-active-parent")
        nested = outer / "captures/capture-abc"
        nested.mkdir(parents=True)
        start_run(nested)
        failed_outer = self.run_dir("run-failed-child")
        child = failed_outer / "captures/capture-def"
        child.mkdir(parents=True)
        data = json.loads((failed_outer / MARKER).read_text())
        data.update(state="failed", failed_checks=["nested.js"])
        (child / MARKER).write_text(json.dumps(data))
        self.report(days=0, apply=True)
        self.assertTrue(outer.exists())
        self.assertTrue(failed_outer.exists())

    def test_symlinks_and_hardlinks_never_delete_targets(self):
        original = self.root / "original.png"
        original.write_bytes(b"do not delete")
        symlink_run = self.run_dir("run-symlink")
        (symlink_run / "link.png").symlink_to(original)
        hardlink_run = self.run_dir("run-hardlink")
        os.link(original, hardlink_run / "link.png")
        (symlink_run.parent / "run-link").symlink_to(self.root, target_is_directory=True)
        self.report(days=0, apply=True)
        self.assertTrue(symlink_run.exists())
        self.assertTrue(hardlink_run.exists())
        self.assertEqual(original.read_bytes(), b"do not delete")

    def test_symlink_output_roots_and_lock_refused(self):
        generated = self.root / "generated-artifacts"
        generated.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.report(apply=True)
        generated.unlink()
        generated.mkdir()
        (generated / "browser-checks").symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.report(apply=True)
        (generated / "browser-checks").unlink()
        (generated / ".artifact-cleanup.lock").unlink()
        (generated / ".artifact-cleanup.lock").symlink_to(self.root / "do-not-create")
        with self.assertRaises(OSError):
            self.report(apply=True)
        self.assertFalse((self.root / "do-not-create").exists())

    def test_changed_run_during_apply_is_refused(self):
        old = self.run_dir("run-old")
        actual = cleaner.plan
        calls = 0

        def racing(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                (old / "new.log").write_text("new evidence")
            return actual(*args, **kwargs)

        with patch.object(cleaner, "plan", side_effect=racing):
            with self.assertRaisesRegex(RuntimeError, "changed"):
                self.report(apply=True)
        self.assertTrue(old.exists())

    def test_pid_reuse_unknown_identity_and_live_identity(self):
        identity = owner_identity()
        self.assertTrue(cleaner.owner_alive(identity))
        self.assertFalse(cleaner.owner_alive(dict(identity, start_ticks="0")))
        self.assertTrue(cleaner.owner_alive({}))
        self.assertTrue(cleaner.owner_alive({"pid": -1}))
        self.assertTrue(cleaner.owner_alive(dict(identity, start_ticks=None)))

    def test_cleanup_lock_excludes_concurrent_cleanup(self):
        import fcntl
        path = self.run_dir("run-old").parent.parent / ".artifact-cleanup.lock"
        with path.open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):
                self.report(apply=True)

    def test_python_context_records_success_returned_failure_and_exception(self):
        for name, code, exc in (("pass", 0, False), ("failure", 1, False), ("exception", 0, True)):
            directory = self.root / "generated-artifacts/browser-checks" / name
            with patch("offline_support.source_preservation.fingerprint", return_value={}):
                try:
                    with SourcePreservation(directory, self.root) as preservation:
                        preservation.exit_code = code
                        if exc:
                            raise RuntimeError("failed")
                except RuntimeError:
                    if not exc:
                        raise
            data = json.loads((directory / MARKER).read_text())
            self.assertEqual(data["state"], "failed" if code or exc else "passed")
            self.assertTrue(cleaner.owner_alive(data["owner"]))

    def test_successive_post_merge_failures_keep_each_checks_latest_evidence(self):
        spec = importlib.util.spec_from_file_location("retention_post_merge", ROOT / "scripts/post_merge_checks.py")
        post_merge = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(post_merge)
        cases = [("run-frontend-old", 1, 0, 90),
                 ("run-frontend-latest", 1, 0, 80),
                 ("run-mobile-latest", 0, 1, 70),
                 ("run-pass", 0, 0, 60)]
        paths = []
        for name, frontend_code, mobile_code, age in cases:
            directory = self.run_dir(name, age=age, tree="post-merge")
            paths.append(directory)

            def execute(check, command, timeout, log):
                log.write_text("frontend evidence")
                return {"exit_code": frontend_code}

            def run_check(command, **kwargs):
                kwargs["logfile"].write_text("mobile evidence")
                return {"exit_code": mobile_code}

            with patch.object(post_merge, "execute", side_effect=execute), \
                    patch.object(post_merge, "run_check", side_effect=run_check), \
                    patch.object(post_merge, "legacy_runtime",
                                 return_value=nullcontext({"HOMENSTAY_LEGACY_WORKSPACE": str(self.root)})), \
                    patch("offline_support.source_preservation.fingerprint", return_value={}):
                with SourcePreservation(directory, self.root) as preservation:
                    preservation.exit_code = post_merge.checks(directory)
            data = json.loads((directory / MARKER).read_text())
            expected = (["frontend_distribution_test.py"] if frontend_code else
                        ["analysis_mobile_browser_test.js"] if mobile_code else [])
            self.assertEqual(data["failed_checks"], expected)
            # Simulate these completed producer processes having since exited.
            data.update(owner={"pid": 99999999, "boot_id": "old-boot", "start_ticks": "1"},
                        finished_at=time.time() - age * 86400)
            (directory / MARKER).write_text(json.dumps(data))
        self.report(days=0, max_bytes=0, apply=True)
        self.assertFalse(paths[0].exists())
        self.assertTrue(paths[1].exists(), "latest frontend failure lost")
        self.assertTrue(paths[2].exists(), "latest mobile failure lost")
        self.assertFalse(paths[3].exists())

    def test_post_merge_fixture_exception_keeps_pending_check_identity(self):
        spec = importlib.util.spec_from_file_location("retention_post_exception", ROOT / "scripts/post_merge_checks.py")
        post_merge = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(post_merge)
        directory = self.run_dir("run-exception", tree="post-merge")
        with patch.object(post_merge, "execute", return_value={"exit_code": 0}), \
                patch.object(post_merge, "legacy_runtime", side_effect=RuntimeError("fixture failed")), \
                patch("offline_support.source_preservation.fingerprint", return_value={}):
            with self.assertRaisesRegex(RuntimeError, "fixture failed"):
                with SourcePreservation(directory, self.root):
                    post_merge.checks(directory)
        data = json.loads((directory / MARKER).read_text())
        self.assertEqual(data["state"], "failed")
        self.assertEqual(data["failed_checks"], ["analysis_mobile_browser_test.js"])

    def test_source_violation_does_not_hide_check_failure_identity(self):
        directory = self.run_dir("run-source-violation")
        (directory / "summary.json").write_text(json.dumps([
            {"name": "frontend_distribution_test.py", "exit_code": 1}]))
        with patch("offline_support.source_preservation.fingerprint",
                   side_effect=[{"file": "before"}, {"file": "after"}]):
            with self.assertRaisesRegex(RuntimeError, "preservation failed"):
                with SourcePreservation(directory, self.root):
                    pass
        data = json.loads((directory / MARKER).read_text())
        self.assertEqual(set(data["failed_checks"]),
                         {"frontend_distribution_test.py", "source-preservation"})

    def test_suite_setup_exception_keeps_pending_check_identity(self):
        import run_offline_suite as suite
        directory = self.run_dir("run-suite-exception")
        with patch.object(suite, "execute", side_effect=RuntimeError("setup failed")), \
                patch("offline_support.source_preservation.fingerprint", return_value={}):
            with self.assertRaisesRegex(RuntimeError, "setup failed"):
                with SourcePreservation(directory, self.root):
                    suite.execute_entries([("failed-check.py", [])],
                                          SimpleNamespace(results=directory, timeout=1))
        data = json.loads((directory / MARKER).read_text())
        self.assertEqual(data["failed_checks"], ["failed-check.py"])

    def test_unidentified_python_failures_are_all_kept(self):
        paths = [self.run_dir("run-unknown-first", state="failed"),
                 self.run_dir("run-unknown-second", state="failed", age=40)]
        for path in paths:
            data = json.loads((path / MARKER).read_text())
            data["producer"] = "python-run"
            (path / MARKER).write_text(json.dumps(data))
        self.report(days=0, apply=True)
        self.assertTrue(all(path.exists() for path in paths))

    def test_node_metadata_on_pass_and_failure_and_live_process(self):
        # Actual capture helper, output kept in an unmanaged disposable subtree.
        (ROOT / "generated-artifacts").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "generated-artifacts") as output:
            script = ("const a = require('./tests/offline_support/capture_artifacts.cjs'); "
                      "console.log('DIR=' + a.artifactDirectory()); ")
            for code in (0, 2):
                result = subprocess.run(["node", "-e", script + f"process.exitCode={code};"],
                                        cwd=ROOT, env=dict(os.environ,
                                        HOMENSTAY_OFFLINE_ARTIFACT_DIR=output),
                                        text=True, capture_output=True)
                directory = Path(next(line[4:] for line in result.stdout.splitlines() if line.startswith("DIR=")))
                data = json.loads((directory / MARKER).read_text())
                self.assertEqual(data["state"], "failed" if code else "passed")
                self.assertFalse(cleaner.owner_alive(data["owner"]))
            child = subprocess.Popen(["node", "-e", script + "setInterval(()=>{},1000);"],
                                     cwd=ROOT, env=dict(os.environ, HOMENSTAY_OFFLINE_ARTIFACT_DIR=output),
                                     text=True, stdout=subprocess.PIPE)
            try:
                directory = Path(child.stdout.readline().strip().split(": ", 1)[1])
                data = json.loads((directory / MARKER).read_text())
                self.assertEqual(data["state"], "running")
                self.assertTrue(cleaner.owner_alive(data["owner"]))
            finally:
                child.kill()
                child.wait()
                child.stdout.close()
            self.assertEqual(json.loads((directory / MARKER).read_text())["state"], "running")

    def test_cli_default_dry_run_and_invalid_limits(self):
        command = [sys.executable, str(ROOT / "scripts/cleanup_test_artifacts.py")]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["mode"], "dry-run")
        for args in (["--keep-days", "-1"], ["--max-mib", "nan"], ["--max-mib", "inf"],
                     ["--apply", "--dry-run"]):
            result = subprocess.run(command + args, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
