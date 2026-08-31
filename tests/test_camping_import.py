import unittest
from datetime import datetime
from pathlib import Path
import time
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
        self.assertEqual(parsed["phone"], "0558540404")

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


if __name__ == "__main__":
    unittest.main()