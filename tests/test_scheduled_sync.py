import os
import unittest
from unittest.mock import patch

import scheduled_sync


class ScheduledSyncPlanTests(unittest.TestCase):
    def test_building_api_stages_do_not_share_a_weekday(self):
        registry = scheduled_sync.STAGE_MAP["building_registry"]
        permits = scheduled_sync.STAGE_MAP["building_permits"]
        self.assertTrue(set(registry.weekdays).isdisjoint(permits.weekdays))

    def test_fresh_run_obeys_stage_cadence(self):
        stages = scheduled_sync.prepare_stage_statuses(None, weekday=0)
        self.assertEqual(stages["building_registry"]["state"], "pending")
        self.assertEqual(stages["building_permits"]["state"], "skipped")
        self.assertEqual(stages["rural_hanok"]["state"], "pending")

    def test_failed_run_keeps_successful_stages_for_resume(self):
        previous = {
            "state": "failed",
            "stages": {
                "transactions": {
                    "key": "transactions",
                    "label": "실거래",
                    "state": "done",
                    "finished_at": "2026-08-30 02:10:00",
                },
                "lodging": {
                    "key": "lodging",
                    "label": "일반·생활숙박·캠핑",
                    "state": "failed",
                },
            },
        }
        stages = scheduled_sync.prepare_stage_statuses(previous, weekday=0)
        self.assertEqual(stages["transactions"]["state"], "done")
        self.assertTrue(stages["transactions"]["resumed"])
        self.assertEqual(stages["lodging"]["state"], "pending")

    def test_selected_retry_runs_only_one_stage(self):
        stages = scheduled_sync.prepare_stage_statuses(
            {"state": "failed"},
            weekday=6,
            selected_stage="rural_hanok",
        )
        self.assertEqual(stages["rural_hanok"]["state"], "pending")
        self.assertTrue(
            all(
                item["state"] == "skipped"
                for key, item in stages.items()
                if key != "rural_hanok"
            )
        )

    def test_failed_cadence_stage_retries_on_another_weekday(self):
        previous = {
            "state": "failed",
            "stages": {
                "building_registry": {"state": "failed", "error": "quota"},
                "building_permits": {"state": "skipped"},
            },
        }
        stages = scheduled_sync.prepare_stage_statuses(previous, weekday=5)
        self.assertEqual(stages["building_registry"]["state"], "pending")
        self.assertEqual(stages["building_permits"]["state"], "pending")

    def test_manual_retry_runs_only_failed_or_interrupted_stages(self):
        previous = {
            "state": "failed",
            "stages": {
                "building_registry": {"state": "failed", "error": "quota"},
                "building_permits": {"state": "skipped"},
                "lodging": {"state": "done"},
            },
        }
        stages = scheduled_sync.prepare_stage_statuses(
            previous,
            weekday=5,
            retry_failures_only=True,
        )
        self.assertEqual(stages["building_registry"]["state"], "pending")
        self.assertEqual(stages["building_permits"]["state"], "skipped")
        self.assertEqual(stages["lodging"]["state"], "done")

    def test_outer_runner_does_not_pass_unclaimed_child_status_keys(self):
        self.assertNotIn(
            "--status-key",
            scheduled_sync.STAGE_MAP["building_registry"].command,
        )
        self.assertNotIn(
            "--status-key",
            scheduled_sync.STAGE_MAP["lodging"].command,
        )
        self.assertNotIn(
            "--status-key",
            scheduled_sync.STAGE_MAP["brokers"].command,
        )

    def test_child_nonzero_exit_marks_outer_stage_failed(self):
        writes = []
        with (
            patch.object(scheduled_sync, "_acquire_lock", return_value=(object(), object())),
            patch.object(scheduled_sync, "_release_lock"),
            patch.object(scheduled_sync, "_read_status", return_value=None),
            patch.object(scheduled_sync, "_write_initial_status"),
            patch.object(
                scheduled_sync,
                "_write_status",
                side_effect=lambda key, value, run_id=None: writes.append(
                    {**value, "stages": {
                        k: dict(v) for k, v in value["stages"].items()
                    }},
                ),
            ),
            patch.object(scheduled_sync, "_source_busy", return_value=None),
            patch.object(scheduled_sync, "_metric_value", return_value=0),
            patch.object(scheduled_sync, "_run_stage", return_value=(1, ["inner failure"])),
        ):
            result = scheduled_sync.run(selected_stage="lodging")
        self.assertEqual(result, 1)
        self.assertEqual(writes[-1]["state"], "failed")
        self.assertEqual(writes[-1]["stages"]["lodging"]["state"], "failed")
        self.assertTrue(writes[-1]["stages"]["lodging"]["retryable"])

    def test_secret_values_are_redacted(self):
        with patch.dict(os.environ, {"LODGING_SERVICE_KEY": "top-secret"}):
            self.assertEqual(
                scheduled_sync._redact("failed top-secret"),
                "failed ***",
            )


if __name__ == "__main__":
    unittest.main()