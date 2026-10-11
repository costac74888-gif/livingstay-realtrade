"""Pure auth tests: no database, real credentials or operational authority."""
import re
import unittest
from unittest.mock import patch
from flask import Flask
from werkzeug.security import generate_password_hash
from scripts.hs2_preview_admin_auth import install


class PreviewAdminAuth(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        # The owned DB prerequisite is tested by the existing boundary suite;
        # these cases exercise only authentication, with no DB adapter at all.
        with patch("scripts.hs2_preview_admin_auth.require_owned"), patch.dict(
                "os.environ", {"HS2_PREVIEW_ADMIN_PASSWORD": ""}):
            install(self.app)
        self.app.add_url_rule("/hs2/admin/", "private", lambda: "private")
        self.client = self.app.test_client()
        self.password = "synthetic-auth-fixture-only"

    def login(self, password=None, csrf=None, username="preview-admin"):
        page = self.client.get("/hs2/admin/login").get_data(as_text=True)
        token = re.search(r'name="csrf" type="hidden" value="([^"]+)"', page)[1]
        return self.client.post("/hs2/admin/login", json={
            "username": username, "password": password or self.password, "csrf": csrf or token})

    def test_no_configuration_or_public_role_bypass(self):
        self.assertEqual(self.client.get("/hs2/admin/").status_code, 403)
        self.assertEqual(self.login().status_code, 503)
        for path in ("/hs2/listings-fixture/identity", "/__development__/seongsu/admin-role"):
            self.assertEqual(self.client.post(path, json={"admin": True}).status_code, 403)
        with self.client.session_transaction() as session:
            session["fixture_admin"] = True
        self.assertEqual(self.client.get("/hs2/admin/").status_code, 403)

    def test_correct_login_private_route_and_logout(self):
        self.app.config["HS2_PREVIEW_ADMIN_HASH"] = generate_password_hash(self.password)
        self.assertEqual(self.login().status_code, 200)
        self.assertEqual(self.client.get("/hs2/admin/").status_code, 200)
        with self.client.session_transaction() as session:
            csrf = session["fixture_csrf"]
        self.assertEqual(self.client.post("/hs2/admin/logout").status_code, 403)
        self.assertEqual(self.client.post("/hs2/admin/logout",
                         headers={"X-HS2-CSRF": csrf}).status_code, 200)
        self.assertEqual(self.client.get("/hs2/admin/").status_code, 403)

    def test_wrong_credentials_unicode_csrf_and_rate_limit(self):
        self.app.config["HS2_PREVIEW_ADMIN_HASH"] = generate_password_hash(self.password)
        self.assertEqual(self.login(csrf="비정상").status_code, 403)
        for _ in range(5):
            self.assertEqual(self.login(password="wrong").status_code, 401)
        self.assertEqual(self.login().status_code, 429)

    def test_expiration_denies_private_access(self):
        self.app.config["HS2_PREVIEW_ADMIN_HASH"] = generate_password_hash(self.password)
        self.assertEqual(self.login().status_code, 200)
        with self.client.session_transaction() as session:
            session["hs2_admin_login_at"] -= 8 * 3600 + 1
        self.assertEqual(self.client.get("/hs2/admin/").status_code, 403)
