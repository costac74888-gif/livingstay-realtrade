"""HTTP contracts for the isolated annual-roster admin endpoints."""
import io
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("SKIP_STARTUP_SCHEMA_INIT", "1")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import app as application


class AnnualTourismRosterRouteTests(unittest.TestCase):
    def setUp(self):
        application.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        self.client = application.app.test_client()
        with self.client.session_transaction() as session:
            session["admin"] = True
            session["admin_user_id"] = 7

    def test_preview_uses_exact_endpoint_and_returns_preview_contract(self):
        conn = MagicMock()
        result = {
            "token": "preview-token", "total_rows": 1, "active_facilities": 1,
            "active_rooms": 2, "inactive_count": 0, "review_count": 0,
            "reference_year": 2025, "next_collection_year": 2026,
            "source_name": "문화체육관광부 공개 명부",
            "building_cross_check": {"matched": 0, "unmatched": 1, "ambiguous": 0, "conflict": 0},
        }
        with patch.object(application, "get_conn", return_value=conn), \
             patch.object(application.annual_tourism_roster, "assert_production_connection"), \
             patch.object(application.annual_tourism_roster, "store_preview", return_value=result) as preview:
            response = self.client.post("/api/admin/annual-tourism-roster/preview", data={
                "file": (io.BytesIO(b"PK\x03\x04"), "2025년_관광숙박업.xlsx"),
                "reference_year": "2025",
                "next_collection_year": "2026",
                "source_name": "문화체육관광부 공개 명부",
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"ok": True, **result})
        self.assertEqual(preview.call_args.args[2], 7)
        self.assertEqual(preview.call_args.args[3:], ("2025", "2026", "문화체육관광부 공개 명부"))
        conn.close.assert_called_once()

    def test_apply_returns_production_guard_as_explicit_client_error(self):
        conn = MagicMock()
        with patch.object(application, "get_conn", return_value=conn), \
             patch.object(application.annual_tourism_roster, "apply",
                          side_effect=RuntimeError("운영 서버에서만 적용할 수 있습니다.")):
            response = self.client.post("/api/admin/annual-tourism-roster/apply",
                                        json={"token": "preview-token"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["ok"], False)
        self.assertIn("운영 서버", response.get_json()["message"])
        conn.close.assert_called_once()

    def test_status_returns_applied_numbers_reference_date_and_source(self):
        conn = MagicMock()
        approved = {
            "permit_count": 2929,
            "room_count": 219621,
            "sub_rows": [],
            "source": {
                "reference_year": 2025,
                "next_collection_year": 2026,
                "source_name": "문화체육관광부 공개 명부",
                "source_file": "2025년말_관광숙박업_등록현황.xlsx",
                "approved_at": "2026-09-06 12:00:00+00",
                "building_cross_check": {"matched": 1550, "unmatched": 1379},
            },
        }
        with patch.object(application, "get_conn", return_value=conn), \
             patch.object(application.annual_tourism_roster, "latest_approved_stats",
                           return_value=approved), \
             patch.object(application.annual_tourism_roster, "latest_pending_preview",
                          return_value=None):
            response = self.client.get("/api/admin/annual-tourism-roster/status")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["permit_count"], 2929)
        self.assertEqual(payload["room_count"], 219621)
        self.assertEqual(payload["reference_date"], "2025-12-31")
        self.assertEqual(payload["source_file"], approved["source"]["source_file"])
        self.assertEqual(payload["source_name"], approved["source"]["source_name"])
        self.assertEqual(payload["next_collection_year"], 2026)
        conn.close.assert_called_once()

    def test_override_updates_total_delta_and_public_tourism_breakdown(self):
        base = {
            "ok": True,
            "rows": [
                {"type": "전체", "permit_count": 85098, "room_count": 1015152},
                {"type": "관광", "building_count": 765, "units": 19678,
                 "permit_count": 939, "room_count": 110461, "report_rate": 74.1},
            ],
        }
        approved = {
            "permit_count": 2929,
            "room_count": 219621,
            "sub_rows": [
                {"type": "호스텔업", "permit_count": 1396, "room_count": 18952,
                 "linked_building_count": 2},
                {"type": "수상관광호텔업", "permit_count": 0, "room_count": 0,
                 "linked_building_count": 0},
            ],
            "source": {"reference_year": 2025},
        }
        with patch.object(application, "get_conn", return_value=MagicMock()), \
             patch.object(application.annual_tourism_roster, "latest_approved_stats",
                          return_value=approved):
            result = application._apply_annual_tourism_roster_override(base)
        total, tourism = result["rows"]
        self.assertEqual(total["permit_count"], 87088)
        self.assertEqual(total["room_count"], 1124312)
        public = application._public_lodging_stats_payload(result)
        public_tourism = public["rows"][1]
        self.assertEqual(public_tourism["sub_rows"][0]["type"], "호스텔업")
        self.assertEqual(public_tourism["sub_rows"][0]["building_count"], 2)
        self.assertEqual(public_tourism["sub_rows"][1]["type"], "수상관광호텔업")

    def test_hotel_operation_zip_apply_uses_production_guard(self):
        conn = MagicMock()
        result = {
            "inserted": True, "reference_year": 2024,
            "region_rows": 149, "total_rows": 633,
        }
        with patch.object(application, "get_conn", return_value=conn), \
             patch.object(application.annual_tourism_roster,
                          "assert_production_connection") as guard, \
             patch.object(application.import_hotel_operation,
                          "import_uploaded_operation_zip",
                          return_value=result) as importer:
            response = self.client.post("/api/admin/hotel-operation/apply", data={
                "file": (io.BytesIO(b"PK\x03\x04"), "2024_운영현황.zip"),
                "reference_year": "2024",
            })
        self.assertEqual(200, response.status_code)
        self.assertEqual(149, response.get_json()["region_rows"])
        guard.assert_called_once_with(conn)
        self.assertEqual("2024", importer.call_args.args[1])

    def test_hotel_operation_status_reports_current_archive(self):
        conn = MagicMock()
        current = {
            "reference_year": 2024, "source_file": "2024_운영현황.zip",
            "region_rows": 149, "total_rows": 633,
        }
        with patch.object(application, "get_conn", return_value=conn), \
             patch.object(application.import_hotel_operation,
                          "latest_operation_status", return_value=current):
            response = self.client.get("/api/admin/hotel-operation/status")
        self.assertEqual(200, response.status_code)
        self.assertTrue(response.get_json()["applied"])
        self.assertEqual(current, response.get_json()["current"])


if __name__ == "__main__":
    unittest.main()