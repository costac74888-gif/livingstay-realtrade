import unittest
from datetime import datetime
from io import StringIO
from pathlib import Path
import time
from types import SimpleNamespace
from unittest import mock

import import_camping_lodging as importer
import sync_lodgings


def _camping_row(**overrides):
    row = {
        "개방자치단체코드": 3030000,
        "관리번호": "CDFI2262132015000001",
        "인허가일자": datetime(2015, 6, 30),
        "영업상태명": "영업/정상",
        "사업장명": "테스트 캠핑장",
        "객실수": None,
        "건물용도명": None,
        "데이터갱신시점": datetime(2026, 8, 30, 12, 34, 56),
        "도로명주소": "서울특별시 성동구 뚝섬로 273 (성수동1가)",
        "상세영업상태명": "영업중",
        "시설규모": 2000,
        "전화번호": "02-1234-5678",
        "지번주소": "서울특별시 성동구 성수동1가 643",
        "지역구분명": "자연녹지지역",
    }
    row.update(overrides)
    return row


class CampingImportTests(unittest.TestCase):
    def test_uses_camping_source_key_and_legal_type(self):
        parsed = importer.parse_row(_camping_row())

        self.assertEqual(
            parsed["permit_number"],
            "CAMPING:3030000:CDFI2262132015000001",
        )
        self.assertEqual(parsed["hygiene_type"], "일반야영장업")
        self.assertEqual(parsed["lodging_type"], "캠핑")
        self.assertEqual(parsed["master_source"], "camping_import")

    def test_same_management_number_in_different_authorities_does_not_collide(self):
        first = importer.parse_row(_camping_row(개방자치단체코드=3030000))
        second = importer.parse_row(_camping_row(개방자치단체코드=3040000))

        self.assertNotEqual(first["permit_number"], second["permit_number"])

    def test_camping_room_count_is_not_used_as_lodging_room_count(self):
        parsed = importer.parse_row(
            _camping_row(객실수=12, 야영사이트수=37)
        )

        self.assertIsNone(parsed["room_count"])
        self.assertEqual(parsed["camping_site_count"], 37)

    def test_non_active_rows_are_preserved_for_status_refresh(self):
        parsed = importer.parse_row(_camping_row(영업상태명="폐업"))

        self.assertEqual(parsed["biz_status_name"], "폐업")

    def test_automotive_camping_uses_parent_type_and_subtype(self):
        parsed = importer.parse_row(
            _camping_row(문화체육업종명="자동차야영장업")
        )

        self.assertEqual(parsed["hygiene_type"], "자동차야영장업")
        self.assertEqual(parsed["lodging_type"], "캠핑")
        self.assertEqual(parsed["lodging_subtype"], "자동차야영")

    def test_gocamping_item_uses_content_id_and_separate_site_count(self):
        parsed = importer.parse_api_item({
            "contentId": "217764",
            "facltNm": "솔섬오토캠핑장",
            "addr1": "경상남도 사천시 서포면 토끼로 245-29",
            "manageSttus": "운영",
            "gnrlSiteCo": "10",
            "autoSiteCo": "12",
            "glampSiteCo": "3",
            "caravSiteCo": "2",
            "indvdlCaravSiteCo": "1",
            "allar": "1234.5",
            "tel": "055-854-0404",
            "modifiedtime": "20260830123456",
        })

        self.assertEqual(parsed["permit_number"], "CAMPING:217764")
        self.assertEqual(parsed["biz_status_name"], "영업/정상")
        self.assertEqual(parsed["hygiene_type"], "일반야영장업")
        self.assertIsNone(parsed["room_count"])
        self.assertEqual(parsed["camping_site_count"], 28)
        self.assertEqual(parsed["camping_general_site_count"], 10)
        self.assertEqual(parsed["camping_auto_site_count"], 12)
        self.assertEqual(parsed["camping_glamping_site_count"], 3)
        self.assertEqual(parsed["camping_caravan_site_count"], 3)
        self.assertEqual(parsed["camping_classification"], "confirmed_mixed")
        self.assertEqual(parsed["phone"], "0558540404")

    def test_gocamping_missing_invalid_and_negative_site_counts_are_safe_unknown(self):
        parsed = importer.parse_api_item({
            "contentId": "217765",
            "facltNm": "유형 미확인 캠핑장",
            "manageSttus": "운영",
            "gnrlSiteCo": "not-a-number",
            "autoSiteCo": "-2",
            "glampSiteCo": None,
        })

        self.assertEqual(parsed["camping_site_count"], 0)
        self.assertEqual(parsed["camping_general_site_count"], 0)
        self.assertEqual(parsed["camping_auto_site_count"], 0)
        self.assertEqual(parsed["camping_glamping_site_count"], 0)
        self.assertEqual(parsed["camping_caravan_site_count"], 0)
        self.assertEqual(parsed["camping_classification"], "unknown")

    def test_gocamping_single_positive_type_gets_specific_internal_classification(self):
        parsed = importer.parse_api_item({
            "contentId": "217766",
            "facltNm": "글램핑 전용",
            "manageSttus": "운영",
            "glampSiteCo": "5",
        })

        self.assertEqual(parsed["camping_classification"], "glamping_only")

    def test_gocamping_status_changes_keep_same_source_key(self):
        active = importer.parse_api_item({
            "contentId": 100,
            "facltNm": "테스트 캠핑장",
            "manageSt": "운영",
        })
        closed = importer.parse_api_item({
            "contentId": 100,
            "facltNm": "테스트 캠핑장",
            "manageSt": "폐업",
        })

        self.assertEqual(active["permit_number"], closed["permit_number"])
        self.assertEqual(closed["biz_status_name"], "폐업")

    def test_gocamping_real_status_field_takes_precedence(self):
        parsed = importer.parse_api_item({
            "contentId": "101",
            "facltNm": "상태 테스트 캠핑장",
            "manageSttus": "휴장",
            "manageSt": "운영",
        })

        self.assertEqual(parsed["biz_status_name"], "휴업")

    def test_real_xlsx_is_read_by_shared_header_parser(self):
        fixture = Path(
            "attached_assets/문화_일반야영장업1_1788079511098.xlsx"
        )
        if not fixture.exists():
            self.skipTest("선택적 원본 야영장 XLSX가 작업공간에 없음")
        rows = importer.common.read_rows(str(fixture))

        self.assertEqual(len(rows), 4901)
        self.assertEqual(rows[0]["문화체육업종명"], "일반야영장업")


