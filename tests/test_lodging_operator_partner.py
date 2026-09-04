"""Focused no-DB regression coverage for lodging-operator public boundaries."""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
os.environ.setdefault("FLASK_SECRET_KEY", "lodging-test-secret")
import db  # noqa: E402
with patch.object(db, "init_db"):
    import app as app_module  # noqa: E402


class LodgingOperatorBoundaryTests(unittest.TestCase):
    def setUp(self):
        app_module.app.config.update(TESTING=True, RATELIMIT_ENABLED=False)
        self.client = app_module.app.test_client()

    def test_submit_requires_identity_login_and_consent_before_db(self):
        response = self.client.post("/api/apply/lodging-operator", json={
            "lodging_op_type": "airbnb", "biz_name": "테스트", "phone": "01012345678",
            "permit_no": "P-1", "airbnb_url": "https://www.airbnb.co.kr/rooms/123",
        })
        self.assertEqual(response.status_code, 400)

    def test_public_url_allowlist_rejects_script_and_bad_airbnb(self):
        self.assertIsNone(app_module._public_http_url("javascript:alert(1)"))
        self.assertIsNone(app_module._public_http_url("https://example.com/rooms/123", airbnb_only=True))
        self.assertEqual(app_module._public_http_url("https://www.airbnb.com/rooms/123", airbnb_only=True),
                         "https://www.airbnb.com/rooms/123")

    def test_owner_edit_requires_authenticated_approved_owner(self):
        response = self.client.get("/api/lodging-operator/me")
        self.assertEqual(response.status_code, 401)

    def test_schema_version_advances_for_airbnb_urls_migration(self):
        self.assertGreater(db.SCHEMA_VERSION, "2026-09-04-03")

    def test_extra_airbnb_urls_are_bound_as_jsonb_not_pg_array(self):
        self.assertEqual(
            app_module._jsonb_airbnb_urls(["https://www.airbnb.com/rooms/123"]),
            '["https://www.airbnb.com/rooms/123"]',
        )
        self.assertEqual(
            app_module._jsonb_airbnb_urls('["https://www.airbnb.com/rooms/456"]'),
            '["https://www.airbnb.com/rooms/456"]',
        )

    def test_gocamping_only_uses_canonical_content_id_key(self):
        self.assertEqual(
            app_module._gocamping_url_for_registry_key("CAMPING:12345"),
            "https://www.gocamping.or.kr/bsite/camp/info/read.do?c_sn=12345",
        )
        self.assertIsNone(
            app_module._gocamping_url_for_registry_key("CAMPING:authority:permit")
        )

    def test_matched_permit_is_canonicalized_to_registry_key(self):
        matched = {"id": 7, "permit_number": "CAMPING:12345"}
        self.assertEqual(
            app_module._canonical_operator_permit(matched, "123-45"),
            "CAMPING:12345",
        )
        self.assertEqual(
            app_module._canonical_operator_permit(None, "unmatched-1"),
            "unmatched-1",
        )

    def test_registry_duplicate_guard_runs_a_locked_lookup(self):
        class Cursor:
            def __init__(self):
                self.sql = ""
                self.params = None
            def execute(self, sql, params):
                self.sql, self.params = " ".join(sql.split()), params
            def fetchone(self):
                return {"id": 99}
        cursor = Cursor()
        self.assertTrue(app_module._lodging_registry_operator_exists(cursor, {"id": 7}))
        self.assertIn("lodging_reg_id=%s", cursor.sql)
        self.assertIn("FOR UPDATE", cursor.sql)
        self.assertEqual(cursor.params, [7])

    def test_schema_declares_partial_registry_uniqueness_without_cleanup(self):
        source = (Path(ROOT) / "db.py").read_text(encoding="utf-8")
        self.assertIn("CREATE UNIQUE INDEX IF NOT EXISTS idx_op_lodging_registry_unique", source)
        self.assertIn("WHERE lodging_reg_id IS NOT NULL", source)
        self.assertNotIn("DELETE FROM operator_lodging", source)
        self.assertGreater(db.SCHEMA_VERSION, "2026-09-04-04")

    def test_partner_counts_reuse_public_lodging_statistics_values(self):
        payload = {
            "ok": True,
            "rows": [
                {"type": "에어비앤비", "building_count": 11209, "room_count": 0},
                {
                    "type": "캠핑",
                    "building_count": 3662,
                    "camping_facility_count": 6296,
                    "room_count": 65146,
                },
                {"type": "농어촌민박", "building_count": 36618, "room_count": 103582},
                {"type": "한옥", "building_count": 2590, "room_count": 2499},
                {"type": "생활", "building_count": 7191, "room_count": 168608},
            ],
        }
        stats = app_module._lodging_operator_stats_from_full(payload)["stats"]
        self.assertEqual(stats["airbnb"]["count"], 11209)
        self.assertEqual(stats["camping"]["count"], 6296)
        self.assertEqual(stats["rural"]["count"], 36618)
        self.assertEqual(stats["hanok"]["count"], 2590)
        self.assertEqual(stats["living"]["rooms"], 168608)

    def test_partner_hero_names_lodging_operators(self):
        html = (Path(ROOT) / "static" / "partner.html").read_text(encoding="utf-8")
        self.assertIn("운영자·중개사·운영지원업체·금융 파트너이신가요?", html)

    def test_partner_pages_fetch_the_same_public_stats_as_data_lab(self):
        for filename in ("partner.html", "apply_lodging_operator.html"):
            html = (Path(ROOT) / "static" / filename).read_text(encoding="utf-8")
            self.assertIn('fetch("/api/v1/d/3f7")', html.replace("'", '"'))
            self.assertIn('rows["캠핑"]?.camping_facility_count', html)
            self.assertIn('rows["생활"]?.room_count', html)


if __name__ == "__main__":
    unittest.main()