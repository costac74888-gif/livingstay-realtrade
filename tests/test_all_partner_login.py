"""All support categories, loan advisors and lodging operators share users auth."""
import html
import re
import unittest
import uuid
from unittest.mock import patch
from urllib.parse import urlparse, parse_qs
from tests import test_role_login as base

web, unify, generate_password_hash = base.web, base.unify, base.generate_password_hash


class AllPartnerLoginTests(unittest.TestCase):
    login = base.RoleLoginTests.login
    new_user = base.RoleLoginTests.new_user
    add_agent = base.RoleLoginTests.add_agent

    def setUp(self):
        base.RoleLoginTests.setUp(self)
        self.businesses = {"operators": [], "loan_consultants": [], "operator_lodging": []}
        self.audits = {}
        for key in ("account_operator_unification", "account_loan_consultant_unification"):
            self.cur.execute("SELECT value FROM app_meta WHERE key=%s", (key,))
            self.audits[key] = self.cur.fetchone()

    def tearDown(self):
        self.conn.rollback()
        for table, ids in self.businesses.items():
            self.cur.execute("DELETE FROM account_business_memberships WHERE business_table=%s AND business_id=ANY(%s)", (table, ids))
            self.cur.execute(f"DELETE FROM {table} WHERE id=ANY(%s)", (ids,))
        for key, previous in self.audits.items():
            if previous:
                self.cur.execute("INSERT INTO app_meta(key,value) VALUES (%s,%s) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value",
                                 (key, previous["value"]))
            else:
                self.cur.execute("DELETE FROM app_meta WHERE key=%s", (key,))
        self.conn.commit()
        base.RoleLoginTests.tearDown(self)

    def operator(self, email=None, category="위탁"):
        self.cur.execute("""INSERT INTO operators(email,company_name,owner_name,category,status,password_hash)
            VALUES (%s,'지원업체 검사','검사 대표',%s,'approved',%s) RETURNING id""",
            (email or self.email, category, generate_password_hash(self.old)))
        bid = self.cur.fetchone()["id"]
        self.businesses["operators"].append(bid)
        return bid

    def loan(self, email=None):
        self.cur.execute("""INSERT INTO loan_consultants(email,office_name,owner_name,license_number,status,password_hash)
            VALUES (%s,'대출 검사','검사 상담사',%s,'approved',%s) RETURNING id""",
            (email or self.email, uuid.uuid4().hex, generate_password_hash(self.old)))
        bid = self.cur.fetchone()["id"]
        self.businesses["loan_consultants"].append(bid)
        return bid

    def lodging(self):
        self.cur.execute("""INSERT INTO operator_lodging(user_id,biz_name,permit_no,lodging_op_type,status)
            VALUES ((SELECT id FROM users WHERE email=%s),'숙박 검사',%s,'rural','approved') RETURNING id""",
            (self.email, uuid.uuid4().hex))
        bid = self.cur.fetchone()["id"]
        self.businesses["operator_lodging"].append(bid)
        self.cur.execute("""INSERT INTO account_role_memberships(user_id,role,status,legacy_account_id)
            SELECT id,'lodging_operator','active',%s FROM users WHERE email=%s""", (bid,self.email))
        self.cur.execute("""INSERT INTO account_business_memberships(user_id,role,status,business_table,business_id)
            SELECT id,'lodging_operator','active','operator_lodging',%s FROM users WHERE email=%s""", (bid,self.email))
        return bid

    def test_single_role_password_change_logout_and_live_revocation(self):
        op = self.operator()
        lc = self.loan()
        self.lodging()
        self.conn.commit()
        for table in ("operators", "loan_consultants"):
            unify(self.conn,self.businesses[table],True,True,table)
            self.assertEqual(unify(self.conn,self.businesses[table],True,True,table)["already_linked"],1)
        routes = [("operator","/api/operator/login","/operator/dashboard","/api/operator/me","/api/operator/password"),
                  ("loan_consultant","/api/loan-consultant/login","/loan-consultant/dashboard","/api/loan-consultant/me","/api/loan-consultant/password"),
                  ("lodging_operator","/api/auth/login","/lodging-operator/manage","/api/lodging-operator/me",None)]
        password = self.primary
        for role, endpoint, dashboard, me, pw_endpoint in routes:
            response = self.login(self.email,password,role,endpoint)
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.json["redirect"],dashboard)
            self.assertEqual(self.client.get(dashboard).status_code,200)
            self.assertEqual(self.client.get(me).status_code,200)
            if pw_endpoint:
                new = f"changed-{role}-password"
                self.assertEqual(self.client.put(pw_endpoint,json={"current_password":password,"new_password":new}).status_code,200)
                self.assertEqual(self.login(self.email,password,"general").status_code,401)
                password = new
            self.assertEqual(self.login(self.email,password,"general").status_code,200)
            if role != "lodging_operator":
                self.assertEqual(self.client.get(me).status_code,401)
        self.login(self.email,password,"operator")
        self.assertEqual(self.client.get("/api/loan-consultant/me").status_code,401)
        self.cur.execute("UPDATE operators SET status='suspended' WHERE id=%s",(op,))
        self.conn.commit()
        self.assertEqual(self.client.get("/api/operator/me").status_code,401)
        self.assertEqual(self.login(self.email,password,"operator").status_code,403)
        self.assertEqual(self.client.post("/api/auth/context",json={"context_id":f"operator:operators:{op}"}).status_code,403)
        self.login(self.email,password,"loan_consultant")
        self.cur.execute("""UPDATE account_role_memberships SET status='withdrawn'
            WHERE role='loan_consultant' AND user_id=(SELECT id FROM users WHERE email=%s)""",(self.email,))
        self.conn.commit()
        self.assertEqual(self.client.get("/api/loan-consultant/me").status_code,401)
        self.assertEqual(self.login(self.email,password,"loan_consultant").status_code,403)
        contexts = self.client.get("/api/auth/contexts").json["contexts"]
        self.assertFalse(any(c["role"] == "loan_consultant" for c in contexts))
        self.client.post("/api/operator/logout")
        self.assertFalse(self.client.get("/api/auth/me").json["logged_in"])

    def test_all_categories_multiple_roles_ownership_and_one_reset(self):
        for category in ("위탁","청소","세탁","용품","소독","세무","인테리어"):
            self.operator(category=category)
        self.loan()
        self.lodging()
        self.lodging()
        foreign = self.operator(self.new_email)
        self.conn.commit()
        for table in ("operators","loan_consultants"):
            unify(self.conn,self.businesses[table],True,True,table)
        response = self.login(self.email,self.primary,"partner")
        self.assertTrue(response.json["select_context"])
        self.assertEqual(len(response.json["contexts"]),10)
        self.assertEqual({c["role"] for c in response.json["contexts"]},
                         {"operator","loan_consultant","lodging_operator"})
        with self.client.session_transaction() as s:
            self.assertEqual(s["active_role"],"general")
            self.assertNotIn("operator_id",s)
        self.assertEqual(self.client.post("/api/auth/context",
            json={"context_id":f"operator:operators:{foreign}"}).status_code,403)
        lodging_context = next(c for c in response.json["contexts"] if c["role"] == "lodging_operator")
        self.assertEqual(self.client.post("/api/auth/context",
            json={"context_id":lodging_context["id"]}).json["redirect"],"/lodging-operator/manage")
        self.assertTrue(self.login(self.email,self.primary,"lodging_operator").json["select_context"])
        self.assertTrue(self.login(self.email,self.primary,"operator").json["select_context"])
        with patch.object(web,"_queue_password_reset_email") as delivery:
            self.assertEqual(self.client.post("/api/auth/request-password-reset",
                json={"email":self.email}).status_code,200)
            self.assertEqual(delivery.call_count,1)
            markup = delivery.call_args.args[1]
        href = html.unescape(re.search(r'href="([^"]+)"',markup).group(1))
        token = parse_qs(urlparse(href).query)["token"][0]
        new = "one-reset-for-every-partner"
        self.assertEqual(self.client.post("/api/auth/reset-password",json={"token":token,"new_password":new}).status_code,200)
        self.assertEqual(self.client.post("/api/auth/reset-password",json={"token":token,"new_password":new}).status_code,400)
        for role in ("general","operator","loan_consultant","lodging_operator","partner"):
            self.assertEqual(self.login(self.email,new,role).status_code,200)
            self.assertEqual(self.login(self.email,self.primary,role).status_code,401)

    def test_standalone_claim_social_admin_merge_and_existing_user_proof(self):
        self.operator(self.social)
        self.operator(self.new_email)
        self.loan(self.new_email)
        self.conn.commit()
        self.assertEqual(self.login(self.social,self.old,"operator").status_code,401)
        unify(self.conn,self.businesses["operators"],True,True,"operators")
        self.assertEqual(self.login(self.social,self.old,"operator").status_code,200)
        self.cur.execute("SELECT kakao_id IS NOT NULL AS linked FROM users WHERE email=%s",(self.social,))
        self.assertTrue(self.cur.fetchone()["linked"])
        # Loan at an existing user must still be proved via the explicit link flow.
        self.assertEqual(self.login(self.new_email,self.old,"loan_consultant").status_code,403)
        fresh = f"standalone-{self.suffix}@example.test"
        self.emails.append(fresh)
        self.loan(fresh)
        self.conn.commit()
        self.assertEqual(self.login(fresh,self.old,"loan_consultant","/api/loan-consultant/login").status_code,200)
        self.assertEqual(self.login(fresh,self.old,"general").status_code,200)


if __name__ == "__main__":
    unittest.main()
