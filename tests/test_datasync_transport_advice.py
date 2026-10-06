"""Offline phase-three contracts: local telemetry mocked, all network forbidden."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import Mock, patch

from datasync_board import ITEMS, build_board, read_board

NOW = datetime(2026, 10, 6, 4, tzinfo=timezone.utc)


def record(data, at=NOW):
    return {"value": json.dumps(data), "updated_at": at}


class AdviceTests(unittest.TestCase):
    def setUp(self):
        self.http = self.enterContext(patch(
            "requests.sessions.Session.request", side_effect=AssertionError("no probes")))
        self.local = self.enterContext(patch("datasync_board.relay_status", return_value={}))

    def board(self, meta=None, enabled=None, snapshot=None):
        return build_board(meta or {}, now=NOW, enabled=enabled or {},
                           relay_snapshot=snapshot)

    def advice(self, error=None, key="dsSecTx", state="failed", **kwargs):
        item = next(i for i in ITEMS if i.anchor == key)
        meta = kwargs.pop("meta", None)
        if meta is None:
            meta = {item.keys[0]: record({
                "state": state, "error": error, "finished_at": NOW.isoformat()})}
        return next(r["transport_advice"] for r in self.board(meta, **kwargs)["rows"]
                    if r["key"] == key)

    def test_timeout_and_connection_supported_review_and_manual_steps(self):
        for error in ("ReadTimeout: timed out", "ConnectionError: DB connection lost"):
            advice = self.advice(error)
            self.assertEqual(advice["verdict"], "중계 전환 검토")
            self.assertEqual(advice["switch_name"], "RELAY_USE_RTMS")
            self.assertEqual(advice["consecutive_note"], "연속 횟수 미확인")
            self.assertEqual(len(advice["steps"]), 5)
            steps = " ".join(advice["steps"])
            for text in ("RELAY_ENABLED", "Scheduled deployment", "별도로 재게시",
                         "DB 오류", "자동으로 직접 호출로 되돌아가는 기능은 없습니다"):
                self.assertIn(text, steps)
        hub = self.advice("timeout", key="dsSecTitle")
        self.assertEqual(hub["switch_name"], "RELAY_USE_BLDG_HUB")
        self.http.assert_not_called()

    def test_quota_keeps_direct_and_warns_relay_does_not_fix_shared_limit(self):
        advice = self.advice("HTTP 429 quota exhausted")
        self.assertEqual(advice["verdict"], "직접 유지")
        for text in ("중계로 해결되지 않습니다", "서비스 전체가 공유", "내일 초기화"):
            self.assertIn(text, advice["reason"])
        for state in ("waiting_quota", "paused"):
            meta = {"tx_sync_status": record({"state": state, "stop_reason": "daily_cap"})}
            self.assertIn("중계로 해결되지", self.advice(meta=meta)["reason"])
        self.assertEqual(advice["steps"], [])

    def test_auth_keeps_direct_and_requests_key_approval_review(self):
        for error in ("HTTP 403 Forbidden", "401 authentication failure"):
            advice = self.advice(error)
            self.assertEqual(advice["verdict"], "직접 유지")
            self.assertIn("키 또는 승인 상태 확인", advice["reason"])
            self.assertIn("해결되지 않을 수", advice["reason"])

    def test_unsupported_including_permits_never_invents_switches(self):
        for key in ("dsSecPermits", "dsSecStores",
                    "dsSecPhotos", "dsSecGeo", "dsSecBroker", "dsSecCampingImages"):
            advice = self.advice("timeout", key=key)
            self.assertEqual(advice["verdict"], "중계 미지원", key)
            self.assertIn("중계 서버와 클라이언트", advice["reason"])
            self.assertIsNone(advice["switch_name"])
            self.assertEqual(advice["steps"], [])
        self.assertIn("중계로 해결되지", self.advice("429", key="dsSecOnbid")["reason"])

    def test_onbid_supported_off_review_and_on_local_observation(self):
        advice = self.advice("ConnectTimeout", key="dsSecOnbid")
        self.assertEqual(advice["verdict"], "중계 전환 검토")
        self.assertEqual(advice["switch_name"], "RELAY_USE_ONBID")
        self.assertIn("RELAY_USE_ONBID", " ".join(advice["steps"]))
        quota = self.advice("429", key="dsSecOnbid")
        self.assertEqual(quota["verdict"], "직접 유지")
        self.assertEqual(quota["steps"], [])
        on = self.advice(key="dsSecOnbid", enabled={"onbid": True}, snapshot={
            "onbid": {"enabled": True, "last_success_at": NOW.isoformat(),
                      "last_error_code": None},
        })
        self.assertEqual(on["verdict"], "중계 사용 중")
        row = next(r for r in self.board(enabled={"onbid": True})["rows"]
                   if r["key"] == "dsSecOnbid")
        self.assertEqual(row["route"], "중계")

    def test_current_relay_error_newer_than_success_is_red(self):
        status = {"rtms": {
            "enabled": True, "last_success_at": (NOW-timedelta(hours=1)).isoformat(),
            "last_error_code": "UPSTREAM_TIMEOUT", "last_error_at": NOW.isoformat()}}
        advice = self.advice(enabled={"rtms": True}, snapshot=status)
        self.assertEqual(advice["verdict"], "중계 사용 중 - 오류 있음")
        self.assertIn("UPSTREAM_TIMEOUT", advice["reason"])
        for code, text in (("RELAY_QUOTA", "중계로 해결되지"),
                           ("RELAY_FORBIDDEN", "키 또는 승인")):
            status["rtms"]["last_error_code"] = code
            self.assertIn(text, self.advice(enabled={"rtms": True}, snapshot=status)["reason"])

    def test_relay_healthy_and_older_error_not_red(self):
        status = {"rtms": {"enabled": True, "last_success_at": NOW.isoformat()}}
        self.assertEqual(self.advice(enabled={"rtms": True}, snapshot=status)["verdict"], "중계 사용 중")
        status["rtms"].update(last_error_code="UPSTREAM_CONNECT",
                             last_error_at=(NOW-timedelta(hours=2)).isoformat())
        self.assertEqual(self.advice(enabled={"rtms": True}, snapshot=status)["verdict"], "중계 사용 중")

    def test_actual_legacy_telemetry_has_no_error_time_never_infer_order(self):
        status = {"rtms": {"enabled": True, "last_success_at": NOW.isoformat(),
                           "last_error_code": "RELAY_FORBIDDEN"}}
        advice = self.advice(enabled={"rtms": True}, snapshot=status)
        self.assertEqual(advice["verdict"], "판단불가")
        self.assertIn("시각 미기록", advice["reason"])

    def test_missing_malformed_future_records_and_relay_no_history_unknown(self):
        for meta in ({}, {"tx_sync_status": record({})},
                     {"tx_sync_status": {"value": "{bad-json", "updated_at": NOW}},
                     {"tx_sync_status": record({"state": "failed", "error": "timeout"},
                                              NOW+timedelta(days=1))}):
            advice = self.advice(meta=meta)
            self.assertEqual(advice["verdict"], "판단불가")
        self.assertEqual(self.advice(enabled={"rtms": True})["verdict"], "판단불가")
        self.assertEqual(self.advice(meta={}, key="dsSecOnbid")["verdict"], "판단불가")
        result = self.board()
        self.assertEqual(len(result["rows"]), 24)
        self.assertTrue(all(r["transport_advice"]["verdict"] == "판단불가" for r in result["rows"]))

    def test_missing_telemetry_never_means_switch_off(self):
        result = self.board(enabled={"rtms": True}, snapshot={})
        self.assertTrue(result["relay_observation"]["services"]["rtms"]["enabled"])
        advice = next(r["transport_advice"] for r in result["rows"] if r["key"] == "dsSecTx")
        self.assertEqual(advice["verdict"], "판단불가")

    def test_nonconnection_failure_success_and_retained_old_error_keep_direct(self):
        self.assertEqual(self.advice("parse failure")["verdict"], "직접 유지")
        meta = {"tx_sync_status": record({
            "state": "done", "last_error": "timeout", "finished_at": NOW.isoformat()})}
        self.assertEqual(self.advice(meta=meta)["verdict"], "직접 유지")
        meta["tx_sync_status"]["value"] = json.dumps({"state": "done", "finished_at": NOW.isoformat()})
        meta["scheduled_sync_status:transactions"] = record({"stages": {
            "transactions": {"state": "failed", "error": "timeout",
                             "finished_at": (NOW-timedelta(days=2)).isoformat()}}})
        self.assertEqual(self.advice(meta=meta)["verdict"], "직접 유지")

    def test_cadence_skip_does_not_hide_last_executed_failure(self):
        meta = {"tx_sync_status": record({"state": "failed", "error": "timeout"},
                                        NOW-timedelta(hours=1)),
                "scheduled_sync_status:transactions": record({"stages": {
                    "transactions": {"state": "skipped", "error": "cadence"}}})}
        self.assertEqual(self.advice(meta=meta)["verdict"], "중계 전환 검토")

    def test_snapshot_and_all_response_text_strictly_exclude_private_values(self):
        private = "FAKE_PRIVATE_TEST_TOKEN"
        address = "https://fake-private-relay.invalid/api"
        status = {"rtms": {"enabled": False, "token": private, "base_url": address,
                           "serviceKey": private, "last_error_code": private,
                           "last_success_at": address, "last_error_at": private},
                  "unsupported": {"address": address}}
        result = self.board({"tx_sync_status": record({
            "state": "failed", "error": f"timeout {address}?serviceKey={private}",
            "token": private})}, snapshot=status)
        text = json.dumps(result, ensure_ascii=False)
        for forbidden in (private, address, "serviceKey", "https://", "base_url"):
            self.assertNotIn(forbidden, text)
        self.assertEqual(set(result["relay_observation"]["services"]), {"rtms", "bldg_hub", "onbid", "juso"})

    def test_read_board_mocks_local_snapshot_once_readonly_select_and_single_row(self):
        conn = Mock()
        cur = conn.cursor.return_value
        cur.fetchall.return_value = []
        self.local.return_value = {"rtms": {"enabled": False}}
        result = read_board(lambda: conn, key="dsSecTx")
        self.assertEqual([r["key"] for r in result["rows"]], ["dsSecTx"])
        self.assertIn("transport_advice", result["rows"][0])
        self.assertIn("relay_observation", result)
        self.local.assert_called_once_with()
        self.assertEqual(cur.execute.call_count, 3)
        conn.commit.assert_not_called()
        self.http.assert_not_called()

    def test_store_failure_and_local_reader_failure_are_unknown_safe(self):
        private = "FAKE_SECRET_EXCEPTION"
        self.local.side_effect = RuntimeError(private)
        result = read_board(Mock(side_effect=RuntimeError(private)))
        self.assertTrue(all(r["transport_advice"]["verdict"] == "판단불가" for r in result["rows"]))
        self.assertNotIn(private, json.dumps(result))
        self.http.assert_not_called()

    def test_existing_actions_routes_schedules_and_schema_untouched(self):
        changed = set(subprocess.check_output(
            ["git", "diff", "--name-only", "HEAD"], text=True).splitlines())
        self.assertFalse(changed & {
            "app.py", "datasync_controls.py", "scheduled_sync.py",
            "db.py", ".replit", "gunicorn.conf.py"})
        self.assertNotIn("os.environ[", Path("datasync_transport_advice.py").read_text())


if __name__ == "__main__":
    unittest.main()
