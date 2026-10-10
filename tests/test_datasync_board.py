"""Offline evidence, auth, read-only, and legacy-preservation checks."""

import ast
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import Mock, patch

from datasync_board import ITEMS, build_board, read_board

NOW = datetime(2026, 10, 6, 3, 0, tzinfo=timezone.utc)


def record(value, updated=NOW):
    return {"value": json.dumps(value), "updated_at": updated}


def row(meta, anchor="dsSecTx", **kwargs):
    return next(r for r in build_board(meta, now=NOW, enabled={}, **kwargs)["rows"]
                if r["anchor"] == anchor)


class BoardTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch("datasync_board.relay_status", return_value={}))

    def test_all_real_cards_and_no_unknown_fabrication(self):
        html = Path("static/admin.html").read_text()
        import re
        anchors = set(re.findall(r'id="(dsSec\w+)"', html))
        self.assertEqual({item.anchor for item in ITEMS} - {"dsSecRuralHanokTrades"}, anchors)
        self.assertEqual(len(ITEMS), 24)
        result = build_board({}, now=NOW, enabled={})
        self.assertTrue(all(r["state"] == "확인불가" and r["reason"] for r in result["rows"]))
        self.assertTrue(all(r["today_calls"] is None and r["last_success_at"] is None
                            for r in result["rows"]))

    def test_states_and_no_insert_count_success_inference(self):
        for raw, expected in (("running", "실행 중"), ("pending", "대기"),
                              ("idle", "대기"), ("failed", "실패")):
            with self.subTest(raw=raw):
                self.assertEqual(row({"tx_sync_status": record({"state": raw})})["state"], expected)
        data = {"state": "done", "finished_at": NOW.isoformat(), "inserted": 0}
        result = row({"tx_sync_status": record(data)})
        self.assertEqual(result["state"], "완료")
        self.assertIsNotNone(result["last_success_at"])
        self.assertIsNone(row({"tx_sync_status": record({"state": "failed"})})["last_success_at"])

    def test_staleness_exact_two_periods_not_heartbeat(self):
        for delta, expected in ((timedelta(days=2) - timedelta(seconds=1), "완료"),
                                (timedelta(days=2), "오래됨")):
            with self.subTest(delta=delta):
                value = {"state": "done", "finished_at": (NOW - delta).isoformat()}
                self.assertEqual(row({"tx_sync_status": record(value)})["state"], expected)
        stale = record({"state": "running"}, NOW - timedelta(minutes=6))
        result = row({"tx_sync_status": stale})
        self.assertEqual(result["state"], "확인불가")
        self.assertIn("하트비트", result["reason"])
        # A one-off manual backfill has no invented periodic age.
        value = {"state": "done", "finished_at": (NOW - timedelta(days=90)).isoformat()}
        self.assertEqual(row({"tx_backfill_status": record(value)}, "dsSecTxBackfill")["state"], "완료")

    def test_quota_stops_are_not_full_completions(self):
        for data in (
            {"state": "done", "stop_reason": "daily_cap", "finished_at": NOW.isoformat()},
            {"state": "failed", "error": "QuotaExhausted daily cap 429"},
            {"state": "done", "capped": True},
            {"state": "paused", "stop_reason": "consecutive_errors"},
        ):
            with self.subTest(data=data):
                result = row({"tx_sync_status": record(data)})
                self.assertEqual(result["state"], "일시중단")
                self.assertIsNone(result["last_success_at"])
        result = row({"zip_code_backfill_status": record({"state": "partial", "done": False})}, "dsSecZip")
        self.assertEqual(result["state"], "일시중단")
        # Last in-flight request reaching the cap is not proof that a job stopped.
        result = row({"tx_sync_status": record({"state": "running"}),
                      "rtms_provider_daily_calls": record({"date": "2026-10-06", "count": 10000})})
        self.assertEqual(result["state"], "실행 중")

    def test_scheduled_history_while_current_attempt_fails(self):
        previous = (NOW - timedelta(days=1)).isoformat()
        meta = {"scheduled_sync_status:transactions": record({
            "stages": {"transactions": {"state": "failed", "finished_at": NOW.isoformat(),
                                        "last_success_at": previous, "error": "timeout"}}})}
        result = row(meta)
        self.assertEqual(result["state"], "실패")
        self.assertEqual(datetime.fromisoformat(result["last_success_at"]).astimezone(timezone.utc),
                         datetime.fromisoformat(previous))
        self.assertEqual(result["last_error_summary"], "외부 API 응답 시간 초과")

    def test_skip_not_selected_never_masks_real_failure(self):
        meta = {"tx_sync_status": record({"state": "failed", "error": "403",
                                         "finished_at": (NOW - timedelta(hours=1)).isoformat()}),
                "scheduled_sync_status:transactions": record({
                    "stages": {"transactions": {"state": "skipped", "finished_at": NOW.isoformat(),
                                                "last_success_at": (NOW - timedelta(days=3)).isoformat()}}})}
        result = row(meta)
        self.assertEqual(result["state"], "실패")
        self.assertIsNotNone(result["last_success_at"])
        # With no actual attempt record, skipping is waiting, not completion.
        del meta["tx_sync_status"]
        self.assertEqual(row(meta)["state"], "오래됨")

    def test_nested_stage_child_and_live_heartbeat(self):
        meta = {"scheduled_sync_status:transactions:transactions": record({
            "stages": {"transactions": {"state": "running", "started_at": NOW.isoformat()}}})}
        self.assertEqual(row(meta)["state"], "실행 중")

    def test_daily_counters_absent_old_and_shared(self):
        meta = {"rtms_provider_daily_calls": record({"date": "2026-10-06", "count": 7})}
        self.assertEqual(row(meta)["today_calls"], 7)
        self.assertEqual(row(meta, "dsSecTxBackfill")["today_calls"], 7)
        self.assertEqual(row(meta)["daily_limit"], 10000)
        for day, count in (("2026-10-05", 0), ("2026-10-07", None)):
            meta = {"rtms_provider_daily_calls": record({"date": day, "count": 999})}
            self.assertEqual(row(meta)["today_calls"], count)
        for value in ({}, {"date": "bad", "count": 7}, {"date": "2026-10-06", "count": -1}):
            self.assertIsNone(row({"rtms_provider_daily_calls": record(value)})["today_calls"])
        self.assertIsNone(row({})["today_calls"])
        meta = {"store_api_batch_requests": record({"date": "2026-10-06", "realty": 12, "stores": 3})}
        self.assertEqual(row(meta, "dsSecRealty")["today_calls"], 12)
        self.assertEqual(row(meta, "dsSecStores")["today_calls"], 3)

    def test_relay_boolean_only_and_mixed_routes(self):
        for enabled, expected in (({}, "직접"), ({"rtms": True}, "중계")):
            result = next(r for r in build_board({}, now=NOW, enabled=enabled)["rows"]
                          if r["anchor"] == "dsSecTx")
            self.assertEqual(result["route"], expected)
            self.assertIn("건축HUB", result["route_note"])
        result = next(r for r in build_board({}, now=NOW,
                       enabled={"rtms": True, "bldg_hub": True})["rows"] if r["anchor"] == "dsSecOnbid")
        self.assertEqual(result["route"], "직접")
        self.assertIsNone(row({}, "dsSecBackup")["route"])

    def test_no_secret_error_echo_or_guessed_retry_count(self):
        secret = "VERY_PRIVATE_TEST_CREDENTIAL_7788"
        meta = {"tx_sync_status": record({"state": "failed", "error": (
            f"timeout https://api.example/?serviceKey={secret} token={secret}"),
            "finished_at": NOW.isoformat()})}
        result = build_board(meta, now=NOW, enabled={})
        output = json.dumps(result)
        self.assertNotIn(secret, output)
        self.assertNotIn("https://api.example", output)
        self.assertNotIn("3회", output)

    def test_next_schedule_not_invented_timezone(self):
        self.assertIn("확인불가", row({})["next_run"])
        self.assertIn("시간대", row({})["next_run"])
        self.assertIn("수동", row({}, "dsSecTxBackfill")["next_run"])
        self.assertIn("30분", row({}, "dsSecZip")["next_run"])
        self.assertIn("KST", row({}, "dsSecOnbid")["next_run"])

    def test_unavailable_and_invalid_json(self):
        result = build_board({}, now=NOW, enabled={}, unavailable=True)
        self.assertTrue(all(r["state"] == "확인불가" and not r["action"] for r in result["rows"]))
        self.assertEqual(row({"tx_sync_status": {"value": "BAD", "updated_at": NOW}})["state"], "확인불가")

    def test_read_only_select_no_commit_or_external_calls(self):
        conn = Mock()
        cur = conn.cursor.return_value
        cur.fetchall.return_value = []
        with patch("requests.get", side_effect=AssertionError("external request")):
            result = read_board(lambda: conn)
        self.assertTrue(result["ok"])
        queries = [str(call.args[0]) for call in cur.execute.call_args_list]
        self.assertEqual(len(queries), 3)
        self.assertTrue(queries[0].startswith("SET TRANSACTION READ ONLY"))
        self.assertTrue(queries[1].startswith("SET LOCAL statement_timeout"))
        self.assertTrue(queries[2].startswith("SELECT"))
        conn.commit.assert_not_called()
        conn.rollback.assert_called_once()
        conn.close.assert_called_once()
        cur.close.assert_called_once()

    def test_db_failure_no_exception_leak(self):
        def fail():
            raise RuntimeError("password=VERY_PRIVATE_TEST")
        result = read_board(fail)
        self.assertNotIn("VERY_PRIVATE_TEST", json.dumps(result))
        self.assertTrue(all(r["state"] == "확인불가" for r in result["rows"]))

    def test_board_endpoint_and_existing_collection_runners_unchanged(self):
        from datasync_controls import RUN_HANDLERS
        source = Path("app.py").read_text()
        previous = subprocess.check_output(["git", "show", "HEAD:app.py"], text=True)
        old = {n.name: ast.dump(n) for n in ast.parse(previous).body if isinstance(n, ast.FunctionDef)}
        new = {n.name: ast.dump(n) for n in ast.parse(source).body if isinstance(n, ast.FunctionDef)}
        # 다른 기능의 앱 변경이 아닌, 이 보드가 호출하는 기존 수집기를 보호한다.
        protected = set(RUN_HANDLERS.values()) | {
            name for name in old if name.startswith("admin_scheduled_sync")
        }
        for name in protected & old.keys():
            expected = old[name]
            if name == "admin_title_info_run":
                # Explicitly approved detailed backfill: only runner/arguments
                # change; authentication, limits and the action route stay frozen.
                expected = expected.replace("Constant(value='backfill_title_info.py')", "Constant(value='backfill_building_details.py')")
                before = ast.dump(ast.parse('["--status-key", _TITLE_INFO_META_KEY, "--sleep", "0.05"]', mode="eval").body)
                after = ast.dump(ast.parse('["--status-key", _TITLE_INFO_META_KEY, "--adopt", "--continuous", "--batch-limit", "1000", "--sleep", "1.0"]', mode="eval").body)
                expected = expected.replace(before, after)
            self.assertEqual(new.get(name), expected, name)
        node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef)
                    and n.name == "admin_datasync_board")
        self.assertIn("require_admin", [ast.unparse(d) for d in node.decorator_list])
        self.assertIn('"/api/admin/datasync-board"', ast.get_source_segment(source, node.decorator_list[0]))
        self.assertIn('"no-store"', ast.get_source_segment(source, node))

    def test_postal_terminal_heartbeat_not_arbitrary_success(self):
        terminal = {"state": "done", "done": True, "heartbeat": NOW.isoformat()}
        result = row({"zip_code_backfill_status": record(terminal)}, "dsSecZip")
        self.assertEqual(result["state"], "완료")
        self.assertIsNotNone(result["last_success_at"])
        self.assertIsNone(row({"tx_sync_status": record({
            "state": "running", "heartbeat": NOW.isoformat()})})["last_success_at"])

    def test_http_auth_and_response_using_real_route_and_guard(self):
        from flask import Flask, jsonify, redirect, request, session
        from functools import wraps
        source = Path("app.py").read_text()
        names = {"admin_datasync_board", "require_admin"}
        nodes = [n for n in ast.parse(source).body
                 if isinstance(n, ast.FunctionDef) and n.name in names]
        # Isolated HTTP test app, not a bypass of the user's running app.
        isolated = Flask("board_contract")
        isolated.secret_key = "offline-test-only"
        scope = {"app": isolated, "jsonify": jsonify, "redirect": redirect,
                 "request": request, "session": session, "wraps": wraps,
                 "_is_internal_stats_refresh_request": lambda: False,
                 "get_conn": Mock(side_effect=AssertionError("Unexpected DB call"))}
        guard = next(n for n in nodes if n.name == "require_admin")
        route = next(n for n in nodes if n.name == "admin_datasync_board")
        exec(compile(ast.Module(body=[guard, route], type_ignores=[]), "board_contract", "exec"), scope)
        client = isolated.test_client()
        with patch("datasync_board.read_board", return_value=build_board({}, now=NOW, enabled={})) as read:
            self.assertEqual(client.get("/api/admin/datasync-board").status_code, 401)
            read.assert_not_called()
            with client.session_transaction() as test_session:
                test_session["admin"] = True
            response = client.get("/api/admin/datasync-board")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["Cache-Control"], "no-store")
            self.assertEqual(len(response.get_json()["rows"]), 24)
            read.assert_called_once()


if __name__ == "__main__":
    unittest.main()
