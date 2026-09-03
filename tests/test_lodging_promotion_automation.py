import os
import unittest
from unittest.mock import patch

import apply_lodging_promotion
import scheduled_sync


class LodgingPromotionAutomationTest(unittest.TestCase):
    def test_scheduler_uses_promotion_and_keeps_legacy_collectors_separate(self):
        stage = scheduled_sync.STAGE_MAP["lodging_promotion"]
        self.assertEqual(
            stage.command,
            ("apply_lodging_promotion.py", "--scheduled"),
        )
        self.assertNotIn("lodging_promotion", scheduled_sync.LEGACY_LODGING_STAGES)

    def test_orchestrated_scheduled_legacy_stage_is_never_started(self):
        with (
            patch.object(
                scheduled_sync,
                "_acquire_lock",
                return_value=(object(), object()),
            ),
            patch.object(scheduled_sync, "_release_lock"),
            patch.object(scheduled_sync, "_read_status", return_value=None),
            patch.object(
                scheduled_sync,
                "_read_legacy_lodging_sync_control",
                return_value={"enabled": True},
            ),
            patch.object(scheduled_sync, "_write_initial_status"),
            patch.object(scheduled_sync, "_write_status"),
            patch.object(scheduled_sync, "_run_stage") as run_stage,
            patch.object(scheduled_sync, "_write_scheduled_evidence"),
        ):
            result = scheduled_sync.run(
                selected_stage="rural",
                source="scheduled",
                orchestrated=True,
            )
        self.assertEqual(result, 0)
        run_stage.assert_not_called()

    def test_unapproved_staging_is_recorded_without_creating_manifest(self):
        writes = []
        with (
            patch.dict(
                os.environ,
                {
                    "DATABASE_URL": "postgres://production",
                    "DEV_DATABASE_URL": "postgres://development",
                    "PROD_DATABASE_URL": "postgres://production",
                },
                clear=False,
            ),
            patch.object(
                apply_lodging_promotion,
                "_write_automation_status",
                side_effect=lambda **value: writes.append(value),
            ),
            patch.object(
                apply_lodging_promotion,
                "_approved_source_readiness",
                return_value=({}, ["관광숙박업(변경 1건 미승인)"]),
            ),
            patch.object(
                apply_lodging_promotion,
                "create_production_baseline_manifest",
            ) as create_manifest,
        ):
            result = apply_lodging_promotion.run_scheduled_promotion()
            self.assertEqual(
                os.environ.get("DATABASE_URL"),
                "postgres://production",
            )
        self.assertEqual(result, 1)
        create_manifest.assert_not_called()
        self.assertEqual(writes[-1]["state"], "blocked")

    def test_approved_staging_runs_manifest_steps_in_order(self):
        phases = []

        def record_status(**value):
            if value.get("phase"):
                phases.append(value["phase"])

        with (
            patch.dict(
                os.environ,
                {
                    "DATABASE_URL": "postgres://production",
                    "DEV_DATABASE_URL": "postgres://development",
                    "PROD_DATABASE_URL": "postgres://production",
                },
                clear=False,
            ),
            patch.object(
                apply_lodging_promotion,
                "_write_automation_status",
                side_effect=record_status,
            ),
            patch.object(
                apply_lodging_promotion,
                "_approved_source_readiness",
                return_value=({"lodging": {}}, []),
            ),
            patch.object(
                apply_lodging_promotion,
                "create_production_baseline_manifest",
                return_value={"id": 17, "status": "draft", "run_id": "run-17"},
            ),
            patch.object(
                apply_lodging_promotion,
                "approve_production_manifest_automated",
                return_value={"id": 17, "status": "approved", "run_id": "run-17"},
            ) as approve,
            patch.object(
                apply_lodging_promotion,
                "run_production_manifest_dry_run",
                return_value={"id": 17, "status": "dry_run"},
            ) as dry_run,
            patch.object(
                apply_lodging_promotion,
                "apply_manifest",
                return_value={"production_writes": 3},
            ) as apply,
            patch.object(
                apply_lodging_promotion,
                "compare_production_manifest",
                return_value={"comparison_id": 5},
            ) as compare,
        ):
            result = apply_lodging_promotion.run_scheduled_promotion()

        self.assertEqual(result, 0)
        approve.assert_called_once_with(17)
        dry_run.assert_called_once_with(17)
        apply.assert_called_once_with(17, confirm_run_id="run-17")
        compare.assert_called_once_with(17)
        self.assertEqual(
            phases,
            [
                "started",
                "manifest_created",
                "promotion_approved",
                "dry_run",
                "applied",
                "parallel_comparison",
            ],
        )

    def test_post_apply_surface_regression_is_reported_as_blocked(self):
        writes = []
        with (
            patch.dict(
                os.environ,
                {
                    "DATABASE_URL": "postgres://production",
                    "DEV_DATABASE_URL": "postgres://development",
                    "PROD_DATABASE_URL": "postgres://production",
                },
                clear=False,
            ),
            patch.object(
                apply_lodging_promotion,
                "_write_automation_status",
                side_effect=lambda **value: writes.append(value),
            ),
            patch.object(
                apply_lodging_promotion,
                "_approved_source_readiness",
                return_value=({"lodging": {}}, []),
            ),
            patch.object(
                apply_lodging_promotion,
                "create_production_baseline_manifest",
                return_value={"id": 18, "status": "draft", "run_id": "run-18"},
            ),
            patch.object(
                apply_lodging_promotion,
                "approve_production_manifest_automated",
                return_value={"id": 18, "status": "approved", "run_id": "run-18"},
            ),
            patch.object(
                apply_lodging_promotion,
                "run_production_manifest_dry_run",
                return_value={"id": 18, "status": "dry_run"},
            ),
            patch.object(
                apply_lodging_promotion,
                "apply_manifest",
                return_value={"production_writes": 1},
            ),
            patch.object(
                apply_lodging_promotion,
                "compare_production_manifest",
                return_value={
                    "comparison_id": 6,
                    "major_regression_count": 1,
                    "screen_comparison": {
                        "blocking": True,
                        "blocking_reasons": ["객실 수가 허용 범위를 벗어났습니다."],
                    },
                },
            ),
        ):
            result = apply_lodging_promotion.run_scheduled_promotion()

        self.assertEqual(result, 1)
        self.assertEqual(writes[-1]["state"], "blocked")
        self.assertEqual(writes[-1]["phase"], "parallel_comparison_blocked")
        self.assertIn("객실 수", writes[-1]["last_error"])

    def test_already_applied_manifest_recheck_cannot_hide_surface_regression(self):
        writes = []
        with (
            patch.dict(
                os.environ,
                {
                    "DATABASE_URL": "postgres://production",
                    "DEV_DATABASE_URL": "postgres://development",
                    "PROD_DATABASE_URL": "postgres://production",
                },
                clear=False,
            ),
            patch.object(
                apply_lodging_promotion,
                "_write_automation_status",
                side_effect=lambda **value: writes.append(value),
            ),
            patch.object(
                apply_lodging_promotion,
                "_approved_source_readiness",
                return_value=({"lodging": {}}, []),
            ),
            patch.object(
                apply_lodging_promotion,
                "create_production_baseline_manifest",
                return_value={"id": 19, "status": "applied", "run_id": "run-19"},
            ),
            patch.object(
                apply_lodging_promotion,
                "compare_production_manifest",
                return_value={
                    "comparison_id": 7,
                    "major_regression_count": 1,
                    "screen_comparison": {
                        "blocking": True,
                        "blocking_reasons": ["전환 전 화면 기준선이 없습니다."],
                    },
                },
            ),
        ):
            result = apply_lodging_promotion.run_scheduled_promotion()

        self.assertEqual(result, 1)
        self.assertEqual(writes[-1]["state"], "blocked")
        self.assertEqual(writes[-1]["manifest_id"], 19)


if __name__ == "__main__":
    unittest.main()