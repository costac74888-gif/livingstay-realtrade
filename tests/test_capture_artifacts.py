"""Output-only path mapping and preservation failures require no live services."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from offline_support.source_preservation import (
    ROOT, SourcePreservation, new_run_directory,
)


class CaptureArtifactsTests(unittest.TestCase):
    def node(self, script, **env):
        return subprocess.check_output(
            ["node", "-e", script], cwd=ROOT,
            env=dict(os.environ, **env), text=True)

    def test_standalone_runs_never_reuse_paths(self):
        script = """
const {artifactDirectory, artifactPath} = require('./tests/offline_support/capture_artifacts.cjs');
const assert = require('node:assert/strict');
const path = require('node:path');
const root = artifactDirectory();
for (const input of ['screenshots/original.png', '/tmp/capture.pdf', '../outside.jpg']) {
  const output = artifactPath(input);
  assert.ok(output.startsWith(root + path.sep));
  assert.equal(artifactPath(output), output);
}
console.log(JSON.stringify(root));
"""
        first = json.loads(self.node(script, HOMENSTAY_OFFLINE_ARTIFACT_DIR="").splitlines()[-1])
        second = json.loads(self.node(script, HOMENSTAY_OFFLINE_ARTIFACT_DIR="").splitlines()[-1])
        self.assertNotEqual(first, second)
        self.assertTrue(Path(first).is_relative_to(ROOT / "generated-artifacts"))

    def test_configured_capture_directory_cannot_be_an_original_directory(self):
        script = """
const assert = require('node:assert/strict');
const {artifactDirectory} = require('./tests/offline_support/capture_artifacts.cjs');
assert.throws(() => artifactDirectory(), /run-specific child/);
"""
        self.node(script, HOMENSTAY_OFFLINE_ARTIFACT_DIR=str(ROOT / "screenshots"))

    def test_reusing_a_configured_parent_still_creates_distinct_runs(self):
        parent = new_run_directory(ROOT / "generated-artifacts/capture-contract")
        script = """
const {artifactDirectory} = require('./tests/offline_support/capture_artifacts.cjs');
console.log(JSON.stringify(artifactDirectory()));
"""
        first = json.loads(self.node(script, HOMENSTAY_OFFLINE_ARTIFACT_DIR=str(parent)).splitlines()[-1])
        second = json.loads(self.node(script, HOMENSTAY_OFFLINE_ARTIFACT_DIR=str(parent)).splitlines()[-1])
        self.assertNotEqual(first, second)
        self.assertTrue(Path(first).is_relative_to(parent))
        self.assertTrue(Path(second).is_relative_to(parent))

    def test_changed_deleted_and_new_originals_fail_without_restoring_them(self):
        for action in ("change", "delete", "new"):
            with self.subTest(action=action), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                (root / "screenshots").mkdir()
                image = root / "screenshots/reference.png"
                source = root / "source.js"
                image.write_bytes(b"original")
                source.write_text("source")
                report = root / "generated-artifacts/run"
                with patch("offline_support.source_preservation.subprocess.check_output",
                           return_value=b"source.js\0screenshots/reference.png\0"):
                    with self.assertRaisesRegex(RuntimeError, "preservation failed"):
                        with SourcePreservation(report, root):
                            if action == "change":
                                image.write_bytes(b"changed")
                                source.write_text("changed")
                            elif action == "delete":
                                image.unlink()
                            else:
                                (root / "screenshots/new.png").write_bytes(b"new")
                result = json.loads((report / "source-preservation.json").read_text())
                self.assertFalse(result["unchanged"])
                self.assertTrue(result["changed"])
                if action == "change":
                    self.assertEqual(image.read_bytes(), b"changed")

    def test_failed_check_still_records_preserved_fingerprints(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "source.py").write_text("original")
            report = root / "generated-artifacts/run"
            with patch("offline_support.source_preservation.subprocess.check_output",
                       return_value=b"source.py\0"):
                with self.assertRaisesRegex(ValueError, "check failed"):
                    with SourcePreservation(report, root):
                        raise ValueError("check failed")
            self.assertTrue(json.loads((report / "source-preservation.json").read_text())["unchanged"])

    def test_run_parent_is_ignored_output_only_and_always_unique(self):
        parent = ROOT / "generated-artifacts/capture-contract"
        self.assertNotEqual(new_run_directory(parent), new_run_directory(parent))
        with self.assertRaises(ValueError):
            new_run_directory(ROOT / "screenshots")


if __name__ == "__main__":
    unittest.main()
