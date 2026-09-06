"""Regression contracts for admin policy publication and manual release identity."""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("SKIP_STARTUP_SCHEMA_INIT", "1")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as application
from scripts import build_policy_manual_bundle as bundle


class PolicyAdminRouteTests(unittest.TestCase):
    def setUp(self):
        application.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        self.client = application.app.test_client()
        with self.client.session_transaction() as session:
            session["admin"] = True
            session["admin_user_id"] = 7

    def test_create_cannot_bypass_publish_action(self):
        response = self.client.post("/api/admin/policies", json={
            "document_code": "POL-TEST",
            "title": "테스트",
            "category": "data",
            "status": "published",
            "version": "V.01.0",
            "body_markdown": "# 테스트",
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn("게시 작업", response.get_json()["message"])

    def test_update_cannot_change_status_without_audited_action(self):
        conn = MagicMock()
        conn.cursor.return_value.fetchone.return_value = {
            "id": 11,
            "document_code": "POL-TEST",
            "title": "테스트",
            "category": "data",
            "status": "draft",
            "version": "V.01.0",
            "body_markdown": "# 테스트",
            "effective_date": None,
        }
        with patch.object(application, "get_conn", return_value=conn):
            response = self.client.put("/api/admin/policies/11", json={"status": "published"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("게시 또는 보관", response.get_json()["message"])
        conn.rollback.assert_called_once()


class PolicyBundleIdentityTests(unittest.TestCase):
    def test_generated_release_identity_matches_markdown(self):
        md = bundle.SOURCE.read_text(encoding="utf-8")
        version, effective_date = bundle.release_identity(md)
        self.assertEqual(version, "V.01.1.1")
        self.assertEqual(effective_date, "2026-09-07")
        html = (bundle.EXPORTS / f"{bundle.BASE}.html").read_text(encoding="utf-8")
        self.assertIn(f"<title>홈앤스테이 종합매뉴얼 {version}</title>", html)

    def test_admin_ui_keeps_status_read_only(self):
        source = Path("static/admin.html").read_text(encoding="utf-8")
        self.assertIn('name="status" class="member-edit-input" value="draft" readonly', source)
        self.assertIn("상태 변경은 게시 또는 보관 작업", Path("app.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()