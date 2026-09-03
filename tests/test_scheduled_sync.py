import os
import signal
import unittest
from pathlib import Path
from unittest.mock import patch

import scheduled_sync
from scheduled_sync_state import reconcile_stage_state, stage_displayed_running
import quota_policy


class ScheduledSyncPlanTests(unittest.TestCase):
    def test_collection_progress_parser_handles_api_and_work_units(self):
        self.assertEqual(
            scheduled_sync._parse_collection_progress(
                "[rural] 1페이지 100건 (누적 원본 100 / API 55,419)"
            ),
            (100, 55419, "원본"),
        )
        self.assertEqual(
            scheduled_sync._parse_collection_progress(
                "[hanok] 1페이지 100건 (누적 원본 100 / API 3,164)"
            ),
            (100, 3164, "원본"),
        )
        self.assertEqual(
            scheduled_sync._parse_collection_progress(
                "[수집진행] 시군구 17/250"
            ),
            (17, 250, "시군구"),
        )

    def test_admin_lodging_source_button_calls_current_stage_handler(self):
        html = Path("static/admin.html").read_text(encoding="utf-8")
        self.assertIn("function renderLodgingSourceOverview(data)", html)
        self.assertIn("async function runLodgingSourceStage(stage, button)", html)
        self.assertIn(
            'runLodgingSourceStage(btn.dataset.stage, btn)',
            html,
        )
        self.assertIn('fetch("/api/admin/scheduled-sync/run"', html)
        self.assertIn('button.textContent = "시작하는 중…"', html)
        self.assertIn('${running ? "실행 중…" : "지금 동기화"}', html)

    def test_building_api_stages_do_not_share_a_weekday(self):
        registry = scheduled_sync.STAGE_MAP["building_registry"]
        permits = scheduled_sync.STAGE_MAP["building_permits"]
        self.assertTrue(set(registry.weekdays).isdisjoint(permits.weekdays))

    def test_recent_transaction_stage_skips_juso_address_prepare(self):
        command = scheduled_sync.STAGE_MAP["transactions"].command
        self.assertIn("--skip-address-prepare", command)

    def test_fresh_run_obeys_stage_cadence(self):
        stages = scheduled_sync.prepare_stage_statuses(None, weekday=0)
        self.assertEqual(stages["building_registry"]["state"], "pending")
        self.assertEqual(stages["building_permits"]["state"], "skipped")
        self.assertEqual(stages["camping"]["state"], "pending")
        self.assertEqual(stages["rural"]["state"], "pending")
        self.assertEqual(stages["hanok"]["state"], "pending")
        self.assertEqual(stages["building_geocode"]["state"], "pending")
        self.assertEqual(stages["title_info"]["state"], "pending")

    def test_manual_full_run_ignores_scheduled_weekday_cadence(self):
        stages = scheduled_sync.prepare_stage_statuses(
            None,
            weekday=6,
            ignore_cadence=True,
        )
        self.assertTrue(all(stage["state"] == "pending" for stage in stages.values()))

    def test_manual_single_stage_labels_other_stages_as_waiting(self):
        stages = scheduled_sync.prepare_stage_statuses(
            None,
            weekday=6,
            selected_stage="hanok",
            ignore_cadence=True,
        )
        self.assertEqual(stages["hanok"]["state"], "pending")
        self.assertEqual(stages["transactions"]["state"], "not_selected")

    def test_scheduled_run_uses_korea_weekday_for_cadence(self):
        writes = []
        with patch.object(scheduled_sync, "_korea_weekday", return_value=1) as weekday:
            with (
                patch.object(scheduled_sync, "_acquire_lock", return_value=(object(), object())),
                patch.object(scheduled_sync, "_release_lock"),
                patch.object(scheduled_sync, "_read_status", return_value=None),
                patch.object(scheduled_sync, "_write_initial_status"),
                patch.object(
                    scheduled_sync,
                    "_write_status",
                    side_effect=lambda key, value, run_id: writes.append(
                        {**value, "stages": {
                            k: dict(v) for k, v in value["stages"].items()
                        }}
                    ),
                ),
                patch.object(scheduled_sync, "_write_scheduled_evidence"),
                patch.object(scheduled_sync, "_source_busy", return_value=None),
                patch.object(scheduled_sync, "_metric_value", return_value=0),
                patch.object(scheduled_sync, "_run_stage", return_value=(0, [])),
            ):
                self.assertEqual(scheduled_sync.run(), 0)
        weekday.assert_called_once_with()
        final = writes[-1]
        self.assertEqual(final["stages"]["building_registry"]["state"], "skipped")
        self.assertEqual(final["stages"]["building_permits"]["state"], "done")

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
                    "label": "일반·생활숙박",
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
            selected_stage="rural",
        )
        self.assertEqual(stages["rural"]["state"], "pending")
        self.assertTrue(
            all(
                item["state"] == "not_selected"
                for key, item in stages.items()
                if key != "rural"
            )
        )

    def test_stage_status_keeps_last_result_history(self):
        stages = scheduled_sync.prepare_stage_statuses(
            {"state": "done", "stages": {
                "lodging": {"state": "done", "finished_at": "2026-08-30 02:10:00"}
            }},
            weekday=0,
            selected_stage="lodging",
        )
        self.assertEqual(stages["lodging"]["last_success_at"], "2026-08-30 02:10:00")
        self.assertIsNone(stages["lodging"]["last_error"])

    def test_manual_source_is_recorded_before_stage_work(self):
        writes = []
        with (
            patch.object(scheduled_sync, "_acquire_lock", return_value=(object(), object())),
            patch.object(scheduled_sync, "_release_lock"),
            patch.object(scheduled_sync, "_read_status", return_value={
                "run_id": "manual-claim", "state": "running", "stages": {}
            }),
            patch.object(scheduled_sync, "_write_initial_status"),
            patch.object(scheduled_sync, "_write_status",
                         side_effect=lambda key, value, run_id: writes.append(dict(value))),
            patch.object(scheduled_sync, "_source_busy", return_value=None),
            patch.object(scheduled_sync, "_metric_value", return_value=0),
            patch.object(scheduled_sync, "_run_stage", return_value=(0, [])),
            patch.object(scheduled_sync, "_write_scheduled_evidence") as evidence,
        ):
            scheduled_sync.run(selected_stage="lodging", source="manual", run_id="manual-claim")
        self.assertEqual(writes[0]["source"], "manual")
        self.assertEqual(writes[0]["state"], "running")
        evidence.assert_not_called()

    def test_source_specific_caps_preserve_manual_reserve(self):
        regular = scheduled_sync.stage_command(
            scheduled_sync.STAGE_MAP["realty"], "scheduled"
        )
        manual = scheduled_sync.stage_command(
            scheduled_sync.STAGE_MAP["realty"], "manual", {"realty_stores_progress": 300}
        )
        self.assertEqual(regular[regular.index("--daily-cap") + 1], "800")
        self.assertEqual(manual[manual.index("--daily-cap") + 1], "500")

    def test_known_api_quotas_assign_exactly_eighty_percent_to_sync(self):
        for provider, policy in quota_policy.PROVIDER_QUOTAS.items():
            if policy["total"] is None:
                continue
            self.assertEqual(
                policy["regular"],
                int(policy["total"] * 0.8),
                provider,
            )

    def test_shared_api_bucket_serializes_only_related_stages(self):
        registry_lock = scheduled_sync._lock_id_for_stage("building_registry")
        permits_lock = scheduled_sync._lock_id_for_stage("building_permits")
        lodging_lock = scheduled_sync._lock_id_for_stage("lodging")
        self.assertEqual(registry_lock, permits_lock)
        self.assertNotEqual(registry_lock, lodging_lock)

    def test_stage_activity_locks_are_unique_inside_shared_execution_bucket(self):
        shared_bucket_stages = (
            "transactions",
            "building_registry",
            "building_permits",
            "building_geocode",
            "title_info",
            "realty",
        )
        execution_locks = {
            scheduled_sync._lock_id_for_stage(stage)
            for stage in shared_bucket_stages
        }
        activity_locks = {
            scheduled_sync._activity_lock_id_for_stage(stage)
            for stage in shared_bucket_stages
        }

        self.assertEqual(len(execution_locks), 1)
        self.assertEqual(len(activity_locks), len(shared_bucket_stages))

    def test_later_shared_bucket_lock_does_not_keep_stopped_stage_running(self):
        stage_keys = tuple(scheduled_sync.STAGE_MAP)
        stopped_stage = "transactions"
        later_stage = "building_registry"
        active_locks = {
            scheduled_sync._activity_lock_id_for_stage(later_stage),
        }

        self.assertFalse(stage_displayed_running(
            reports_running=True,
            active_locks=active_locks,
            stage_keys=stage_keys,
            stage_key=stopped_stage,
        ))
        self.assertTrue(stage_displayed_running(
            reports_running=True,
            active_locks=active_locks,
            stage_keys=stage_keys,
            stage_key=later_stage,
        ))

    def test_fresh_running_lodging_status_without_activity_lock_is_stale(self):
        self.assertEqual(
            reconcile_stage_state(
                state="running",
                age_seconds=1,
                stale_seconds=300,
                lock_active=False,
            ),
            "stale",
        )
        app_source = Path("app.py").read_text(encoding="utf-8")
        source_status_body = app_source.split(
            "def _lodging_source_stage_status(stage):", 1
        )[1].split(
            '@app.route("/api/admin/lodging-source-overview")', 1
        )[0]
        self.assertIn("reconcile_stage_state(", source_status_body)
        self.assertIn("_scheduled_sync_activity_lock_id(stage)", source_status_body)
        self.assertIn('"running": state == "running"', source_status_body)

    def test_rural_and_hanok_have_separate_half_quota_and_locks(self):
        rural = scheduled_sync.quotas_for_stage("rural")[0]
        hanok = scheduled_sync.quotas_for_stage("hanok")[0]
        self.assertEqual((rural["total"], rural["regular"]), (5000, 4000))
        self.assertEqual((hanok["total"], hanok["regular"]), (5000, 4000))
        self.assertNotEqual(
            scheduled_sync._lock_id_for_stage("rural"),
            scheduled_sync._lock_id_for_stage("hanok"),
        )
        rural_command = scheduled_sync.stage_command(
            scheduled_sync.STAGE_MAP["rural"], "scheduled"
        )
        self.assertEqual(
            rural_command[rural_command.index("--daily-cap") + 1],
            "4000",
        )
        self.assertIn("rural_hanok_sync_status:rural", rural_command)
        self.assertIn(
            "rural_hanok_sync_status:hanok",
            scheduled_sync.STAGE_MAP["hanok"].command,
        )

    def test_collection_targets_are_declared_for_fill_stages(self):
        self.assertIsNotNone(
            scheduled_sync.STAGE_MAP["building_geocode"].target_query
        )
        self.assertIsNotNone(
            scheduled_sync.STAGE_MAP["title_info"].target_query
        )

    def test_lodging_parallel_comparison_runs_after_legacy_collectors(self):
        keys = [stage.key for stage in scheduled_sync.STAGES]
        self.assertGreater(keys.index("lodging_compare"), keys.index("pension"))

    def test_manual_lodging_command_excludes_camping_without_reserve(self):
        command = scheduled_sync.stage_command(
            scheduled_sync.STAGE_MAP["lodging"], "manual",
            {"lodging_daily_calls": 8000},
        )
        self.assertNotIn("--include-camping", command)
        self.assertEqual(command[command.index("--max-calls") + 1], "10000")

    def test_lodging_and_broker_known_counter_policies_are_listed(self):
        lodging = scheduled_sync.quotas_for_stage("lodging")
        self.assertEqual(
            {(p["provider"], p["counter_key"]) for p in lodging},
            {("lodging", "lodging_daily_calls")},
        )
        camping = scheduled_sync.quotas_for_stage("camping")
        self.assertEqual(
            {(p["provider"], p["counter_key"]) for p in camping},
            {("camping", "camping_daily_calls")},
        )
        broker = scheduled_sync.quotas_for_stage("brokers")[0]
        self.assertEqual(broker["counter_key"], "broker_daily_calls")
        self.assertEqual(scheduled_sync.cap_for_source(broker, "manual"), 1000)

    def test_building_provider_includes_registry_and_permits_counters(self):
        from quota_policy import PROVIDER_COUNTER_KEYS
        self.assertEqual(
            set(PROVIDER_COUNTER_KEYS["building_hub"]),
            {"brhub_progress", "brhub_rescan_progress", "permits_progress"},
        )

    def test_building_hub_claim_is_atomic_and_hard_capped(self):
        class Cursor:
            def __init__(self):
                self.sql = ""
            def execute(self, sql, params):
                self.sql = sql
            def fetchone(self):
                return {"count": 8000}
            def close(self):
                pass
        class Conn:
            def __init__(self):
                self.cursor_obj = Cursor()
            def cursor(self):
                return self.cursor_obj
            def commit(self):
                pass
            def close(self):
                pass
        conn = Conn()
        with patch("db.get_conn", return_value=conn):
            self.assertEqual(quota_policy.claim_building_hub_request(), 8000)
        self.assertIn("ON CONFLICT", conn.cursor_obj.sql)
        self.assertIn("< %s", conn.cursor_obj.sql)

    def test_both_building_collectors_claim_before_outbound_request(self):
        with open("sync_brhub.py", encoding="utf-8") as f:
            brhub = f.read()
        with open("sync_permits.py", encoding="utf-8") as f:
            permits = f.read()
        self.assertIn("claim_building_hub_request()\n    r = requests.get", brhub)
        self.assertIn("claim_building_hub_request()\n    r = requests.get", permits)

    def test_manual_child_lock_failure_fences_its_claim(self):
        writes = []
        claim = {"run_id": "claimed", "state": "running", "stages": {}}
        with (
            patch.object(scheduled_sync, "_acquire_lock", return_value=(None, None)),
            patch.object(scheduled_sync, "_release_lock"),
            patch.object(scheduled_sync, "_read_status", return_value=claim),
            patch.object(scheduled_sync, "_write_status",
                         side_effect=lambda key, value, run_id: writes.append((value, run_id))),
        ):
            self.assertEqual(
                scheduled_sync.run(source="manual", run_id="claimed"), 2
            )
        self.assertEqual(writes[0][0]["state"], "failed")
        self.assertEqual(writes[0][1], "claimed")

    def test_sigterm_marks_running_stage_and_batch_cancelled(self):
        writes = []

        def cancel_during_stage(_stage, _source, on_progress=None, run_control=None):
            run_control.request_cancel()
            return -signal.SIGTERM, []

        with (
            patch.object(
                scheduled_sync,
                "_acquire_lock",
                return_value=(object(), object()),
            ),
            patch.object(scheduled_sync, "_release_lock"),
            patch.object(scheduled_sync, "_read_status", return_value=None),
            patch.object(scheduled_sync, "_read_legacy_lodging_sync_control",
                         return_value={"enabled": True}),
            patch.object(scheduled_sync, "_write_initial_status"),
            patch.object(
                scheduled_sync,
                "_write_status",
                side_effect=lambda key, value, run_id=None: writes.append({
                    **value,
                    "stages": {
                        stage_key: dict(stage_value)
                        for stage_key, stage_value in value["stages"].items()
                    },
                }),
            ),
            patch.object(scheduled_sync, "_source_busy", return_value=None),
            patch.object(scheduled_sync, "_metric_value", return_value=0),
            patch.object(scheduled_sync, "_run_stage", side_effect=cancel_during_stage),
            patch.object(scheduled_sync, "_write_scheduled_evidence") as evidence,
        ):
            result = scheduled_sync.run(selected_stage="transactions")

        self.assertEqual(result, 130)
        self.assertEqual(writes[-1]["state"], "cancelled")
        self.assertEqual(
            writes[-1]["stages"]["transactions"]["state"],
            "cancelled",
        )
        self.assertTrue(writes[-1]["retryable"])
        self.assertIsNotNone(writes[-1]["finished_at"])
        self.assertEqual(evidence.call_args_list[-1].args[1], "cancelled")

    def test_cancelled_stage_is_included_in_retry_plan(self):
        previous = {
            "state": "cancelled",
            "stages": {
                "transactions": {"state": "cancelled", "error": "SIGTERM"},
            },
        }

        stages = scheduled_sync.prepare_stage_statuses(
            previous,
            weekday=0,
            retry_failures_only=True,
        )

        self.assertEqual(stages["transactions"]["state"], "pending")
        app_source = Path("app.py").read_text(encoding="utf-8")
        self.assertIn(
            '("failed", "partial", "running", "stale", "cancelled")',
            app_source,
        )

    def test_admin_running_display_is_fenced_by_advisory_lock(self):
        app_source = Path("app.py").read_text(encoding="utf-8")
        self.assertIn(
            '"SELECT pg_try_advisory_lock(%s) AS acquired"',
            app_source,
        )
        self.assertIn("stage_reports_running", app_source)
        self.assertIn("stage_displayed_running(", app_source)
        self.assertIn(
            "_scheduled_sync_activity_lock_id(key) in active_locks",
            app_source,
        )
        self.assertIn("stage_stale = stage[\"state\"] == \"stale\"", app_source)
        self.assertIn('"lock_active": (', app_source)

    def test_scheduled_runner_does_not_steal_fresh_manual_claim(self):
        claim = {"run_id": "manual", "state": "running", "stages": {}}
        with (
            patch.object(scheduled_sync, "_acquire_lock", return_value=(object(), object())),
            patch.object(scheduled_sync, "_release_lock"),
            patch.object(scheduled_sync, "_read_status", return_value=claim),
            patch.object(scheduled_sync, "_write_initial_status") as initial,
        ):
            self.assertEqual(scheduled_sync.run(source="scheduled"), 2)
        initial.assert_not_called()

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
            patch.object(scheduled_sync, "_write_scheduled_evidence") as evidence,
        ):
            result = scheduled_sync.run(selected_stage="lodging_promotion")
        self.assertEqual(result, 1)
        self.assertEqual(writes[-1]["state"], "failed")
        self.assertEqual(writes[-1]["stages"]["lodging_promotion"]["state"], "failed")
        self.assertTrue(writes[-1]["stages"]["lodging_promotion"]["retryable"])
        self.assertEqual(evidence.call_args_list[0].args[1], "running")
        self.assertEqual(evidence.call_args_list[-1].args[1], "failed")

    def test_rural_hanok_trade_stage_success_is_done(self):
        writes = []
        with (
            patch.object(
                scheduled_sync, "_acquire_lock",
                return_value=(object(), object()),
            ),
            patch.object(scheduled_sync, "_release_lock"),
            patch.object(scheduled_sync, "_read_status", return_value=None),
            patch.object(scheduled_sync, "_write_initial_status"),
            patch.object(
                scheduled_sync,
                "_write_status",
                side_effect=lambda key, value, run_id=None: writes.append(
                    {
                        **value,
                        "stages": {
                            k: dict(v) for k, v in value["stages"].items()
                        },
                    }
                ),
            ),
            patch.object(scheduled_sync, "_source_busy", return_value=None),
            patch.object(scheduled_sync, "_metric_value", return_value=0),
            patch.object(scheduled_sync, "_run_stage", return_value=(0, [])),
            patch.object(scheduled_sync, "_write_scheduled_evidence"),
        ):
            result = scheduled_sync.run(selected_stage="rural_hanok_trades")

        self.assertEqual(result, 0)
        self.assertEqual(writes[-1]["state"], "done")
        self.assertEqual(
            writes[-1]["stages"]["rural_hanok_trades"]["state"],
            "done",
        )
        self.assertFalse(
            writes[-1]["stages"]["rural_hanok_trades"]["retryable"]
        )

    def test_rural_hanok_trade_stage_failure_is_retryable(self):
        writes = []
        with (
            patch.object(
                scheduled_sync, "_acquire_lock",
                return_value=(object(), object()),
            ),
            patch.object(scheduled_sync, "_release_lock"),
            patch.object(scheduled_sync, "_read_status", return_value=None),
            patch.object(scheduled_sync, "_write_initial_status"),
            patch.object(
                scheduled_sync,
                "_write_status",
                side_effect=lambda key, value, run_id=None: writes.append(
                    {
                        **value,
                        "stages": {
                            k: dict(v) for k, v in value["stages"].items()
                        },
                    }
                ),
            ),
            patch.object(scheduled_sync, "_source_busy", return_value=None),
            patch.object(scheduled_sync, "_metric_value", return_value=0),
            patch.object(
                scheduled_sync,
                "_run_stage",
                return_value=(1, ["NrgTrade API error 401"]),
            ),
            patch.object(scheduled_sync, "_write_scheduled_evidence"),
        ):
            result = scheduled_sync.run(selected_stage="rural_hanok_trades")

        self.assertEqual(result, 1)
        stage = writes[-1]["stages"]["rural_hanok_trades"]
        self.assertEqual(writes[-1]["state"], "failed")
        self.assertEqual(stage["state"], "failed")
        self.assertTrue(stage["retryable"])

    def test_admin_cutover_skips_legacy_stage_without_spawning_collector(self):
        writes = []
        disabled = {
            "enabled": False,
            "state": "disabled",
            "manifest_id": 42,
        }
        with (
            patch.object(scheduled_sync, "_acquire_lock", return_value=(object(), object())),
            patch.object(scheduled_sync, "_release_lock"),
            patch.object(scheduled_sync, "_read_status", return_value=None),
            patch.object(scheduled_sync, "_read_legacy_lodging_sync_control", return_value=disabled),
            patch.object(scheduled_sync, "_write_initial_status"),
            patch.object(
                scheduled_sync,
                "_write_status",
                side_effect=lambda key, value, run_id=None: writes.append(value),
            ),
            patch.object(scheduled_sync, "_run_stage") as run_stage,
            patch.object(scheduled_sync, "_write_scheduled_evidence"),
        ):
            result = scheduled_sync.run(
                selected_stage="lodging", source="manual", orchestrated=True
            )
        self.assertEqual(result, 0)
        run_stage.assert_not_called()
        self.assertEqual(writes[-1]["state"], "done")
        self.assertEqual(writes[-1]["stages"]["lodging"]["state"], "skipped")
        self.assertIn("manifest #42", writes[-1]["stages"]["lodging"]["error"])

    def test_cutover_admin_controls_are_exposed(self):
        html = Path("static/admin.html").read_text(encoding="utf-8")
        app_source = Path("app.py").read_text(encoding="utf-8")
        self.assertIn("changeLegacyLodgingSync", html)
        self.assertIn("연속 무회귀", html)
        self.assertIn("종료·복구 감사 기록", html)
        self.assertIn(
            'promotion/<int:manifest_id>/legacy-sync',
            app_source,
        )

    def test_secret_values_are_redacted(self):
        with patch.dict(os.environ, {"LODGING_SERVICE_KEY": "top-secret"}):
            self.assertEqual(
                scheduled_sync._redact("failed top-secret"),
                "failed ***",
            )


if __name__ == "__main__":
    unittest.main()