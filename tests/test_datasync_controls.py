"""Offline control contract; every existing runner is mocked, no provider calls."""

import ast
from datetime import datetime, timezone, timedelta
import json
import io
import logging
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
from functools import wraps

from flask import Flask, jsonify, redirect, request, session
from datasync_board import ITEMS, build_board, read_board
from datasync_controls import RUN_HANDLERS, ActionRejected, action_guard, audit, validate_action


def stored(key, value, at=None):
    return {"key": key, "value": json.dumps(value),
            "updated_at": at or datetime.now(timezone.utc)}


class ControlsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path("app.py").read_text()
        tree = ast.parse(source)
        cls.functions = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
        cls.functions.update({n.name: n for n in ast.walk(ast.parse(Path("auction_service.py").read_text()))
                              if isinstance(n, ast.FunctionDef)})
        app = Flask("offline_board_controls")
        app.secret_key = "offline-controls-test-only"
        scope = dict(app=app, jsonify=jsonify, redirect=redirect, request=request,
                     session=session, wraps=wraps,
                     _is_internal_stats_refresh_request=lambda: False,
                     _scheduled_sync_activity_lock_id=lambda stage: 12345001)
        nodes = [cls.functions[name] for name in (
            "require_admin", "admin_datasync_board", "admin_datasync_board_action")]
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "offline_board_controls", "exec"), scope)
        cls.app, cls.scope = app, scope

    def setUp(self):
        self.enterContext(patch("datasync_board.relay_status", return_value={}))
        self.client = self.app.test_client()
        with self.client.session_transaction() as state:
            state["admin"] = True
            state["admin_user_id"] = 123
        self.conn = Mock()
        self.cur = self.conn.cursor.return_value
        self.cur.fetchone.return_value = {"acquired": True}
        self.cur.fetchall.return_value = []
        self.get_conn = Mock(return_value=self.conn)
        self.scope["get_conn"] = self.get_conn
        self.handlers = {}
        for key, name in RUN_HANDLERS.items():
            handler = Mock(side_effect=lambda: (jsonify({"ok": True}), 202))
            self.app.view_functions[name] = handler
            self.handlers[key] = handler
        self.no_network = patch("requests.get", side_effect=AssertionError("provider call"))
        self.no_network.start()
        self.addCleanup(self.no_network.stop)

    def post(self, key="dsSecTx", action="run", **kwargs):
        return self.client.post("/api/admin/datasync-board/action",
                                json={"key": key, "action": action}, **kwargs)

    def idle(self, key="dsSecTx", state="idle"):
        item = next(item for item in ITEMS if item.anchor == key)
        self.cur.fetchall.return_value = [stored(item.keys[0], {"state": state})]

    def test_all_allowlisted_handlers_exist_and_are_exact_existing_post_routes(self):
        self.assertEqual(len(RUN_HANDLERS), 14)
        for key, name in RUN_HANDLERS.items():
            self.assertIn(name, self.functions)
            decorators = " ".join(ast.unparse(d) for d in self.functions[name].decorator_list)
            self.assertTrue("methods=['POST']" in decorators or "app.post(" in decorators)
            self.assertIn("require_admin", decorators)
            self.assertIn("limiter.limit", decorators)
            self.idle(key)
            response = self.post(key)
            self.assertEqual(response.status_code, 202, (key, response.get_json()))
            self.handlers[key].assert_called_once_with()
        self.conn.commit.assert_not_called()

    def test_unauthenticated_and_nonadmin_and_unidentified_session(self):
        client = self.app.test_client()
        self.assertEqual(client.post("/api/admin/datasync-board/action", json={}).status_code, 401)
        with client.session_transaction() as state:
            state["user_id"] = 777
        self.assertEqual(client.post("/api/admin/datasync-board/action", json={}).status_code, 401)
        with client.session_transaction() as state:
            state["admin"] = True
        self.assertEqual(client.post("/api/admin/datasync-board/action", json={}).status_code, 401)
        self.get_conn.assert_not_called()

    def test_arbitrary_paths_functions_keys_and_payloads_rejected(self):
        for body in (None, [], {}, {"key": "app:run", "action": "run"},
                     {"key": "dsSecTx", "action": "run", "path": "/api/admin/sync-lodgings"},
                     {"key": "dsSecTx", "action": "run", "months": 120},
                     {"key": "dsSecTx", "action": "shell"},
                     {"key": ["dsSecTx"], "action": "run"}):
            response = self.client.post("/api/admin/datasync-board/action", json=body)
            self.assertEqual(response.status_code, 400, body)
        self.get_conn.assert_not_called()
        for handler in self.handlers.values():
            handler.assert_not_called()

    def test_only_supported_stops_allowed_none_exist_and_all_are_rejected(self):
        for item in ITEMS:
            self.assertFalse(build_board({}, enabled={})["rows"][0]["controls"]["stop"])
            self.assertEqual(self.post(item.anchor, "stop").status_code, 400)
        self.get_conn.assert_not_called()

    def test_existing_running_and_stale_running_claims_both_409(self):
        for at in (datetime.now(timezone.utc), datetime.now(timezone.utc)-timedelta(days=3)):
            self.cur.fetchall.return_value = [stored("tx_sync_status", {"state": "running"}, at)]
            response = self.post()
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.get_json()["message"], "이미 실행 중입니다")
        self.handlers["dsSecTx"].assert_not_called()

    def test_running_stage_and_busy_db_lock_409(self):
        self.cur.fetchall.return_value = [stored("scheduled_sync_status:transactions", {
            "stages": {"transactions": {"state": "running"}}})]
        self.assertEqual(self.post().status_code, 409)
        self.cur.fetchone.return_value = {"acquired": False}
        self.assertEqual(self.post().status_code, 409)
        self.handlers["dsSecTx"].assert_not_called()
        self.conn.rollback.assert_called()
        self.conn.close.assert_called()

    def test_unknown_and_fresh_completion_cannot_be_reexecuted(self):
        self.assertEqual(self.post().status_code, 409)
        self.cur.fetchall.return_value = [stored("tx_sync_status", {
            "state": "done", "finished_at": datetime.now(timezone.utc).isoformat()})]
        self.assertEqual(self.post().status_code, 409)
        self.handlers["dsSecTx"].assert_not_called()

    def test_shared_provider_is_warning_not_a_block(self):
        self.cur.fetchall.return_value = [
            stored("tx_sync_status", {"state": "failed"}),
            stored("tx_backfill_status", {"state": "running"}),
        ]
        self.assertEqual(self.post().status_code, 202)
        rows = build_board({r["key"]: r for r in self.cur.fetchall.return_value}, enabled={})["rows"]
        current = next(r for r in rows if r["key"] == "dsSecTx")
        self.assertEqual(current["shared_running"], ["과거 실거래"])
        self.handlers["dsSecTx"].assert_called_once()

    def test_composite_peer_running_job_not_hidden_by_newer_failed_job(self):
        now = datetime.now(timezone.utc)
        meta = {
            "brhub_sync_status": stored("brhub_sync_status", {"state": "running"},
                                        now-timedelta(seconds=2)),
            "brhub_rescan_status": stored("brhub_rescan_status", {"state": "failed"}, now),
            "title_info_sync_status": stored("title_info_sync_status", {"state": "idle"}, now),
        }
        rows = build_board(meta, now=now, enabled={})["rows"]
        title = next(r for r in rows if r["key"] == "dsSecTitle")
        self.assertEqual(title["shared_running"], ["건축물대장"])

    def test_response_errors_and_audit_never_echo_secrets(self):
        private = "FAKE_PRIVATE_VALUE_FOR_ISOLATED_TEST"
        self.idle()
        self.handlers["dsSecTx"].side_effect = lambda: (jsonify({"ok": False, "message": private}), 500)
        response = self.post()
        self.assertNotIn(private, response.get_data(as_text=True))
        self.handlers["dsSecTx"].side_effect = RuntimeError(private)
        self.assertEqual(self.post().status_code, 503)
        logger = Mock()
        audit(logger, 123, private, private, 400)
        self.assertNotIn(private, repr(logger.warning.call_args))
        self.assertIn("123", repr(logger.warning.call_args))
        self.assertIn("at=", logger.warning.call_args.args[0])

    def test_audit_survives_existing_warning_log_threshold(self):
        logger = logging.Logger("isolated_offline_audit", level=logging.WARNING)
        output = io.StringIO()
        logger.addHandler(logging.StreamHandler(output))
        audit(logger, 123, "dsSecTx", "run", 202)
        line = output.getvalue()
        self.assertEqual(len(line.splitlines()), 1)
        self.assertIn("admin_id=123", line)
        self.assertIn("item=dsSecTx action=run http=202", line)

    def test_existing_409_normalized_and_cooldown_preserved(self):
        self.idle()
        for code in (409, 429):
            self.handlers["dsSecTx"].side_effect = lambda code=code: (jsonify({"ok": False}), code)
            response = self.post()
            self.assertEqual(response.status_code, code)
            if code == 409:
                self.assertEqual(response.get_json()["message"], "이미 실행 중입니다")

    def test_database_failure_fails_closed(self):
        self.get_conn.side_effect = RuntimeError("private DB connection")
        response = self.post()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private DB", response.get_data(as_text=True))
        self.handlers["dsSecTx"].assert_not_called()

    def test_origin_guard(self):
        self.assertEqual(self.post(headers={"Origin": "https://foreign.example"}).status_code, 403)
        self.assertEqual(self.post(headers={"Sec-Fetch-Site": "cross-site"}).status_code, 403)
        self.get_conn.assert_not_called()

    def test_single_row_get_auth_allowlist_and_read_only(self):
        client = self.app.test_client()
        self.assertEqual(client.get("/api/admin/datasync-board?key=dsSecTx").status_code, 401)
        self.assertEqual(self.client.get("/api/admin/datasync-board?key=unknown").status_code, 400)
        response = self.client.get("/api/admin/datasync-board?key=dsSecTx")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual([r["key"] for r in response.get_json()["rows"]], ["dsSecTx"])
        self.conn.commit.assert_not_called()
        self.assertEqual(len(self.cur.execute.call_args_list), 3)

    def test_rural_row_only_real_evidence_and_shared_rtms_configuration(self):
        now = datetime.now(timezone.utc)
        prior = (now-timedelta(hours=12)).isoformat()
        meta = {
            "rural_hanok_trade_sync_status": stored("rural_hanok_trade_sync_status", {
                "state": "failed", "error": "timeout serviceKey=FAKE_PRIVATE",
                "counters": {"fetched:SHTrade": 8}}),
            "rural_hanok_trade_last_success": stored("rural_hanok_trade_last_success", {
                "state": "done", "last_success_at": prior}),
            "rtms_provider_daily_calls": stored("rtms_provider_daily_calls", {
                "date": now.date().isoformat(), "count": 100}),
        }
        for enabled, expected in (({}, "직접"), ({"rtms": True}, "중계")):
            result = build_board(meta, now=now, enabled=enabled)
            row = next(r for r in result["rows"] if r["key"] == "dsSecRuralHanokTrades")
            self.assertEqual(row["state"], "실패")
            self.assertIsNotNone(row["last_success_at"])
            self.assertIsNone(row["today_calls"])
            self.assertEqual(row["route"], expected)
            for api in ("RHTrade", "SHTrade", "LandTrade"):
                self.assertIn(api, row["route_note"])
            self.assertFalse(row["controls"]["run"])
            self.assertNotIn("FAKE_PRIVATE", json.dumps(row))

    def test_quota_pause_separate_from_consecutive_error_pause(self):
        for reason, expected in (("daily_cap", True), ("consecutive_errors", False)):
            meta = {"tx_sync_status": stored("tx_sync_status", {
                "state": "paused", "stop_reason": reason})}
            row = next(r for r in build_board(meta, enabled={})["rows"] if r["key"] == "dsSecTx")
            self.assertEqual(row["quota_paused"], expected)
        meta = {"onbid_sync_status": stored("onbid_sync_status", {"state": "waiting_quota"})}
        row = next(r for r in build_board(meta, enabled={})["rows"] if r["key"] == "dsSecOnbid")
        self.assertEqual(row["state"], "일시중단")
        self.assertTrue(row["quota_paused"])


if __name__ == "__main__":
    unittest.main()
