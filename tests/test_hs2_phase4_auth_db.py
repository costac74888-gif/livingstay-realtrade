"""Execute original login/context/Kakao source against real owned PostgreSQL."""
import unittest
from urllib.parse import urlparse, parse_qs
from flask import Flask, request
from flask_limiter import Limiter
from hs2_data.repository import connect_fixture
from hs2_modes.api import create_blueprint
from hs2_modes.legacy_fixture import seed_accounts, source_auth


class OriginalAuthPostgreSQL(unittest.TestCase):
    def setUp(self):
        self.conn = connect_fixture()
        seed_accounts(self.conn)
        self.source, self.provider = source_auth(self.conn)
        self.app = Flask("original-auth-fixture")
        self.app.secret_key = "synthetic-only"
        self.limiter = Limiter(key_func=lambda: request.remote_addr, app=self.app, storage_uri="memory://")
        self.app.register_blueprint(create_blueprint(
            current_user=self.source["current_user"], get_contexts=self.source["_get_account_contexts"],
            email_login=self._login,
            member_logout=self.source["auth_logout"], limit=self.limiter.limit))
        self.app.add_url_rule("/auth/kakao/start", view_func=self.source["kakao_start"])
        self.app.add_url_rule("/auth/kakao/callback", view_func=self.source["kakao_callback"])
        self.client = self.app.test_client()
        self.token = self.client.get("/hs2/api/mode").get_json()["csrf_token"]

    def tearDown(self):
        self.conn.rollback()
        with self.conn.cursor() as c:
            c.execute("DROP SCHEMA hs2_fixture_auth CASCADE")
        self.conn.commit()
        self.conn.close()

    def _login(self, data):
        response = self.app.make_response(self.source["_unified_role_login"](data, "partner"))
        return response, response.status_code

    def query(self, sql, args=()):
        with self.conn.cursor() as c:
            c.execute(sql, args)
            return c.fetchall()

    def login(self, password="Synthetic-only-123!"):
        result = self.client.post("/hs2/api/email-login",
            json={"email": "business@example.test", "password": password},
            headers={"X-HS2-CSRF": self.token})
        self.token = self.client.get("/hs2/api/mode").get_json()["csrf_token"]
        return result

    def callback(self, *, state=None, code="synthetic-code"):
        started = self.client.get("/auth/kakao/start")
        expected = parse_qs(urlparse(started.location).query)["state"][0]
        return self.client.get("/auth/kakao/callback", query_string={
            "state": state if state is not None else expected, "code": code})

    def test_original_password_login_and_hashed_history(self):
        self.assertEqual(self.login("wrong").status_code, 401)
        self.assertEqual(self.query("SELECT count(*) FROM login_history"), [(0,)])
        self.assertEqual(self.login().status_code, 200)
        self.assertEqual(self.query("SELECT user_id,length(ip_hash) FROM login_history"), [(101, 64)])
        self.assertEqual(self.query("SELECT email FROM users WHERE id=101"), [("business@example.test",)])

    def test_real_memberships_multi_business_revocation(self):
        self.assertEqual(self.login().status_code, 200)
        p = self.client.get("/hs2/api/mode").get_json()
        self.assertEqual([c["id"] for c in p["contexts"]], ["operator:operators:21", "operator:operators:22"])
        response = self.client.post("/hs2/api/mode", json={"mode": "operator", "context_id": p["contexts"][1]["id"]},
            headers={"X-HS2-CSRF": self.token})
        self.assertEqual(response.status_code, 200)
        with self.conn.cursor() as c:
            c.execute("UPDATE operators SET status='pending' WHERE id=22")
        self.conn.commit()
        self.assertEqual(self.client.get("/hs2/api/operator-context").status_code, 403)
        self.assertEqual(self.client.get("/hs2/api/mode").get_json()["mode"], "consumer")

    def test_pending_and_other_actor_businesses_denied(self):
        with self.conn.cursor() as c:
            c.execute("UPDATE account_business_memberships SET status='inactive'")
        self.conn.commit()
        self.assertEqual(self.login().status_code, 403)
        self.assertEqual(self.query("SELECT count(*) FROM login_history"), [(0,)])

    def test_actual_kakao_subject_logs_same_id_and_does_not_email_merge(self):
        self.callback()
        with self.client.session_transaction() as s:
            self.assertEqual(s["user_id"], 102)
        self.assertEqual(self.query("SELECT count(*) FROM users"), [(3,)])
        self.assertEqual(self.query("SELECT user_id FROM login_history"), [(102,)])

    def test_new_subject_collision_creates_separate_identity_not_existing_email(self):
        before = self.query("SELECT id,email,name,password_hash FROM users WHERE id=101")
        self.provider.subject = "fixture-new-subject"
        self.callback()
        created = self.query("SELECT id,email FROM users WHERE kakao_id='fixture-new-subject'")
        self.assertEqual(created, [(1001, None)])
        self.assertEqual(self.query("SELECT id,email,name,password_hash FROM users WHERE id=101"), before)
        with self.client.session_transaction() as s:
            self.assertEqual(s["user_id"], 1001)

    def test_wrong_state_missing_code_provider_error_never_login(self):
        for which in ("state", "code", "provider"):
            self.provider.broken = which == "provider"
            result = self.callback(state="forged" if which == "state" else None,
                                   code="" if which == "code" else "synthetic-code")
            self.assertIn("login_error=1", result.location)
            with self.client.session_transaction() as s:
                self.assertNotIn("user_id", s)
        self.assertEqual(self.query("SELECT count(*) FROM login_history"), [(0,)])

    def test_callback_replay_and_withdrawn_account_blocked(self):
        start = self.client.get("/auth/kakao/start")
        token = parse_qs(urlparse(start.location).query)["state"][0]
        path = "/auth/kakao/callback?state=" + token + "&code=synthetic-code"
        self.client.get(path)
        self.assertIn("login_error=1", self.client.get(path).location)
        self.provider.subject = "fixture-withdrawn"
        self.assertIn("login_error=1", self.callback().location)
        self.assertEqual(self.query("SELECT status FROM users WHERE id=103"), [("withdrawn",)])

    def test_existing_history_and_memberships_survive_mode_and_logout(self):
        before = self.query("SELECT * FROM account_business_memberships ORDER BY business_id")
        self.login()
        with self.client.session_transaction() as s:
            s["admin"] = True
        self.assertEqual(self.client.post("/hs2/api/logout", json={},
            headers={"X-HS2-CSRF": self.token}).status_code, 200)
        self.assertEqual(self.query("SELECT * FROM account_business_memberships ORDER BY business_id"), before)
        self.assertEqual(self.query("SELECT count(*) FROM login_history"), [(1,)])
        with self.client.session_transaction() as s:
            self.assertNotIn("user_id", s)
            self.assertTrue(s["admin"])
