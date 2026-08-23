"""Focused regression tests for committed-data stats invalidation paths.

All database and network edges are fakes; the tests deliberately invoke the
real Flask views and sync/merge functions rather than the stats helper alone.
"""

import os
import sys
import unittest
import hashlib
import hmac
from argparse import Namespace
from unittest.mock import patch


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
os.environ.setdefault("FLASK_SECRET_KEY", "focused-test-secret")
os.environ.setdefault("DATA_GO_KR_BROKER_API_KEY", "test-api-key")
os.environ.setdefault("PROD_DATABASE_URL", "postgresql://invalid/test")

# app imports run a schema gate.  It must not contact a database in this unit test.
import db  # noqa: E402

with patch.object(db, "init_db"):
    import app as app_module  # noqa: E402

import merge_dev_to_prod  # noqa: E402
import sync_brhub  # noqa: E402
import sync_lodgings  # noqa: E402
import sync_permits  # noqa: E402


class FakeConnection:
    def __init__(self, cursor, events=None):
        self._cursor = cursor
        self.events = events if events is not None else []

    def cursor(self):
        return self._cursor

    def commit(self):
        self.events.append("commit")

    def rollback(self):
        self.events.append("rollback")

    def close(self):
        self.events.append("close")


class FakeCursor:
    def __init__(self, responder=None):
        self.responder = responder or (lambda _sql, _params: None)
        self.current = None
        self.rowcount = 0
        self.closed = False

    def execute(self, sql, params=None):
        self.current = self.responder(" ".join(sql.split()), params)
        if isinstance(self.current, tuple) and self.current[:1] == ("rowcount",):
            self.rowcount = self.current[1]
            self.current = None

    def fetchone(self):
        if isinstance(self.current, list):
            return self.current.pop(0) if self.current else None
        result, self.current = self.current, None
        return result

    def fetchall(self):
        result, self.current = self.current or [], None
        return list(result)

    def close(self):
        self.closed = True


class FakeRefreshResponse:
    def __init__(self, *, ok=True, status_code=200, payload=None, json_error=None):
        self.ok = ok
        self.status_code = status_code
        self.payload = payload or {}
        self.json_error = json_error

    def json(self):
        if self.json_error:
            raise self.json_error
        return self.payload


