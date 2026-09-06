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
            "building_cross_check": {"matched": 0, "unmatched": 1, "ambiguous": 0, "conflict": 0},
        }
        with patch.object(application, "get_conn", return_value=conn), \
             patch.object(application.annual_tourism_roster, "assert_production_connection"), \
             patch.object(application.annual_tourism_roster, "store_preview", return_value=result) as preview:
            response = self.client.post("/api/admin/annual-tourism-roster/preview", data={
                "file": (io.BytesIO(b"PK\x03\x04"), "2025년_관광숙박업.xlsx"),
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"ok": True, **result})
        self.assertEqual(preview.call_args.args[2], 7)
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


if __name__ == "__main__":
    unittest.main()