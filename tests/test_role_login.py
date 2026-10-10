"""Real development-DB checks for shared credentials and explicit broker entry."""
import os
import unittest
import uuid
from unittest.mock import patch

os.environ["DISABLE_EXTERNAL_NOTIFICATIONS"] = "1"
os.environ["SKIP_APP_BOOT_TASKS"] = "1"
os.environ["SKIP_STARTUP_SCHEMA_INIT"] = "1"
import db
with patch.object(db, "init_db"):
    import app as web
from scripts.unify_approved_brokers import unify
from werkzeug.security import generate_password_hash, check_password_hash


class RoleLoginTests(unittest.TestCase):
    def setUp(self):
        self.rate_patch = patch.object(web.limiter, "enabled", False)
        self.rate_patch.start()
        self.addCleanup(self.rate_patch.stop)
        self.conn = db.get_conn()
        self.cur = self.conn.cursor()
        self.suffix = uuid.uuid4().hex[:12]
        self.ids = []
        self.emails = []
        self.cur.execute("SELECT value FROM app_meta WHERE key='account_broker_unification'")
        self.previous_audit = self.cur.fetchone()
        self.primary = " primary-pass-123 "
        self.old = "legacy-pass-456"
        self.client = web.app.test_client()
        self.email = self.new_user("email", self.primary)
        self.social = self.new_user("kakao", None)
        self.new_email = f"new-{self.suffix}@example.test"
        self.emails.append(self.new_email)
        for email in (self.email, self.social, self.new_email):
            self.add_agent(email)
        self.conn.commit()

    def new_user(self, provider, password):
        email = f"{provider}-{self.suffix}@example.test"
        self.emails.append(email)
        self.cur.execute("""INSERT INTO users(email,name,provider,status,password_hash,kakao_id)
            VALUES (%s,'역할 검사',%s,'active',%s,%s)""",
            (email, provider, generate_password_hash(password) if password else None,
             self.suffix if provider == "kakao" else None))
        return email

    def add_agent(self, email):
        self.cur.execute("""INSERT INTO agents
            (email,office_name,owner_name,reg_number,status,password_hash)
            VALUES (%s,'검사 사무소','검사 대표',%s,'approved',%s) RETURNING id""",
            (email, uuid.uuid4().hex, generate_password_hash(self.old)))
        self.ids.append(self.cur.fetchone()["id"])

    def tearDown(self):
        self.conn.rollback()
        self.cur.execute("DELETE FROM account_business_memberships WHERE business_table='agents' AND business_id=ANY(%s)", (self.ids,))
        self.cur.execute("DELETE FROM account_role_memberships WHERE user_id IN (SELECT id FROM users WHERE email=ANY(%s))", (self.emails,))
        self.cur.execute("DELETE FROM agents WHERE id=ANY(%s)", (self.ids,))
        self.cur.execute("DELETE FROM users WHERE email=ANY(%s)", (self.emails,))
        if self.previous_audit:
            self.cur.execute("INSERT INTO app_meta(key,value) VALUES ('account_broker_unification',%s) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value",
                             (self.previous_audit["value"],))
        else:
            self.cur.execute("DELETE FROM app_meta WHERE key='account_broker_unification'")
        self.conn.commit()
        self.cur.close()
        self.conn.close()

    def login(self, email, password, role, endpoint="/api/auth/login"):
        return self.client.post(endpoint, json={"email": email, "password": password, "role": role})

    def test_dry_run_and_explicit_approval(self):
        with self.assertRaises(ValueError):
            unify(self.conn, self.ids, approve_existing=False)
        self.conn.rollback()
        result = unify(self.conn, self.ids, approve_existing=True)
        self.assertFalse(result["applied"])
        self.cur.execute("SELECT COUNT(*) AS n FROM users WHERE email=%s", (self.new_email,))
        self.assertEqual(self.cur.fetchone()["n"], 0)
        self.cur.execute("SELECT COUNT(*) AS n FROM agents WHERE id=ANY(%s) AND password_hash IS NOT NULL", (self.ids,))
        self.assertEqual(self.cur.fetchone()["n"], 3)

    def test_three_accounts_credentials_roles_password_change_and_revocation(self):
        result = unify(self.conn, self.ids, approve_existing=True, apply=True)
        self.assertEqual((result["created_users"], result["existing_users"]), (1, 2))
        again = unify(self.conn, self.ids, approve_existing=True, apply=True)
        self.assertEqual(again["already_linked"], 3)
        self.cur.execute("SELECT provider,kakao_id,password_hash FROM users WHERE email=%s", (self.social,))
        social = self.cur.fetchone()
        self.assertEqual(social["kakao_id"], self.suffix)
        self.assertEqual(social["provider"], "email")
        self.assertTrue(check_password_hash(social["password_hash"], self.old))
        for email, password in ((self.email, self.primary), (self.social, self.old), (self.new_email, self.old)):
            response = self.login(email, password, "agent", "/api/agent/login")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json["redirect"], "/agent/dashboard")
            with self.client.session_transaction() as s:
                self.assertEqual(s["active_role"], "agent")
                self.assertIn(s["agent_id"], self.ids)
            self.assertEqual(self.client.get("/agent/dashboard").status_code, 200)
            self.assertEqual(self.client.get("/api/auth/me").json["active_context"]["business_name"], "검사 사무소")
            response = self.login(email, password, "general")
            self.assertEqual(response.json["redirect"], "/mypage")
            with self.client.session_transaction() as s:
                self.assertEqual(s["active_role"], "general")
                self.assertNotIn("agent_id", s)
            self.assertEqual(self.client.get("/api/agent/me").status_code, 401)
        # Old overlapping broker credential must not become a second login path.
        self.assertEqual(self.login(self.email, self.old, "agent").status_code, 401)
        self.assertEqual(self.login(self.email, self.primary, "bogus").status_code, 401)
        self.login(self.email, self.primary, "agent")
        new_password = "new-shared-password-789"
        response = self.client.put("/api/agent/password",
            json={"current_password": self.primary, "new_password": new_password})
        self.assertEqual(response.status_code, 200)
        for role in ("general", "agent"):
            self.assertEqual(self.login(self.email, new_password, role).status_code, 200)
        self.assertEqual(self.login(self.email, self.primary, "general").status_code, 401)
        self.cur.execute("UPDATE agents SET status='pending' WHERE id=%s", (self.ids[0],))
        self.conn.commit()
        self.assertEqual(self.client.get("/api/agent/me").status_code, 401)
        self.assertEqual(self.login(self.email, new_password, "agent").status_code, 403)
        self.assertEqual(self.client.post("/api/auth/context",
            json={"context_id": f"agent:agents:{self.ids[0]}"}).status_code, 403)
        me = self.client.get("/api/auth/me")
        self.assertEqual(me.json["active_context"]["role"], "general")

    def test_multiple_offices_require_selection_and_foreign_office_denied(self):
        self.add_agent(self.email)
        self.conn.commit()
        unify(self.conn, self.ids, approve_existing=True, apply=True)
        response = self.login(self.email, self.primary, "agent")
        self.assertTrue(response.json["select_context"])
        self.assertEqual(len(response.json["contexts"]), 2)
        with self.client.session_transaction() as s:
            self.assertNotIn("agent_id", s)
        self.assertEqual(self.client.post("/api/auth/context",
            json={"context_id": f"agent:agents:{self.ids[1]}"}).status_code, 403)
        response = self.client.post("/api/auth/context", json={"context_id": response.json["contexts"][1]["id"]})
        self.assertEqual(response.json["redirect"], "/agent/dashboard")
        self.client.post("/api/agent/logout")
        self.assertFalse(self.client.get("/api/auth/me").json["logged_in"])

    def test_unclaimed_office_proves_legacy_password_without_email_merge(self):
        # A future standalone approved broker can transition on first login.
        response = self.login(self.new_email, self.old, "agent")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["redirect"], "/agent/dashboard")
        self.assertEqual(self.login(self.new_email, self.old, "general").status_code, 200)
        self.cur.execute("SELECT password_hash IS NULL AS retired FROM agents WHERE id=%s", (self.ids[2],))
        self.assertTrue(self.cur.fetchone()["retired"])
        # Having the legacy password does not prove ownership of an existing user.
        self.assertEqual(self.login(self.email, self.old, "agent").status_code, 401)
        self.assertEqual(self.login(self.email, self.primary, "agent").status_code, 403)
        self.cur.execute("SELECT COUNT(*) AS n FROM account_business_memberships WHERE business_id=%s AND business_table='agents'", (self.ids[0],))
        self.assertEqual(self.cur.fetchone()["n"], 0)


if __name__ == "__main__":
    unittest.main()