class AppMutationInvalidationTests(unittest.TestCase):
    def setUp(self):
        app_module.app.config.update(
            TESTING=True,
            SECRET_KEY="focused-test-secret",
            RATELIMIT_ENABLED=False,
        )
        app_module.limiter.reset()
        self.client = app_module.app.test_client()
        with self.client.session_transaction() as session:
            session["admin"] = True

    @staticmethod
    def _stats_refresh_cache(failed=()):
        section_keys = (
            "lodging_stats",
            "region_match",
            "consign_stats",
            "closure_stats",
            "transaction_stats",
        )
        return {
            "ts": 1_700_000_000,
            "sections": {
                key: {
                    "status": "error" if key in failed else "ok",
                    "error": "test failure" if key in failed else None,
                }
                for key in section_keys
            },
        }

    def test_admin_stats_refresh_requires_admin_session(self):
        anonymous = app_module.app.test_client()

        response = anonymous.post("/api/admin/stats/refresh")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["ok"], False)

    @staticmethod
    def _internal_refresh_headers(timestamp, secret="internal-test-secret"):
        signature = hmac.new(
            secret.encode("utf-8"),
            f"POST:/api/admin/stats/refresh:{timestamp}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return {
            "X-Stats-Refresh-Timestamp": str(timestamp),
            "X-Stats-Refresh-Signature": signature,
        }

    def test_signed_internal_stats_refresh_rebuilds_without_admin_session(self):
        cache = self._stats_refresh_cache()
        anonymous = app_module.app.test_client()
        timestamp = "1700000000"
        with (
            patch.dict(os.environ, {"SESSION_SECRET": "internal-test-secret"}),
            patch.object(app_module.time, "time", return_value=int(timestamp)),
            patch.object(app_module, "_rebuild_master_stats", return_value=cache) as rebuild,
        ):
            response = anonymous.post(
                "/api/admin/stats/refresh",
                headers=self._internal_refresh_headers(timestamp),
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])
        rebuild.assert_called_once_with(force=True)

    def test_invalid_or_stale_internal_stats_refresh_signature_is_rejected(self):
        anonymous = app_module.app.test_client()
        timestamp = "1700000000"
        with patch.dict(os.environ, {"SESSION_SECRET": "internal-test-secret"}):
            invalid = anonymous.post(
                "/api/admin/stats/refresh",
                headers={
                    "X-Stats-Refresh-Timestamp": timestamp,
                    "X-Stats-Refresh-Signature": "not-a-valid-signature",
                },
            )
        with (
            patch.dict(os.environ, {"SESSION_SECRET": "internal-test-secret"}),
            patch.object(app_module.time, "time", return_value=int(timestamp) + 61),
        ):
            stale = anonymous.post(
                "/api/admin/stats/refresh",
                headers=self._internal_refresh_headers(timestamp),
            )

        self.assertEqual(invalid.status_code, 401)
        self.assertEqual(stale.status_code, 401)

    def test_admin_stats_refresh_returns_all_section_results(self):
        cache = self._stats_refresh_cache()
        with patch.object(
            app_module, "_rebuild_master_stats", return_value=cache
        ) as rebuild:
            response = self.client.post("/api/admin/stats/refresh")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["refreshed_at"])
        self.assertEqual(payload["sections"], {
            "lodging_stats": True,
            "region_match": True,
            "consign_stats": True,
            "closure_stats": True,
            "transaction_stats": True,
        })
        rebuild.assert_called_once_with(force=True)

    def test_admin_stats_refresh_keeps_success_for_partial_section_failure(self):
        cache = self._stats_refresh_cache(failed=("closure_stats",))
        with patch.object(app_module, "_rebuild_master_stats", return_value=cache):
            response = self.client.post("/api/admin/stats/refresh")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["sections"], {
            "lodging_stats": True,
            "region_match": True,
            "consign_stats": True,
            "closure_stats": False,
            "transaction_stats": True,
        })

    def test_admin_stats_refresh_reports_failure_when_all_sections_fail(self):
        cache = self._stats_refresh_cache(failed=(
            "lodging_stats",
            "region_match",
            "consign_stats",
            "closure_stats",
            "transaction_stats",
        ))
        with patch.object(app_module, "_rebuild_master_stats", return_value=cache):
            response = self.client.post("/api/admin/stats/refresh")

        self.assertEqual(response.status_code, 500)
        self.assertFalse(response.get_json()["ok"])

    def _marker(self, events):
        def mark(source):
            self.assertIn("commit", events, source)
            events.append(("marker", source))
        return mark

    def _marker_after_source_write(self, events, write_event):
        def mark(source):
            self.assertIn(write_event, events, source)
            write_index = max(
                index for index, event in enumerate(events)
                if event == write_event
            )
            self.assertTrue(
                any(
                    event == "commit" and index > write_index
                    for index, event in enumerate(events)
                ),
                f"{source} invalidated stats before its source-data commit",
            )
            events.append(("marker", source))
        return mark

    def test_correction_changed_data_marks_only_after_commit(self):
        events = []

        def respond(sql, _params):
            if sql.startswith("INSERT INTO building_requests"):
                events.append("building_request_write")
                return {"id": 91}
            if sql.startswith("SELECT id, building_name"):
                return {
                    "id": 7, "building_name": "기존명",
                    "lodging_type": "생활", "name_pending": True,
                }
            if sql.startswith("UPDATE master_buildings"):
                events.append("master_source_write")
            elif sql.startswith("UPDATE transactions"):
                events.append("transaction_source_write")
            return None

        conn = FakeConnection(FakeCursor(respond), events)

        class Bjdong:
            def __init__(self, _path):
                pass

            def find_bjdong_cd(self, _sgg, _umd):
                return "12345"

        payload = {
            "sgg_cd": "11111", "umd_nm": "테스트동", "jibun": "1",
            "suggested_lodging_type": "일반",
            "suggested_building_name": "제안명",
        }
        with (
            patch.object(app_module, "get_conn", return_value=conn),
            patch("address_utils.BjdongMap", Bjdong),
            patch("building_registry.classify_lodging_type",
                  return_value=("일반", "detail", None, {"bldNm": "공식명"}, "ok")),
            patch("building_registry.resolve_api_building_name", return_value="공식명"),
            patch.object(app_module, "mark_master_stats_invalidated",
                         side_effect=self._marker_after_source_write(
                             events, "transaction_source_write"
                         )),
        ):
            response = self.client.post("/api/request-correction", json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["changed"])
        self.assertIn(("marker", "request_correction"), events)
        request_write = events.index("building_request_write")
        master_write = events.index("master_source_write")
        transaction_write = events.index("transaction_source_write")
        commits = [
            index for index, event in enumerate(events) if event == "commit"
        ]
        marker = events.index(("marker", "request_correction"))
        self.assertEqual(len(commits), 2)
        self.assertLess(request_write, commits[0])
        self.assertLess(commits[0], master_write)
        self.assertLess(master_write, transaction_write)
        self.assertLess(transaction_write, commits[1])
        self.assertLess(commits[1], marker)

    def test_admin_buildings_bulk_update_marks_after_source_commit(self):
        events = []

        def respond(sql, _params):
            if sql.startswith("UPDATE master_buildings"):
                events.append("bulk_update_source_write")
                return ("rowcount", 2)
            return None

        conn = FakeConnection(FakeCursor(respond), events)
        with (
            patch.object(app_module, "get_conn", return_value=conn),
            patch.object(
                app_module,
                "mark_master_stats_invalidated",
                side_effect=self._marker_after_source_write(
                    events, "bulk_update_source_write"
                ),
            ) as marker,
        ):
            response = self.client.post(
                "/api/admin/buildings/bulk-update",
                json={"ids": [11, 12], "field": "building_name", "value": "일괄명"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["updated"], 2)
        marker.assert_called_once_with("admin_buildings_bulk_update")

    def test_admin_buildings_bulk_delete_marks_after_source_commit(self):
        events = []

        def respond(sql, _params):
            if sql.startswith("SELECT DISTINCT master_building_id"):
                return []
            if sql.startswith("SELECT id, sgg_cd"):
                return []
            if sql.startswith("DELETE FROM master_buildings"):
                events.append("bulk_delete_source_write")
                return ("rowcount", 2)
            return None

        conn = FakeConnection(FakeCursor(respond), events)
        with (
            patch.object(app_module, "get_conn", return_value=conn),
            patch.object(
                app_module,
                "mark_master_stats_invalidated",
                side_effect=self._marker_after_source_write(
                    events, "bulk_delete_source_write"
                ),
            ) as marker,
        ):
            response = self.client.post(
                "/api/admin/buildings/bulk-delete",
                json={"ids": [21, 22]},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {
            "ok": True, "deleted": 2, "skipped": 0,
        })
        marker.assert_called_once_with("admin_buildings_bulk_delete")

    def test_admin_create_building_from_lodging_marks_after_source_commit(self):
        events = []

        def respond(sql, _params):
            if sql.startswith("SELECT biz_name"):
                return {
                    "biz_name": "테스트호텔",
                    "road_address": "서울 테스트로 1",
                    "jibun_address": "서울 테스트동 1",
                    "room_count": 12,
                }
            if sql.startswith("INSERT INTO master_buildings"):
                events.append("lodging_building_source_write")
                return {"id": 77}
            return None

        conn = FakeConnection(FakeCursor(respond), events)
        with (
            patch.object(app_module, "get_conn", return_value=conn),
            patch.object(
                app_module,
                "mark_master_stats_invalidated",
                side_effect=self._marker_after_source_write(
                    events, "lodging_building_source_write"
                ),
            ) as marker,
        ):
            response = self.client.post(
                "/api/admin/unmatched-building-candidates/permit-77/create-building"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"ok": True, "building_id": 77})
        marker.assert_called_once_with("admin_create_building_from_lodging")

    def test_master_create_update_delete_crud_paths_mark_committed_changes(self):
        events = []

        create = FakeConnection(FakeCursor(
            lambda sql, _p: {"id": 10} if sql.startswith("INSERT INTO master_buildings") else None
        ), events)
        update = FakeConnection(FakeCursor(
            lambda sql, _p: {"exists": 1} if sql.startswith("SELECT 1 FROM master_buildings") else None
        ), events)

        def delete_response(sql, _params):
            if sql.startswith("SELECT sgg_cd"):
                return {"sgg_cd": "11111", "umd_nm": "동", "jibun": "1", "building_name": "건물"}
            if sql.startswith("SELECT COUNT(*)"):
                return {"c": 0}
            return None

        delete = FakeConnection(FakeCursor(delete_response), events)
        with (
            patch.object(app_module, "get_conn", side_effect=[create, update, delete]),
            patch.object(app_module, "_fill_master_coords"),
            patch.object(app_module, "mark_master_stats_invalidated",
                         side_effect=self._marker(events)),
        ):
            self.assertEqual(self.client.post(
                "/api/admin/buildings",
                json={"building_name": "새 건물", "road_address": "서울 테스트로 1"},
            ).status_code, 200)
            self.assertEqual(self.client.put(
                "/api/admin/buildings/10", json={"building_name": "바뀐 건물"}
            ).status_code, 200)
            self.assertEqual(self.client.delete(
                "/api/admin/buildings/10"
            ).status_code, 200)

        sources = [event[1] for event in events if isinstance(event, tuple)]
        self.assertEqual(sources, [
            "admin_buildings_create",
            "admin_buildings_update",
            "admin_buildings_delete",
        ])

    def test_transaction_edit_and_name_approval_mark_after_commit(self):
        events = []
        tx = FakeConnection(FakeCursor(
            lambda sql, _p: {"price": 100}
            if sql.startswith("SELECT price FROM transactions") else None
        ), events)

        def approval_response(sql, _params):
            if sql.startswith("SELECT id, status"):
                return {
                    "id": 3, "status": "name_review",
                    "suggested_building_name": "승인명", "master_building_id": 8,
                }
            if sql.startswith("UPDATE master_buildings"):
                return ("rowcount", 1)
            return None

        approval = FakeConnection(FakeCursor(approval_response), events)
        with (
            patch.object(app_module, "get_conn", side_effect=[tx, approval]),
            patch.object(app_module, "mark_master_stats_invalidated",
                         side_effect=self._marker(events)),
        ):
            edited = self.client.put(
                "/api/admin/transactions/2",
                json={"reason": "오입력 수정", "price": 200},
            )
            approved = self.client.post(
                "/api/admin/building-requests/3/approve-name"
            )

        self.assertEqual(edited.status_code, 200)
        self.assertEqual(edited.get_json()["logged"], 1)
        self.assertEqual(approved.status_code, 200)
        sources = [event[1] for event in events if isinstance(event, tuple)]
        self.assertEqual(sources, [
            "admin_transactions_update",
            "admin_building_request_approve_name",
        ])

    def test_operator_building_assignment_marks_after_commit_and_not_on_missing_building(self):
        events = []

        def respond(sql, _params):
            if sql.startswith("SELECT 1 FROM master_buildings"):
                return {"exists": 1}
            if sql.startswith("SELECT COUNT(*) c FROM operator_buildings"):
                return {"c": 0}
            if sql.startswith("INSERT INTO operator_buildings"):
                events.append("operator_building_assignment_write")
            return None

        conn = FakeConnection(FakeCursor(respond), events)
        with self.client.session_transaction() as session:
            session["operator_id"] = 17
        with (
            patch.object(app_module, "get_conn", return_value=conn),
            patch.object(
                app_module,
                "mark_master_stats_invalidated",
                side_effect=self._marker_after_source_write(
                    events, "operator_building_assignment_write"
                ),
            ) as marker,
        ):
            response = self.client.post(
                "/api/operator/buildings",
                json={"master_building_id": 42, "note": "담당"},
            )

        self.assertEqual(response.status_code, 200)
        marker.assert_called_once()

        with (
            patch.object(app_module, "get_conn") as get_conn,
            patch.object(app_module, "mark_master_stats_invalidated") as marker,
        ):
            response = self.client.post(
                "/api/operator/buildings",
                json={"master_building_id": "not-an-id"},
            )
        self.assertEqual(response.status_code, 400)
        get_conn.assert_not_called()
        marker.assert_not_called()

    def test_operator_building_delete_marks_after_commit_but_not_when_missing(self):
        events = []

        def respond(sql, _params):
            if sql.startswith("DELETE FROM operator_buildings"):
                events.append("operator_building_delete_write")
                return ("rowcount", 1)
            return None

        conn = FakeConnection(FakeCursor(respond), events)
        with self.client.session_transaction() as session:
            session["operator_id"] = 17
        with (
            patch.object(app_module, "get_conn", return_value=conn),
            patch.object(
                app_module,
                "mark_master_stats_invalidated",
                side_effect=self._marker_after_source_write(
                    events, "operator_building_delete_write"
                ),
            ) as marker,
        ):
            response = self.client.delete("/api/operator/buildings/42")

        self.assertEqual(response.status_code, 200)
        marker.assert_called_once()

        missing = FakeConnection(FakeCursor(
            lambda sql, _params: ("rowcount", 0)
            if sql.startswith("DELETE FROM operator_buildings") else None
        ))
        with (
            patch.object(app_module, "get_conn", return_value=missing),
            patch.object(app_module, "mark_master_stats_invalidated") as marker,
        ):
            response = self.client.delete("/api/operator/buildings/999")
        self.assertEqual(response.status_code, 404)
        marker.assert_not_called()

    def test_operator_approval_with_preferred_building_marks_after_commit(self):
        events = []
        application = {
            "id": 71, "status": "submitted", "applicant_type": "operator",
            "office_or_company_name": "테스트 운영사", "owner_name": "대표",
            "category": "위탁운영", "biz_reg_number": "123-45-67890",
            "phone": "01012345678", "email": "operator@example.test",
            "website_url": None, "password_hash": "stored-hash",
            "doc_logo_url": None, "office_address": None,
            "preferred_building_id": 42,
        }

        def respond(sql, _params):
            if sql.startswith("SELECT * FROM applications"):
                return application
            if sql.startswith("SELECT 1 FROM operators"):
                return None
            if sql.startswith("INSERT INTO operators"):
                events.append("approved_operator_write")
                return {"id": 18}
            if sql.startswith("INSERT INTO operator_buildings"):
                events.append("approved_operator_building_write")
            return None

        conn = FakeConnection(FakeCursor(respond), events)
        with (
            patch.object(app_module, "get_conn", return_value=conn),
            patch.object(app_module, "send_sms", return_value=(True, "sent")),
            patch.object(app_module, "_send_approval_email", return_value=(True, "sent")),
            patch.object(
                app_module,
                "mark_master_stats_invalidated",
                side_effect=self._marker_after_source_write(
                    events, "approved_operator_building_write"
                ),
            ) as marker,
        ):
            response = self.client.post("/api/admin/applications/71/approve")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["created_id"], 18)
        marker.assert_called_once()

    def test_admin_operator_update_and_delete_mark_after_commit(self):
        events = []

        def update_response(sql, _params):
            if sql.startswith("SELECT status, category FROM operators"):
                return {"status": "approved", "category": "위탁운영"}
            if sql.startswith("UPDATE operators"):
                events.append("admin_operator_update_write")
            return None

        def delete_response(sql, _params):
            if sql.startswith("SELECT 1 FROM operators"):
                return {"exists": 1}
            if sql.startswith("DELETE FROM operators"):
                events.append("admin_operator_delete_write")
                return ("rowcount", 1)
            return None

        update = FakeConnection(FakeCursor(update_response), events)
        delete = FakeConnection(FakeCursor(delete_response), events)
        with (
            patch.object(app_module, "get_conn", side_effect=[update, delete]),
            patch.object(
                app_module,
                "mark_master_stats_invalidated",
                side_effect=[
                    self._marker_after_source_write(events, "admin_operator_update_write"),
                    self._marker_after_source_write(events, "admin_operator_delete_write"),
                ],
            ) as marker,
        ):
            updated = self.client.put(
                "/api/admin/members/operator/18/detail",
                json={"status": "inactive"},
            )
            deleted = self.client.post(
                "/api/admin/members/bulk-delete",
                json={"confirm": "삭제", "ids": [{"type": "operator", "id": 18}]},
            )

        self.assertEqual(updated.status_code, 200)
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(marker.call_count, 2)

        with patch.object(app_module, "mark_master_stats_invalidated") as marker:
            response = self.client.put(
                "/api/admin/members/operator/18/detail", json={}
            )
        self.assertEqual(response.status_code, 400)
        marker.assert_not_called()

    def test_admin_permits_cleanup_marks_only_for_actual_cleanup_after_commit(self):
        events = []

        def respond(sql, _params):
            if sql.startswith("SELECT id FROM master_buildings"):
                return [{"id": 31}, {"id": 32}]
            if sql.startswith("DELETE FROM master_buildings"):
                events.append("permits_cleanup_write")
                return ("rowcount", 2)
            return None

        conn = FakeConnection(FakeCursor(respond), events)
        with (
            patch.object(app_module, "get_conn", return_value=conn),
            patch.object(
                app_module,
                "mark_master_stats_invalidated",
                side_effect=self._marker_after_source_write(
                    events, "permits_cleanup_write"
                ),
            ) as marker,
        ):
            response = self.client.post(
                "/api/admin/permits-cleanup", json={"dry_run": False}
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["deleted"], 2)
        marker.assert_called_once()

        noop = FakeConnection(FakeCursor(
            lambda sql, _params: [] if sql.startswith("SELECT id FROM master_buildings") else None
        ))
        with (
            patch.object(app_module, "get_conn", return_value=noop),
            patch.object(app_module, "mark_master_stats_invalidated") as marker,
        ):
            response = self.client.post(
                "/api/admin/permits-cleanup", json={"dry_run": False}
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["deleted"], 0)
        marker.assert_not_called()


