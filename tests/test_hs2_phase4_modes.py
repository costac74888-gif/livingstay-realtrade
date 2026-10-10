"""Real signed Flask sessions and mode HTTP; source auth is separately DB-tested."""
import unittest
from flask import session
from hs2_modes.fixtures import create_fixture_app, FIXTURE_EMAIL, FIXTURE_PASSWORD
from hs2_modes.api import PREFIX


class ModeContracts(unittest.TestCase):
    def setUp(self):
        self.app = create_fixture_app()
        self.client = self.app.test_client()
        self.token = self.profile()["csrf_token"]

    def profile(self):
        return self.client.get("/hs2/api/mode").get_json()

    def post(self, path, body, token=None):
        return self.client.post("/hs2/api/" + path, json=body,
            headers={"X-HS2-CSRF": self.token if token is None else token})

    def login(self):
        result = self.post("email-login", {"email": FIXTURE_EMAIL, "password": FIXTURE_PASSWORD})
        self.assertEqual(result.status_code, 200)
        self.token = self.profile()["csrf_token"]

    def operator(self, cid="operator:operators:21"):
        result = self.post("mode", {"mode": "operator", "context_id": cid})
        if result.status_code == 200:
            self.token = self.profile()["csrf_token"]
        return result

    def test_anonymous_consumer_available_operator_denied(self):
        p = self.profile()
        self.assertFalse(p["logged_in"])
        self.assertEqual(p["mode"], "consumer")
        self.assertTrue(p["email_entry"])
        self.assertEqual(self.operator().status_code, 401)

    def test_email_entry_actual_password_failure_and_success(self):
        self.assertEqual(self.post("email-login", {"email": FIXTURE_EMAIL, "password": "wrong"}).status_code, 401)
        self.assertFalse(self.profile()["logged_in"])
        self.login()
        self.assertTrue(self.profile()["email_authenticated"])

    def test_multiple_businesses_and_consumer_switch(self):
        self.login()
        self.assertEqual(len(self.profile()["contexts"]), 2)
        self.assertEqual(self.operator().status_code, 200)
        self.assertEqual(self.profile()["context_id"], "operator:operators:21")
        self.assertEqual(self.operator("lodging_operator:operator_lodging:22").status_code, 200)
        self.assertEqual(self.profile()["context_id"], "lodging_operator:operator_lodging:22")
        self.assertEqual(self.post("mode", {"mode": "consumer"}).status_code, 200)
        self.assertEqual(self.profile()["mode"], "consumer")
        self.assertIsNone(self.profile()["context_id"])

    def test_csrf_required_and_rotated_old_token_denied(self):
        self.login()
        old = self.token
        self.assertEqual(self.operator().status_code, 200)
        self.assertNotEqual(old, self.token)
        self.assertEqual(self.post("mode", {"mode": "consumer"}, token=old).status_code, 403)
        self.assertEqual(self.post("logout", {}, token="").status_code, 403)

    def test_target_actor_cannot_be_supplied(self):
        self.login()
        self.assertEqual(self.post("mode", {"mode": "operator", "context_id": "operator:operators:21", "user_id": 102}).status_code, 400)
        self.assertEqual(self.operator("operator:operators:999").status_code, 403)
        self.assertEqual(self.profile()["mode"], "consumer")

    def test_existing_kakao_user_must_prove_email(self):
        with self.client.session_transaction() as s:
            s["user_id"] = 101
        self.token = self.profile()["csrf_token"]
        self.assertEqual(self.operator().status_code, 403)
        self.login()
        self.assertEqual(self.operator().status_code, 200)

    def test_reauthentication_failure_revokes_operator_proof(self):
        self.login()
        self.operator()
        self.assertEqual(self.post("email-login", {"email": FIXTURE_EMAIL, "password": "wrong"}).status_code, 401)
        self.assertEqual(self.profile()["mode"], "consumer")
        self.assertFalse(self.profile()["email_authenticated"])

    def test_membership_revocation_takes_effect_next_request(self):
        self.login()
        self.operator()
        self.app.fixture_contexts[101] = []
        self.assertEqual(self.client.get("/hs2/api/operator-context").status_code, 403)
        self.assertEqual(self.profile()["mode"], "consumer")

    def test_actor_change_invalidates_mode_and_old_csrf(self):
        self.login()
        self.operator()
        with self.client.session_transaction() as s:
            s["user_id"] = 102
        self.assertEqual(self.post("mode", {"mode": "operator", "context_id": "operator:operators:21"}).status_code, 403)
        p = self.profile()
        self.assertEqual(p["contexts"], [])
        self.assertEqual(p["mode"], "consumer")
        self.assertFalse(p["email_authenticated"])

    def test_expiry_and_future_timestamp_fail_closed(self):
        self.login()
        self.operator()
        for timestamp in (0, 99999999999, "invalid"):
            with self.client.session_transaction() as s:
                s[PREFIX + "email_at"] = timestamp
            self.assertEqual(self.client.get("/hs2/api/operator-context").status_code, 403)
            self.assertEqual(self.profile()["mode"], "consumer")

    def test_withdrawn_account_loses_access(self):
        self.login()
        self.operator()
        self.app.fixture_accounts[101]["status"] = "withdrawn"
        self.assertEqual(self.client.get("/hs2/api/operator-context").status_code, 401)
        self.assertFalse(self.profile()["logged_in"])

    def test_logout_preserves_admin_and_clears_member_mode(self):
        self.login()
        self.operator()
        with self.client.session_transaction() as s:
            s.update(admin=True, admin_user_id=71, agent_id=44)
        self.assertEqual(self.post("logout", {}).status_code, 200)
        with self.client.session_transaction() as s:
            self.assertTrue(s["admin"])
            self.assertEqual(s["admin_user_id"], 71)
            self.assertNotIn("user_id", s)
            self.assertNotIn("agent_id", s)
            self.assertNotIn(PREFIX + "context", s)

    def test_request_shape_and_public_dto(self):
        self.login()
        self.assertEqual(self.post("mode", {"mode": "administrator"}).status_code, 400)
        self.assertEqual(self.post("mode", {"mode": "consumer", "context_id": "forged"}).status_code, 400)
        p = self.profile()
        self.assertFalse({"email", "password_hash", "phone", "user_id"} & set(p))
        self.assertFalse({"business_id", "business_table"} & set(p["contexts"][0]))
        response = self.client.get("/hs2/api/mode")
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_actual_login_rate_limit(self):
        for _ in range(5):
            self.assertEqual(self.post("email-login", {"email": FIXTURE_EMAIL, "password": "wrong"}).status_code, 401)
        self.assertEqual(self.post("email-login", {"email": FIXTURE_EMAIL, "password": "wrong"}).status_code, 429)

    def test_page_and_exact_assets_only(self):
        self.assertEqual(self.client.get("/hs2/mode").status_code, 200)
        for file in ("mode.css", "mode.js"):
            self.assertEqual(self.client.get("/hs2/mode-assets/" + file).status_code, 200)
        self.assertEqual(self.client.get("/hs2/mode-assets/../api.py").status_code, 404)

    def test_role_flag_or_admin_session_is_not_member_proof(self):
        with self.client.session_transaction() as s:
            s.update(admin=True, operator_id=21, active_role="operator")
        self.assertFalse(self.profile()["logged_in"])
        self.assertEqual(self.client.get("/hs2/api/operator-context").status_code, 401)
