"""Owned preview routing/security checks; no external services or production DB."""
import json
import unittest
from pathlib import Path
from werkzeug.security import generate_password_hash
from flask import Flask
from unittest.mock import patch
from scripts.hs2_preview_admin_auth import install as install_auth
from scripts.hs2_design_shell import install as install_design


class DesignIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        # Auth/routing tests have no DB adapter. The real owned precondition is
        # separately exercised by the production-boundary tests.
        with patch("scripts.hs2_preview_admin_auth.require_owned"), patch.dict(
                "os.environ", {"HS2_PREVIEW_ADMIN_PASSWORD": ""}):
            install_auth(self.app)
        # Only needed by the normal details landing-page redirect.
        self.app.fixture_demo_catalog = {}
        with patch("scripts.hs2_design_shell.require_owned"):
            install_design(self.app)
        self.app.add_url_rule("/hs2/admin/", "private_root", lambda: "<html><head></head><body>private</body></html>")
        self.app.add_url_rule("/hs2/listings/admin", "private_listings", lambda: "private")
        self.client = self.app.test_client()
        self.registry = json.loads((Path(__file__).resolve().parents[1] /
                                    "scripts/hs2_design_registry.json").read_text())

    def test_registry_separates_pages_tabs_popups_states_aliases(self):
        screens = self.registry["screens"]
        self.assertEqual(len(screens), 246)
        self.assertEqual(len({s["id"] for s in screens}), 246)
        self.assertEqual(sum(s["kind"] == "page" for s in screens), 119)
        self.assertEqual(sum(s["kind"] == "tab" for s in screens), 70)
        self.assertEqual(sum(s["kind"] == "popup" for s in screens), 46)
        self.assertEqual(sum(s["kind"] == "state" for s in screens), 11)
        paths = [s["preview_path"] for s in screens if not s["native"] and not s["alias_of"]]
        self.assertEqual(len(paths), len(set(paths)))

    def test_new_public_pages_have_real_routes_and_no_gallery(self):
        for screen in self.registry["screens"]:
            if screen["native"] or screen["alias_of"] or screen["role"] == "관리자":
                continue
            with self.subTest(screen=screen["id"]):
                r = self.client.get(screen["preview_path"])
                self.assertEqual(r.status_code, 200)
                self.assertIn(b'hs-design-page', r.data)
                self.assertIn(b'hs-live-header', r.data)
                self.assertNotIn(b'hs2-complete/Catalog', r.data)

    def test_all_administrator_ui_routes_are_server_protected(self):
        for s in self.registry["screens"]:
            if s["role"] != "관리자" or s["id"] == "A001" or s["alias_of"] == "A001":
                continue
            with self.subTest(screen=s["id"]):
                self.assertEqual(self.client.get(s["preview_path"]).status_code, 403)
        with self.client.session_transaction() as session:
            session["fixture_admin"] = True
        self.assertEqual(self.client.get("/hs2/admin/pages/policy-admin-a012/").status_code, 403)

    def test_verified_owned_login_new_page_and_logout(self):
        self.app.config["HS2_PREVIEW_ADMIN_HASH"] = generate_password_hash("owned-fixture-password-only")
        self.client.get("/hs2/admin/login")
        with self.client.session_transaction() as s:
            csrf = s["hs2_admin_login_csrf"]
        r = self.client.post("/hs2/admin/login", json={
            "username":"preview-admin","password":"owned-fixture-password-only","csrf":csrf})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.get("/hs2/admin/pages/policy-admin-a012/").status_code, 200)
        with self.client.session_transaction() as s:
            csrf = s["fixture_csrf"]
        self.assertEqual(self.client.post("/hs2/admin/logout", headers={"X-HS2-CSRF":csrf}).status_code, 200)
        self.assertEqual(self.client.get("/hs2/admin/pages/policy-admin-a012/").status_code, 403)

    def test_no_permission_grant_on_design_navigation(self):
        r = self.client.get("/hs2/stays/profile-c023/?screen=A012")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.client.get(r.headers["Location"]).status_code, 403)

    def test_images_are_served_by_the_running_app_not_canvas_router(self):
        response = self.client.get("/hs2/design-images/hs2-unified/interior-1.jpg")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "image/jpeg")
        response.close()
        self.assertEqual(self.client.get("/hs2/design-images/private/interior-1.jpg").status_code, 404)

    def test_owner_navigation_preserves_operator_scope_and_old_urls(self):
        for path in ("/hs2/bookings/", "/hs2/workspace/"):
            response = self.client.get(path + "?view=owner&booking_id=owned-test")
            self.assertEqual(response.status_code, 302)
            self.assertIn("view=operator", response.headers["Location"])
            self.assertIn("booking_id=owned-test", response.headers["Location"])

    def test_preview_exports_are_server_protected(self):
        self.assertEqual(self.client.get(
            "/hs2/admin/preview-exports/homenstay-running-preview-captures.zip").status_code, 403)


if __name__ == "__main__":
    unittest.main()
