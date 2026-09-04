"""Focused no-DB regression coverage for lodging-operator public boundaries."""
import os
import sys
import unittest
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


if __name__ == "__main__":
    unittest.main()