class _CaptureCursor:
    def __init__(self):
        self.sql = ""

    def execute(self, sql, params):
        self.sql = sql

    def fetchone(self):
        return {"id": 1, "is_new": False}


class CampingSyncTests(unittest.TestCase):
    def test_operational_paths_include_camping_sync(self):
        root = Path(__file__).resolve().parents[1]
        app_source = (root / "app.py").read_text(encoding="utf-8")
        workflow_source = (root / ".replit").read_text(encoding="utf-8")

        self.assertIn(
            '"--include-camping", "--status-key", _LODGING_SYNC_META_KEY',
            app_source,
        )
        self.assertIn(
            "sync_lodgings.py --include-camping",
            workflow_source,
        )
        self.assertIn("camping_sync_progress", app_source)
        self.assertIn('"camping_completed"', app_source)

    def test_admin_runner_starts_combined_lodging_and_camping_sync(self):
        import app as app_module
        from db import get_conn

        status_key = f"test_camping_admin_runner_{time.time_ns()}"
        conn = get_conn()
        cur = conn.cursor()
        try:
            cur.execute("DELETE FROM app_meta WHERE key=%s", (status_key,))
            conn.commit()
        finally:
            cur.close()
            conn.close()

        process = mock.Mock()
        process.wait.return_value = 0
        try:
            with (
                mock.patch.object(
                    app_module, "_LODGING_SYNC_META_KEY", status_key
                ),
                mock.patch.object(
                    app_module.subprocess,
                    "Popen",
                    return_value=process,
                ) as popen,
                mock.patch.dict(
                    app_module.os.environ,
                    {
                        "DATA_GO_KR_BROKER_API_KEY": "test-key",
                        "LODGING_SERVICE_KEY": "test-key",
                    },
                ),
            ):
                client = app_module.app.test_client()
                with client.session_transaction() as session:
                    session["admin"] = True
                response = client.post("/api/admin/sync-lodgings")
                status_response = client.get(
                    "/api/admin/lodging-sync-status"
                )

            self.assertEqual(response.status_code, 202)
            command = popen.call_args.args[0]
            self.assertIn("--include-camping", command)
            self.assertEqual(
                command[command.index("--status-key") + 1],
                status_key,
            )
            self.assertEqual(status_response.status_code, 200)
            camping_status = status_response.get_json()["camping"]
            self.assertEqual(
                camping_status["daily_cap"],
                sync_lodgings.CAMPING_MAX_DAILY_CALLS,
            )
        finally:
            conn = get_conn()
            cur = conn.cursor()
            try:
                cur.execute("DELETE FROM app_meta WHERE key=%s", (status_key,))
                conn.commit()
            finally:
                cur.close()
                conn.close()

    def test_conflict_update_refreshes_site_count_without_clearing_match(self):
        cursor = _CaptureCursor()
        data = importer.parse_api_item({
            "contentId": "102",
            "facltNm": "사이트수 테스트",
            "manageSttus": "운영",
            "gnrlSiteCo": "9",
        })

        importer.common._upsert_registry(
            cursor, data, reset_applied_building_id=False
        )

        self.assertIn(
            "camping_site_count = EXCLUDED.camping_site_count",
            cursor.sql,
        )
        self.assertIn(
            "applied_building_id = lodging_registry.applied_building_id",
            cursor.sql,
        )

    def test_unique_xlsx_row_is_adopted_by_gocamping_source_key(self):
        cursor = mock.Mock()
        cursor.fetchone.return_value = None
        cursor.fetchall.return_value = [
            {"id": 9, "applied_building_id": 77}
        ]
        data = importer.parse_api_item({
            "contentId": "103",
            "facltNm": "기존 캠핑장",
            "addr1": "서울특별시 성동구 뚝섬로 273",
            "manageSttus": "운영",
        })

        reconciled = sync_lodgings._reconcile_camping_source_key(
            cursor, data
        )

        self.assertTrue(reconciled)
        update_sql, update_params = cursor.execute.call_args_list[-1].args
        self.assertIn("SET permit_number=%s", update_sql)
        self.assertEqual(update_params, ("CAMPING:103", 9))

    def test_ambiguous_xlsx_rows_are_not_merged(self):
        cursor = mock.Mock()
        cursor.fetchone.return_value = None
        cursor.fetchall.return_value = [
            {"id": 9, "applied_building_id": 77},
            {"id": 10, "applied_building_id": 78},
        ]
        data = importer.parse_api_item({
            "contentId": "104",
            "facltNm": "동명이 캠핑장",
            "addr1": "서울특별시 성동구 뚝섬로 273",
            "manageSttus": "운영",
        })

        reconciled = sync_lodgings._reconcile_camping_source_key(
            cursor, data
        )

        self.assertFalse(reconciled)
        self.assertEqual(cursor.execute.call_count, 2)

    @mock.patch("sync_lodgings.time.sleep")
    @mock.patch("sync_lodgings._fetch_camping_page")
    def test_camping_fetch_retries_three_times(
        self, fetch_page, sleep
    ):
        fetch_page.side_effect = [
            RuntimeError("첫 실패"),
            RuntimeError("둘째 실패"),
            ([{"contentId": "1"}], 1),
        ]
        attempts = []

        result = sync_lodgings._fetch_camping_page_retry(
            "secret",
            3,
            100,
            on_attempt=lambda: attempts.append(1),
            retry_waits=(0, 0),
        )

        self.assertEqual(result[1], 1)
        self.assertEqual(len(attempts), 3)
        self.assertEqual(fetch_page.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    def test_camping_fetch_reads_standard_response_envelope(self):
        response = mock.Mock()
        response.json.return_value = {
            "response": {
                "header": {"resultCode": "0000", "resultMsg": "OK"},
                "body": {
                    "items": {
                        "item": {
                            "contentId": "7",
                            "facltNm": "단일 응답",
                            "manageSttus": "운영",
                        }
                    },
                    "totalCount": "1",
                },
            }
        }
        with mock.patch(
            "sync_lodgings.requests.get", return_value=response
        ) as get:
            items, total = sync_lodgings._fetch_camping_page(
                "secret", 1, 100
            )

        self.assertEqual(total, 1)
        self.assertEqual(items[0]["contentId"], "7")
        params = get.call_args.kwargs["params"]
        self.assertEqual(params["_type"], "json")
        self.assertEqual(params["MobileOS"], "ETC")

    def test_camping_fetch_rejects_malformed_page_shapes_with_clear_path(self):
        malformed_payloads = (
            ([], "최상위 JSON"),
            ({"response": []}, "response가 객체"),
            (
                {"response": {"header": {}, "body": []}},
                "response.body가 객체",
            ),
            (
                {
                    "response": {
                        "header": {},
                        "body": {"items": {"item": ("bad",)}, "totalCount": 1},
                    }
                },
                "items.item",
            ),
            (
                {
                    "response": {
                        "header": {},
                        "body": {"items": {"item": []}},
                    }
                },
                "totalCount",
            ),
        )
        for payload, expected in malformed_payloads:
            with self.subTest(expected=expected):
                response = mock.Mock()
                response.json.return_value = payload
                with (
                    mock.patch(
                        "sync_lodgings.requests.get", return_value=response
                    ),
                    self.assertRaisesRegex(
                        sync_lodgings.CampingResponseValidationError,
                        expected,
                    ),
                ):
                    sync_lodgings._fetch_camping_page("secret", 1, 100)

    def test_camping_sync_skips_bad_row_and_finishes_valid_first_page(self):
        conn = mock.Mock()
        conn.cursor.return_value = mock.Mock()
        items = [
            ("unexpected", "tuple"),
            {
                "contentId": "7",
                "facltNm": "정상 캠핑장",
                "manageSttus": "운영",
            },
        ]

        def fetch_page(*args, on_attempt, **kwargs):
            on_attempt()
            return items, 2

        with (
            mock.patch.dict(
                sync_lodgings.os.environ,
                {sync_lodgings.CAMPING_SERVICE_KEY_ENV: "secret"},
            ),
            mock.patch.object(sync_lodgings, "get_conn", return_value=conn),
            mock.patch.object(
                sync_lodgings.camping_importer.common, "_assert_schema"
            ),
            mock.patch.object(
                sync_lodgings,
                "_load_camping_progress",
                return_value={"next_page": 1, "total_count": None},
            ),
            mock.patch.object(
                sync_lodgings, "_daily_calls_today", return_value=0
            ),
            mock.patch.object(
                sync_lodgings, "_bump_daily_calls", return_value=1
            ),
            mock.patch.object(
                sync_lodgings,
                "_fetch_camping_page_retry",
                side_effect=fetch_page,
            ),
            mock.patch("sys.stdout", new_callable=StringIO) as output,
        ):
            completed, counters, calls_today = sync_lodgings.sync_camping(
                num_rows=100,
                sleep_sec=0,
                max_calls=10,
                dry_run=True,
            )

        self.assertTrue(completed)
        self.assertEqual(calls_today, 1)
        self.assertEqual(counters["skipped"], 1)
        self.assertEqual(counters["validation_errors"], 1)
        self.assertIn("페이지 1 행 1 검증 오류", output.getvalue())
        self.assertIn("type=tuple", output.getvalue())

    def test_empty_page_before_total_preserves_checkpoint_for_retry(self):
        conn = mock.Mock()
        conn.cursor.return_value = mock.Mock()
        with (
            mock.patch.dict(
                sync_lodgings.os.environ,
                {sync_lodgings.CAMPING_SERVICE_KEY_ENV: "secret"},
            ),
            mock.patch.object(sync_lodgings, "get_conn", return_value=conn),
            mock.patch.object(
                sync_lodgings.camping_importer.common, "_assert_schema"
            ),
            mock.patch.object(
                sync_lodgings,
                "_load_camping_progress",
                return_value={"next_page": 1, "total_count": None},
            ),
            mock.patch.object(
                sync_lodgings, "_daily_calls_today", return_value=0
            ),
            mock.patch.object(
                sync_lodgings, "_bump_daily_calls", return_value=1
            ),
            mock.patch.object(
                sync_lodgings.camping_importer.common,
                "_load_master_indexes",
                return_value=({}, {}),
            ),
            mock.patch.object(
                sync_lodgings,
                "_fetch_camping_page_retry",
                return_value=([], 10),
            ),
            mock.patch.object(sync_lodgings, "_save_camping_progress") as save,
            mock.patch.object(sync_lodgings, "_clear_camping_progress") as clear,
            self.assertRaisesRegex(
                sync_lodgings.CampingResponseValidationError,
                "페이지 1가 비어 있지만",
            ),
        ):
            sync_lodgings.sync_camping(
                num_rows=100,
                sleep_sec=0,
                max_calls=10,
                dry_run=False,
            )

        save.assert_not_called()
        clear.assert_not_called()
        conn.rollback.assert_called_once()

    def test_row_storage_index_error_isolated_and_checkpoint_advances(self):
        conn = mock.Mock()
        cursor = mock.Mock()
        conn.cursor.return_value = cursor
        items = [
            {
                "contentId": "bad-1",
                "facltNm": "저장 오류 캠핑장",
                "manageSttus": "운영",
            },
            {
                "contentId": "good-2",
                "facltNm": "정상 저장 캠핑장",
                "manageSttus": "운영",
            },
        ]

        def fetch_page(*args, on_attempt, **kwargs):
            on_attempt()
            return items, 3

        with (
            mock.patch.dict(
                sync_lodgings.os.environ,
                {sync_lodgings.CAMPING_SERVICE_KEY_ENV: "secret"},
            ),
            mock.patch.object(sync_lodgings, "get_conn", return_value=conn),
            mock.patch.object(
                sync_lodgings.camping_importer.common, "_assert_schema"
            ),
            mock.patch.object(
                sync_lodgings.camping_importer.common,
                "_load_master_indexes",
                return_value=({}, {}),
            ),
            mock.patch.object(
                sync_lodgings,
                "_load_camping_progress",
                return_value={"next_page": 1, "total_count": None},
            ),
            mock.patch.object(
                sync_lodgings, "_daily_calls_today", return_value=0
            ),
            mock.patch.object(
                sync_lodgings, "_bump_daily_calls", return_value=1
            ),
            mock.patch.object(
                sync_lodgings,
                "_fetch_camping_page_retry",
                side_effect=fetch_page,
            ),
            mock.patch.object(sync_lodgings, "_reconcile_camping_source_key"),
            mock.patch.object(
                sync_lodgings.camping_importer.common,
                "_upsert_registry",
                side_effect=[
                    IndexError("tuple index out of range"),
                    {"id": 2, "is_new": True},
                ],
            ),
            mock.patch.object(
                sync_lodgings, "_save_camping_progress"
            ) as save_progress,
            mock.patch.object(sync_lodgings, "_signal_stats_change"),
            mock.patch("sys.stdout", new_callable=StringIO) as output,
        ):
            completed, counters, calls_today = sync_lodgings.sync_camping(
                num_rows=100,
                sleep_sec=0,
                max_calls=1,
                dry_run=False,
            )

        self.assertFalse(completed)
        self.assertEqual(calls_today, 1)
        self.assertEqual(counters["failed"], 1)
        self.assertEqual(counters["inserted"], 1)
        self.assertEqual(counters["unmatched"], 1)
        self.assertIn("tuple index out of range", output.getvalue())
        save_progress.assert_called_once_with(cursor, conn, 2, 3)
        executed_sql = [call.args[0] for call in cursor.execute.call_args_list]
        self.assertIn("ROLLBACK TO SAVEPOINT camping_item", executed_sql)

    def test_camping_source_reconcile_escapes_sql_like_wildcards(self):
        cursor = mock.Mock()
        cursor.fetchone.return_value = None
        cursor.fetchall.return_value = []
        data = {
            "permit_number": "CAMPING:123",
            "biz_name_norm": "테스트캠핑장",
            "road_norm": "서울특별시중구세종대로1",
            "jibun_norm": None,
        }

        reconciled = sync_lodgings._reconcile_camping_source_key(cursor, data)

        self.assertFalse(reconciled)
        legacy_query = cursor.execute.call_args_list[1].args[0]
        self.assertIn("LIKE 'CAMPING:%%:%%'", legacy_query)

    def test_incomplete_camping_run_exits_nonzero_for_scheduled_retry(self):
        args = SimpleNamespace(
            status_key=None,
            num_rows=None,
            sleep=0,
            max_calls=None,
            reset=False,
            dry_run=False,
        )
        with (
            mock.patch.object(
                sync_lodgings,
                "sync_camping",
                return_value=(False, {"skipped": 0}, 800),
            ),
            self.assertRaises(SystemExit) as exit_error,
        ):
            sync_lodgings._run_camping(args)

        self.assertEqual(exit_error.exception.code, 1)

    def test_incomplete_camping_status_is_partial_and_retryable(self):
        args = SimpleNamespace(
            status_key="camping-status",
            num_rows=None,
            sleep=0,
            max_calls=None,
            reset=False,
            dry_run=False,
        )
        running = {"state": "running", "run_id": "run-1"}
        writes = []
        with (
            mock.patch.object(
                sync_lodgings,
                "_read_status",
                side_effect=[running, running.copy()],
            ),
            mock.patch.object(
                sync_lodgings,
                "_write_status",
                side_effect=lambda key, value, run_id: writes.append(value.copy()),
            ),
            mock.patch.object(
                sync_lodgings,
                "sync_camping",
                return_value=(False, {"skipped": 0}, 800),
            ),
        ):
            sync_lodgings._run_camping(args)

        self.assertEqual(writes[-1]["state"], "partial")
        self.assertFalse(writes[-1]["completed"])
        self.assertTrue(writes[-1]["retryable"])
        self.assertIn("체크포인트부터 재시도", writes[-1]["error"])


if __name__ == "__main__":
    unittest.main()
