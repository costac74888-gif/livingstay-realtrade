"""Synthetic owners only; no API calls, operational DB, messages or payments."""
from contextlib import redirect_stdout
import io
import os
from pathlib import Path
import runpy
import sys
import unittest
from unittest.mock import Mock, patch
import backfill_tourapi_images as images
import backfill_building_details as details


class BatchControlTest(unittest.TestCase):
    def test_invalid_site_capability_aborts_before_application_code(self):
        root = Path(__file__).resolve().parents[1]
        with patch.dict(os.environ, {"HOMENSTAY_LEGACY_SOCKET": "/tmp/not-owned"}), \
             patch.object(os, "_exit", side_effect=SystemExit(78)) as exit_, \
             redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as stopped:
                runpy.run_path(str(root / "tests" / "owned_legacy_guard" / "sitecustomize.py"))
        self.assertEqual(stopped.exception.code, 78)
        exit_.assert_called_once_with(78)

    def test_standalone_claim_is_atomic_and_never_replaces_running_owner(self):
        conn = Mock()
        cur = conn.cursor.return_value
        for row, expected in ((None, False), ({"key": "synthetic"}, True)):
            cur.fetchone.return_value = row
            with patch.object(images, "get_conn", return_value=conn):
                self.assertEqual(images.claim_standalone_run("synthetic", "owned-test"), expected)
            sql, params = cur.execute.call_args.args
            self.assertIn("ON CONFLICT", sql)
            self.assertIn("IS DISTINCT FROM 'running'", sql)
            self.assertEqual(params[0], "synthetic")
        self.assertEqual(conn.commit.call_count, 2)

    def test_unclaimed_cli_fails_explicitly_before_api_or_writes(self):
        with patch.object(sys, "argv", ["batch", "--status-key", "synthetic",
                                       "--run-id", "new-test-owner"]), \
             patch.object(images, "_read_status", return_value={"state": "failed", "run_id": "old"}), \
             patch.object(images, "run") as run, \
             patch.object(images, "_write_status") as write, \
             redirect_stdout(io.StringIO()) as output:
            with self.assertRaises(SystemExit) as exit_:
                images.main()
            self.assertEqual(exit_.exception.code, 75)
        self.assertIn("--claim-run", output.getvalue())
        run.assert_not_called()
        write.assert_not_called()

    def test_claimed_cli_keeps_existing_run_fencing(self):
        states = [{"state": "running", "run_id": "owned"}, {"state": "running", "run_id": "owned"}]
        with patch.object(sys, "argv", ["batch", "--status-key", "synthetic",
                                       "--run-id", "owned", "--claim-run"]), \
             patch.object(images, "claim_standalone_run", return_value=True) as claim, \
             patch.object(images, "_read_status", side_effect=states), \
             patch.object(images, "run", return_value={"processed": 1}) as run, \
             patch.object(images, "_write_status") as write:
            images.main()
        claim.assert_called_once_with("synthetic", "owned")
        run.assert_called_once()
        self.assertEqual(write.call_args.args[1]["state"], "done")

    def test_cooldown_resets_counters_not_recorded_errors(self):
        failures = dict.fromkeys(details.STAGES, 3)
        state = {"stages": {"title": {"failed": 3}}, "blocked_stages": list(details.STAGES)}
        with patch.object(details, "still_owner", return_value=True), \
             patch.object(details, "_write_status") as write, \
             patch.object(details.time, "sleep") as sleep:
            self.assertTrue(details.provider_cooldown("synthetic", "owned", state,
                                                     {"err": 9}, failures))
        self.assertEqual(sleep.call_count, 5)
        self.assertEqual(failures, dict.fromkeys(details.STAGES, 0))
        self.assertEqual(state["stages"]["title"]["failed"], 3)
        self.assertEqual(state["err"], 9)
        self.assertEqual(state["provider_state"], "provider_cooldown")
        write.assert_called_once()

    def test_lost_owner_never_resets_counters_or_retries_provider(self):
        failures = dict.fromkeys(details.STAGES, 3)
        with patch.object(details, "still_owner", return_value=False), \
             patch.object(details, "_write_status"), \
             patch.object(details.time, "sleep") as sleep:
            self.assertFalse(details.provider_cooldown("synthetic", "owned", {}, {}, failures))
        self.assertEqual(failures, dict.fromkeys(details.STAGES, 3))
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