class SyncInvalidationTests(unittest.TestCase):
    def test_sync_completion_helpers_post_signed_refresh_and_accept_partial_success(self):
        timestamp = "1700000000"
        secret = "internal-test-secret"
        expected_headers = {
            "X-Stats-Refresh-Timestamp": timestamp,
            "X-Stats-Refresh-Signature": hmac.new(
                secret.encode("utf-8"),
                f"POST:/api/admin/stats/refresh:{timestamp}".encode("utf-8"),
                hashlib.sha256,
            ).hexdigest(),
        }
        partial_response = FakeRefreshResponse(payload={
            "ok": True,
            "sections": {
                "lodging_stats": True,
                "closure_stats": False,
            },
        })

        for module in (sync_lodgings, sync_brhub):
            with self.subTest(module=module.__name__):
                with (
                    patch.dict(os.environ, {"SESSION_SECRET": secret}),
                    patch.object(module.time, "time", return_value=int(timestamp)),
                    patch.object(
                        module.requests, "post", return_value=partial_response
                    ) as post,
                ):
                    module._refresh_master_stats_after_completion()

                post.assert_called_once_with(
                    module._INTERNAL_STATS_REFRESH_URL,
                    headers=expected_headers,
                    timeout=180,
                )

    def test_sync_completion_helpers_tolerate_failed_http_or_payload(self):
        failures = (
            ("http", FakeRefreshResponse(
                ok=False,
                status_code=500,
                payload={"ok": False, "message": "server failed"},
            )),
            ("payload", FakeRefreshResponse(json_error=ValueError("invalid JSON"))),
        )

        for module in (sync_lodgings, sync_brhub):
            for label, response in failures:
                with self.subTest(module=module.__name__, failure=label):
                    with (
                        patch.dict(os.environ, {"SESSION_SECRET": "internal-test-secret"}),
                        patch.object(module.requests, "post", return_value=response) as post,
                    ):
                        module._refresh_master_stats_after_completion()

                    post.assert_called_once()

    def test_lodging_run_refreshes_only_after_successful_completion(self):
        args = Namespace(
            reindex_norms=False,
            status_key=None,
            num_rows=1000,
            sleep=0,
            max_calls=10,
            reset=False,
        )
        cases = (
            ("completed", (True, 3, 1), 1),
            ("incomplete", (False, 3, 1), 0),
            ("error", RuntimeError("sync failed"), 0),
        )

        for label, outcome, expected_refreshes in cases:
            with self.subTest(label=label):
                with (
                    patch.object(
                        sync_lodgings,
                        "sync_lodgings",
                        side_effect=outcome if isinstance(outcome, Exception) else None,
                        return_value=None if isinstance(outcome, Exception) else outcome,
                    ),
                    patch.object(sync_lodgings, "send_room_expiry_alerts", return_value={
                        "target_count": 0,
                        "sent_count": 0,
                        "email_sent_count": 0,
                        "in_app_count": 0,
                        "failed_count": 0,
                    }),
                    patch.object(
                        sync_lodgings, "_refresh_master_stats_after_completion"
                    ) as refresh,
                    patch.object(sync_lodgings.sys, "exit") as exit_process,
                ):
                    sync_lodgings._run(args)

                self.assertEqual(refresh.call_count, expected_refreshes)
                self.assertEqual(exit_process.call_count, int(label == "error"))

    def test_lodging_run_reindex_refreshes_after_reindex_completion(self):
        args = Namespace(reindex_norms=True)
        with (
            patch.object(sync_lodgings, "reindex_lodging_norms") as reindex,
            patch.object(
                sync_lodgings, "_refresh_master_stats_after_completion"
            ) as refresh,
        ):
            sync_lodgings._run(args)

        reindex.assert_called_once_with()
        refresh.assert_called_once_with()

        with (
            patch.object(
                sync_lodgings,
                "reindex_lodging_norms",
                side_effect=RuntimeError("reindex failed"),
            ),
            patch.object(
                sync_lodgings, "_refresh_master_stats_after_completion"
            ) as refresh,
        ):
            with self.assertRaisesRegex(RuntimeError, "reindex failed"):
                sync_lodgings._run(args)
        refresh.assert_not_called()

    def test_brhub_main_refreshes_only_after_successful_completed_non_dry_run(self):
        cases = (
            ("completed", False, (True, 2, 0, 2, "completed"), 1),
            ("incomplete", False, (False, 2, 0, 2, "limit"), 0),
            ("dry_run", True, (True, 2, 0, 2, "completed"), 0),
            ("error", False, RuntimeError("sync failed"), 0),
        )

        for label, dry_run, outcome, expected_refreshes in cases:
            argv = ["sync_brhub.py"]
            if dry_run:
                argv.append("--dry-run")
            with self.subTest(label=label):
                with (
                    patch.object(sync_brhub.sys, "argv", argv),
                    patch.object(
                        sync_brhub,
                        "run",
                        side_effect=outcome if isinstance(outcome, Exception) else None,
                        return_value=None if isinstance(outcome, Exception) else outcome,
                    ),
                    patch.object(
                        sync_brhub, "_refresh_master_stats_after_completion"
                    ) as refresh,
                    patch.object(sync_brhub.sys, "exit") as exit_process,
                ):
                    sync_brhub.main()

                self.assertEqual(refresh.call_count, expected_refreshes)
                self.assertEqual(exit_process.call_count, int(label == "error"))

    def test_lodging_no_change_completion_signals_after_last_sync_commit(self):
        events = []

        def respond(sql, params):
            if sql.startswith("DELETE FROM app_meta"):
                events.append("clear_progress_write")
            elif sql.startswith("SELECT COUNT(*) AS c FROM lodging_registry"):
                return {"c": 17}
            elif (
                sql.startswith("INSERT INTO app_meta")
                and params
                and params[0] == sync_lodgings.LAST_SYNC_META_KEY
            ):
                events.append("last_sync_write")
            return None

        conn = FakeConnection(FakeCursor(respond), events)

        def signal():
            last_sync_write = events.index("last_sync_write")
            self.assertTrue(
                any(
                    event == "commit" and index > last_sync_write
                    for index, event in enumerate(events)
                ),
                "lodging completion invalidated stats before _mark_last_sync committed",
            )
            events.append("marker")

        with (
            patch.object(sync_lodgings, "get_conn", return_value=conn) as get_conn,
            patch.object(
                sync_lodgings,
                "_load_progress",
                return_value={"next_page": 1, "total_count": None},
            ),
            patch.object(sync_lodgings, "_daily_calls_today", return_value=0),
            patch.object(sync_lodgings, "_bump_daily_calls", return_value=1),
            patch.object(
                sync_lodgings,
                "_fetch_page_retry",
                return_value=([], 0, False),
            ),
            patch.object(
                sync_lodgings,
                "refresh_auto_building_names",
                return_value=0,
            ),
            patch.object(
                sync_lodgings, "_signal_stats_change", side_effect=signal
            ) as marker,
            patch.object(sync_lodgings.requests, "get") as network,
        ):
            result = sync_lodgings.sync_lodgings(sleep_sec=0, max_calls=10)

        self.assertEqual(result, (True, 0, 1))
        get_conn.assert_called_once_with()
        network.assert_not_called()
        marker.assert_called_once_with()
        last_sync_write = events.index("last_sync_write")
        last_sync_commit = next(
            index
            for index, event in enumerate(events)
            if index > last_sync_write and event == "commit"
        )
        self.assertLess(last_sync_commit, events.index("marker"))

    def test_permit_commit_is_signaled_before_later_ownership_loss(self):
        events = []

        def respond(sql, _params):
            if sql.startswith("INSERT INTO master_buildings"):
                events.append("permit_source_write")
            return None

        conn = FakeConnection(FakeCursor(respond), events)
        args = Namespace(
            reset=True, limit=0, daily_cap=99, sleep=0, dry_run=False,
        )
        permit = {
            "mainPurpsCdNm": "숙박시설",
            "etcPurps": "",
            "bun": "1",
            "ji": "0",
            "platPlc": "서울 테스트구 일동 1",
            "bldNm": "테스트 생활숙박시설",
        }

        def save_progress(connection, _cursor, _progress):
            connection.commit()

        def signal(source):
            self.assertEqual(source, "sync_permits")
            self.assertIn("permit_source_write", events)
            source_write = events.index("permit_source_write")
            self.assertTrue(
                any(
                    event == "commit" and index > source_write
                    for index, event in enumerate(events)
                ),
                "permit stats invalidation preceded the source-data commit",
            )
            events.append("marker")

        with (
            patch.object(sync_permits, "get_conn", return_value=conn),
            patch.object(sync_permits, "_load_codes", return_value=(
                {"11111": "서울 테스트구"},
                [
                    ["1111100001", "서울 테스트구 일동"],
                    ["1111100002", "서울 테스트구 이동"],
                ],
            )),
            patch.object(
                sync_permits,
                "_load_existing_keys",
                return_value=(set(), set(), set(), set()),
            ),
            patch.object(sync_permits, "_still_owner", side_effect=[True, False]),
            patch.object(sync_permits, "_fetch_page", return_value=[permit]),
            patch.object(sync_permits, "_save_progress", side_effect=save_progress),
            patch.object(sync_permits, "mark_master_stats_invalidated",
                         side_effect=signal) as marker,
            patch.object(sync_permits.time, "sleep"),
        ):
            with self.assertRaisesRegex(RuntimeError, "소유권 상실"):
                sync_permits.run(
                    args, status_key="permit_status", run_id="first-run",
                )

        self.assertIn("commit", events)
        self.assertIn("marker", events)
        marker.assert_called_once_with("sync_permits")

    def test_permit_noop_does_not_false_signal(self):
        conn = FakeConnection(FakeCursor())
        args = Namespace(
            reset=True, limit=1, daily_cap=99, sleep=0, dry_run=False,
        )

        with (
            patch.object(sync_permits, "get_conn", return_value=conn),
            patch.object(sync_permits, "_load_codes", return_value=(
                {"11111": "서울 테스트구"},
                [["1111100001", "서울 테스트구 일동"]],
            )),
            patch.object(
                sync_permits,
                "_load_existing_keys",
                return_value=(set(), set(), set(), set()),
            ),
            patch.object(sync_permits, "_fetch_page", return_value=[]),
            patch.object(sync_permits, "_save_progress"),
            patch.object(sync_permits, "mark_master_stats_invalidated") as marker,
            patch.object(sync_permits.time, "sleep"),
        ):
            result = sync_permits.run(args)

        self.assertEqual(result[2], 0)
        marker.assert_not_called()

    def test_reindex_norms_and_auto_name_changes_signal_after_commit(self):
        events = []
        cursor = FakeCursor(lambda sql, _p: [
            {"id": 1, "road_address": "서울 테스트로 1", "jibun_address": "서울 테스트동 1"}
        ] if sql.startswith("SELECT id, road_address") else None)
        conn = FakeConnection(cursor, events)

        def execute_values(_cur, _sql, _rows, **_kwargs):
            cursor.rowcount = 1

        def signal():
            self.assertIn("commit", events)
            events.append("marker")

        with (
            patch.object(sync_lodgings, "get_conn", return_value=conn),
            patch.object(sync_lodgings, "execute_values", side_effect=execute_values),
            patch.object(sync_lodgings, "refresh_auto_building_names", return_value=1),
            patch.object(sync_lodgings, "_signal_stats_change", side_effect=signal),
        ):
            self.assertEqual(sync_lodgings.reindex_lodging_norms(), 1)
        self.assertEqual(events.count("marker"), 2)

    def test_reindex_noop_does_not_false_signal(self):
        cursor = FakeCursor(lambda sql, _p: [] if sql.startswith("SELECT id, road_address") else None)
        conn = FakeConnection(cursor)
        with (
            patch.object(sync_lodgings, "get_conn", return_value=conn),
            patch.object(sync_lodgings, "refresh_auto_building_names", return_value=0),
            patch.object(sync_lodgings, "_signal_stats_change") as marker,
        ):
            self.assertEqual(sync_lodgings.reindex_lodging_norms(), 0)
        marker.assert_not_called()

    def test_lodging_page_commit_is_signaled_before_later_fetch_failure(self):
        events = []
        conn = FakeConnection(FakeCursor(), events)
        item = {
            "BPLC_NM": "테스트호텔", "MNG_NO": "permit-1",
            "SNTTN_BZSTAT_NM": "일반호텔", "ROAD_NM_ADDR": "서울 테스트로 1",
        }

        def fetch(_key, page, _rows):
            if page == 1:
                return [item], 999, False
            raise RuntimeError("later network failure")

        def signal():
            self.assertIn("commit", events)
            events.append("marker")

        with (
            patch.object(sync_lodgings, "get_conn", return_value=conn),
            patch.object(sync_lodgings, "_load_progress",
                         return_value={"next_page": 1, "total_count": None}),
            patch.object(sync_lodgings, "_daily_calls_today", return_value=0),
            patch.object(sync_lodgings, "_bump_daily_calls", side_effect=[1, 2]),
            patch.object(sync_lodgings, "_fetch_page_retry", side_effect=fetch),
            patch.object(sync_lodgings, "_upsert", return_value=True),
            patch.object(sync_lodgings, "_save_progress"),
            patch.object(sync_lodgings, "_signal_stats_change", side_effect=signal),
            patch.object(sync_lodgings.time, "sleep"),
        ):
            with self.assertRaisesRegex(RuntimeError, "later network failure"):
                sync_lodgings.sync_lodgings(sleep_sec=0, max_calls=10)
        self.assertEqual(events.count("marker"), 1)

    def test_brhub_commit_is_signaled_before_later_dong_failure(self):
        events = []

        def respond(sql, _params):
            if sql.startswith("INSERT INTO master_buildings"):
                return {"id": 44}
            return None

        conn = FakeConnection(FakeCursor(respond), events)
        args = Namespace(
            reset=True, start_idx=-1, progress_key="test_progress", daily_cap=99,
            sleep=0, workers=1, end_idx=-1, limit=0, dry_run=False,
        )
        lodging = {
            "regstrGbCdNm": "일반", "mainPurpsCdNm": "숙박시설",
            "etcPurps": "", "bun": "1", "ji": "0", "platPlc": "서울 테스트동 1",
            "newPlatPlc": "서울 테스트로 1", "bldNm": "테스트모텔", "hoCnt": "5",
        }
        fetch_results = [
            ([lodging], 1, None, False),
            (None, 0, "later network failure", False),
        ]

        def signal():
            self.assertIn("commit", events)
            events.append("marker")

        with (
            patch.object(sync_brhub, "get_conn", return_value=conn),
            patch.object(sync_brhub, "_load_codes", return_value=(
                {"11111": "서울 테스트구"},
                [["1111100001", "서울 테스트구 일동"], ["1111100002", "서울 테스트구 이동"]],
            )),
            patch.object(sync_brhub, "_load_existing_keys", return_value=(set(), set(), set())),
            patch.object(sync_brhub, "_combined_calls_today", return_value=0),
            patch.object(sync_brhub, "_fetch_all_dong_pages", side_effect=fetch_results),
            patch.object(sync_brhub, "_save_progress"),
            patch.object(sync_brhub, "refresh_auto_building_names", return_value=0),
            patch.object(sync_brhub, "_signal_stats_change", side_effect=signal),
        ):
            result = sync_brhub.run(args)

        self.assertEqual(result[2], 1)
        self.assertEqual(events.count("marker"), 1)

    def test_brhub_progress_commit_is_followed_by_invalidation_marker(self):
        events = []

        def respond(sql, params):
            if sql.startswith("INSERT INTO master_buildings"):
                events.append("building_insert")
                return {"id": 45}
            if (
                sql.startswith("INSERT INTO app_meta")
                and params
                and params[0] == "test_progress"
            ):
                events.append("progress_write")
            return None

        conn = FakeConnection(FakeCursor(respond), events)
        args = Namespace(
            reset=True, start_idx=-1, progress_key="test_progress", daily_cap=99,
            sleep=0, workers=1, end_idx=-1, limit=0, dry_run=False,
        )
        lodging = {
            "regstrGbCdNm": "일반", "mainPurpsCdNm": "숙박시설",
            "etcPurps": "", "bun": "1", "ji": "0",
            "platPlc": "서울 테스트동 1",
            "newPlatPlc": "서울 테스트로 1", "bldNm": "테스트모텔",
            "hoCnt": "5",
        }

        def signal():
            events.append("marker")

        with (
            patch.object(sync_brhub, "get_conn", return_value=conn) as get_conn,
            patch.object(sync_brhub, "_load_codes", return_value=(
                {"11111": "서울 테스트구"},
                [["1111100001", "서울 테스트구 일동"]],
            )),
            patch.object(
                sync_brhub,
                "_load_existing_keys",
                return_value=(set(), set(), set()),
            ),
            patch.object(sync_brhub, "_combined_calls_today", return_value=0),
            patch.object(
                sync_brhub,
                "_fetch_all_dong_pages",
                return_value=([lodging], 1, None, False),
            ),
            patch.object(
                sync_brhub, "refresh_auto_building_names", return_value=0
            ),
            patch.object(
                sync_brhub, "_signal_stats_change", side_effect=signal
            ) as marker,
            patch.object(sync_brhub.requests, "get") as network,
        ):
            result = sync_brhub.run(args)

        self.assertEqual(result[2], 1)
        get_conn.assert_called_once_with()
        network.assert_not_called()
        self.assertGreaterEqual(marker.call_count, 1)

        insert = events.index("building_insert")
        progress_write = events.index("progress_write")
        source_commit = next(
            index
            for index, event in enumerate(events)
            if index > insert and event == "commit"
        )
        progress_commit = next(
            index
            for index, event in enumerate(events)
            if index > progress_write and event == "commit"
        )
        markers_after_progress = [
            index
            for index, event in enumerate(events)
            if event == "marker" and index > progress_commit
        ]
        self.assertLess(insert, source_commit)
        self.assertLess(source_commit, progress_write)
        self.assertLess(progress_write, progress_commit)
        self.assertTrue(
            markers_after_progress,
            "brhub invalidation occurred only before the progress commit",
        )


