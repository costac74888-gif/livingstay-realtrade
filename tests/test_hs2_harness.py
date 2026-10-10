"""Governance tests never import Flask, connect to DB or use a live API."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from hs2_harness import core


class HarnessTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(directory)
        doc = self.root / "docs/home_stay_2"
        doc.mkdir(parents=True)
        self.enterContext(patch.multiple(core, ROOT=self.root, DOC=doc,
                          STATE=doc / "state.json", PLAN=doc / "stages.json",
                          CHECKS=doc / "checks.json", GENERATED=self.root / "logs"))
        self.enterContext(patch.object(core, "preservation", return_value={}))
        self.enterContext(patch.object(core, "fingerprint", return_value="stable"))
        self.git = self.enterContext(patch.object(core, "git", side_effect=self.fake_git))
        state = {"current_stage": 0, "bootstrap": {"status": "PASS", "fingerprint": "stable"},
                 "events": [], "stages": {str(i): {"status": "PENDING"} for i in range(1, 19)}}
        core.atomic(core.STATE, state)
        self.plan = {"stages": [{"acceptance": [{"id": "A1", "check": "behavior"}],
                                "regression": ["regression"]}]}
        self.registry = {"behavior": {}, "regression": {}}
        self.enterContext(patch.object(core, "configuration", return_value=(self.plan, self.registry)))

    def fake_git(self, *args):
        return "head" if args == ("rev-parse", "HEAD") else ""

    def begin(self):
        core.start_stage(1)

    def test_cannot_skip_stage(self):
        with self.assertRaises(core.GateError):
            core.start_stage(2)
        self.assertFalse(any(call.args[0] == "tag" for call in self.git.call_args_list))

    def test_start_checkpoint_and_only_one_current_stage(self):
        self.begin()
        self.assertEqual(core.load(core.STATE)["stages"]["1"]["start"]["tag"], "hs2/stage-01/start")
        with self.assertRaises(core.GateError):
            core.start_stage(2)

    def test_dirty_start_does_not_tag(self):
        self.git.side_effect = lambda *args: "dirty" if args[0] == "status" else "head"
        with self.assertRaises(core.GateError):
            self.begin()
        self.assertFalse(any(call.args[0] == "tag" for call in self.git.call_args_list))

    def test_stale_bootstrap_blocks_start(self):
        with patch.object(core, "fingerprint", return_value="changed"):
            with self.assertRaises(core.GateError):
                self.begin()

    def test_null_acceptance_blocks_and_is_recorded(self):
        self.begin()
        self.plan["stages"][0]["acceptance"][0]["check"] = None
        with self.assertRaises(core.GateError):
            core.verify_stage(1, "fixture")
        self.assertEqual(core.load(core.STATE)["stages"]["1"]["status"], "BLOCKED")
        with self.assertRaises(core.GateError):
            core.finish_stage(1)

    def test_regression_failure_blocks_finish_and_next(self):
        self.begin()
        with patch.object(core, "run_check", return_value={"status": "FAIL", "id": "fixture"}):
            result = core.verify_stage(1, "fixture")
        self.assertEqual(result["status"], "FAIL")
        with self.assertRaises(core.GateError):
            core.finish_stage(1)
        with self.assertRaises(core.GateError):
            core.start_stage(2)

    def test_pass_then_changed_source_cannot_finish(self):
        self.begin()
        with patch.object(core, "run_check", return_value={"status": "PASS"}):
            core.verify_stage(1, "fixture")
        with patch.object(core, "fingerprint", return_value="new"):
            with self.assertRaises(core.GateError):
                core.finish_stage(1)

    def test_pass_does_not_imply_commit_or_complete(self):
        self.begin()
        with patch.object(core, "run_check", return_value={"status": "PASS"}):
            core.verify_stage(1, "fixture")
        self.git.side_effect = lambda *a: "dirty" if a[0] == "status" else "head"
        with self.assertRaises(core.GateError):
            core.finish_stage(1)
        self.assertEqual(core.load(core.STATE)["stages"]["1"]["status"], "PASS")

    def test_complete_checkpoint_allows_next_start_after_self_check(self):
        self.begin()
        with patch.object(core, "run_check", return_value={"status": "PASS"}):
            core.verify_stage(1, "fixture")
        core.finish_stage(1)
        core.start_stage(2)
        self.assertEqual(core.load(core.STATE)["current_stage"], 2)
        self.assertTrue(any(c.args == ("tag", "hs2/stage-01/complete", "head") for c in self.git.call_args_list))

    def test_only_current_stage_can_verify(self):
        self.begin()
        with self.assertRaises(core.GateError):
            core.verify_stage(2, "fixture")

    def test_preservation_failure_blocks_start(self):
        with patch.object(core, "preservation", side_effect=core.GateError("protected")):
            with self.assertRaises(core.GateError):
                self.begin()

    def test_manual_gate_only_records_request(self):
        result = core.request_approval("production_publish", "fixture scope")
        self.assertFalse(result["automatic_execution"])
        self.assertEqual(core.load(core.STATE)["events"][-1]["status"], "AWAITING_OWNER_APPROVAL")
        self.git.assert_not_called()

    def test_unknown_gate_is_rejected(self):
        with self.assertRaises(core.GateError):
            core.request_approval("auto_deploy", "fixture")

    def test_environment_does_not_inherit_credentials(self):
        env = core.test_env(self.root)
        for name in ["DATABASE_URL", "PROD_DATABASE_URL", "DEV_DATABASE_URL",
                     "RELAY_TOKEN", "RELAY_TOKEN_BATCH", "SOLAPI_API_SECRET", "RESEND_API_KEY"]:
            self.assertNotIn(name, env)
        self.assertEqual(env["RELAY_ENABLED"], "0")

    def test_duplicate_process_lock_is_rejected(self):
        with core.lock():
            with self.assertRaises(core.GateError):
                with core.lock():
                    pass

    def test_timeout_is_failure_and_process_group_terminated(self):
        proc = Mock(pid=999999)
        proc.wait.side_effect = [core.subprocess.TimeoutExpired("fixture", 1), 0]
        fixture = self.root / "tests/fixture.py"
        fixture.parent.mkdir()
        fixture.write_text("# fixture")
        with patch.object(core.subprocess, "Popen", return_value=proc), patch.object(core.os, "killpg") as terminate:
            result = core.run_check("timeout", {"file": "tests/fixture.py", "kind": "python"}, timeout=1)
        self.assertEqual(result["exit_code"], 124)
        self.assertEqual(result["status"], "FAIL")
        terminate.assert_called_once()


if __name__ == "__main__":
    unittest.main()