class MergeInvalidationTests(unittest.TestCase):
    def test_transaction_batch_commit_is_signaled_before_later_batch_failure(self):
        events = []

        class MergeCursor(FakeCursor):
            def __init__(self, role):
                super().__init__()
                self.role = role
                self.current = None

            def execute(self, sql, params=None):
                compact = " ".join(sql.split())
                if self.role == "prod" and compact.startswith("SELECT raw_key"):
                    self.current = []
                elif "information_schema.columns" in compact:
                    self.current = [("raw_key",), ("deal_amount",)]
                elif self.role == "dev" and compact.startswith("SELECT deal_amount, raw_key"):
                    self.current = [(n, f"k-{n}") for n in range(501)]
                else:
                    self.current = []

        dev_cur = MergeCursor("dev")
        prod_cur = MergeCursor("prod")
        prod_conn = FakeConnection(prod_cur, events)
        batches = 0

        def execute_values(_cur, _sql, rows, **_kwargs):
            nonlocal batches
            batches += 1
            if batches == 2:
                raise RuntimeError("later production failure")
            prod_cur.current = [(row[1],) for row in rows]

        def signal():
            self.assertIn("commit", events)
            events.append("marker")

        with (
            patch.object(merge_dev_to_prod.psycopg2.extras, "execute_values",
                         side_effect=execute_values),
            patch.object(merge_dev_to_prod, "_signal_prod_stats_change", side_effect=signal),
        ):
            with self.assertRaisesRegex(RuntimeError, "later production failure"):
                merge_dev_to_prod.merge_transactions(
                    dev_cur, prod_conn, prod_cur, dry_run=False
                )
        self.assertEqual(events.count("marker"), 1)

    def test_merge_dry_run_does_not_signal(self):
        dev = FakeCursor(lambda sql, _p: [] if sql.startswith("SELECT building_name") else None)
        prod = FakeCursor(lambda sql, _p: [] if sql.startswith("SELECT road_address") else None)
        with patch.object(merge_dev_to_prod, "_signal_prod_stats_change") as marker:
            self.assertEqual(
                merge_dev_to_prod.merge_buildings(
                    dev, FakeConnection(prod), prod, dry_run=True
                ),
                (0, 0),
            )
        marker.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)