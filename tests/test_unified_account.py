"""Contract checks for the users-centred account membership model."""
import os
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
os.environ["DISABLE_EXTERNAL_NOTIFICATIONS"] = "1"
os.environ.setdefault("FLASK_SECRET_KEY", "unified-account-test-secret")
import db  # noqa: E402
with patch.object(db, "init_db"):
    import app as app_module  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402


class UnifiedAccountContractTests(unittest.TestCase):
    def test_schema_memberships_and_idempotent_linking(self):
        source = (ROOT / "db.py").read_text(encoding="utf-8")
        for marker in (
            "CREATE TABLE IF NOT EXISTS account_role_memberships",
            "CREATE TABLE IF NOT EXISTS account_business_memberships",
            "UNIQUE (user_id, role, legacy_account_id)",
            "UNIQUE (user_id, role, business_table, business_id)",
            "Existing partner rows are not",
        ):
            self.assertIn(marker, source)
        self.assertGreater(db.SCHEMA_VERSION, "2026-09-09-13")

    def test_context_and_reauthentication_routes(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        for marker in (
            '@app.route("/api/auth/contexts")',
            '@app.route("/api/auth/context", methods=["POST", "PUT"])',
            '@app.route("/api/auth/reauthenticate", methods=["POST"])',
            '@app.route("/api/auth/link-legacy-role", methods=["POST"])',
            'session["active_role"] = role',
            'session["active_business_id"] = business_id',
            "def _require_account_reauth",
            "def _get_account_contexts",
            "status='active'",
            '"agent_id"',
            "check_password_hash(row[\"password_hash\"], legacy_password)",
            "SET password_hash=NULL",
            "def _legacy_business_session_allowed",
        ):
            self.assertIn(marker, source)

    def test_sensitive_operations_and_single_reset_token(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        email_start = source.index("requested_email =")
        email_end = source.index("name = (data.get(", email_start)
        self.assertIn("_require_account_reauth", source[email_start:email_end])
        withdrawal_start = source.index("def auth_withdraw")
        withdrawal_end = source.index("# ---- 카카오", withdrawal_start)
        withdrawal = source[withdrawal_start:withdrawal_end]
        self.assertIn("account_role_memberships", withdrawal)
        self.assertIn("account_business_memberships", withdrawal)
        self.assertIn("_require_account_reauth", withdrawal)
        self.assertIn('session.pop("agent_id"', withdrawal)
        reset_start = source.index("def auth_request_password_reset")
        reset_end = source.index('@app.route("/api/auth/signup"', reset_start)
        reset = source[reset_start:reset_end]
        self.assertIn("if not accounts:", reset)
        self.assertEqual(reset.count("FROM users WHERE LOWER(email) = %s"), 1)

    def test_legacy_login_fallback_is_retained(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        login_start = source.index("def auth_login")
        login_end = source.index('@app.route("/api/auth/logout"', login_start)
        login = source[login_start:login_end]
        self.assertIn('("agents",', login)
        self.assertIn('("operators",', login)
        self.assertIn('("loan_consultants",', login)


class UnifiedAccountIntegrationTests(unittest.TestCase):
    """Exercise the account boundary against the development PostgreSQL schema."""

    def test_lodging_business_switch_scopes_profile_and_photo_changes(self):
        suffix = uuid.uuid4().hex[:12]
        email = f"lodging-context-{suffix}@example.test"
        conn = db.get_conn()
        cur = conn.cursor()
        user_id = None
        lodging_ids = []
        client = app_module.app.test_client()
        try:
            cur.execute(
                """INSERT INTO users
                   (email, password_hash, name, provider, status)
                   VALUES (%s, %s, '숙박 컨텍스트 테스트', 'email', 'active')
                   RETURNING id""",
                (email, generate_password_hash(f"Lodging-{suffix}-pw")),
            )
            user_id = cur.fetchone()["id"]
            for number in (1, 2):
                cur.execute(
                    """INSERT INTO operator_lodging
                       (user_id, lodging_op_type, biz_name, permit_no, status,
                        intro_text, photo_url)
                       VALUES (%s, 'rural', %s, %s, 'approved', %s, %s)
                       RETURNING id""",
                    (
                        user_id,
                        f"숙박 컨텍스트 사업장 {number}",
                        f"lodging-context-{suffix}-{number}",
                        f"기존 소개 {number}",
                        f"operator/photo/context-{suffix}-{number}.jpg",
                    ),
                )
                lodging_ids.append(cur.fetchone()["id"])
            cur.execute(
                """INSERT INTO account_role_memberships
                   (user_id, role, legacy_account_id, status)
                   VALUES (%s, 'lodging_operator', %s, 'active')""",
                (user_id, lodging_ids[0]),
            )
            for lodging_id in lodging_ids:
                cur.execute(
                    """INSERT INTO account_business_memberships
                       (user_id, role, business_table, business_id, status)
                       VALUES (%s, 'lodging_operator', 'operator_lodging',
                               %s, 'active')""",
                    (user_id, lodging_id),
                )
            conn.commit()

            with client.session_transaction() as test_session:
                test_session["user_id"] = user_id

            # 복수 사업장이면 선택 전 임의 사업장을 노출하지 않는다.
            self.assertEqual(client.get("/api/lodging-operator/me").status_code, 401)
            contexts = client.get("/api/auth/contexts").get_json()["contexts"]
            lodging_contexts = [
                item for item in contexts if item["role"] == "lodging_operator"
            ]
            self.assertEqual(len(lodging_contexts), 2)
            self.assertTrue(all(
                item["dashboard_url"] == "/lodging-operator/manage"
                for item in lodging_contexts
            ))

            first_context = next(
                item for item in lodging_contexts
                if item["business_id"] == lodging_ids[0]
            )
            switched = client.post(
                "/api/auth/context", json={"context_id": first_context["id"]}
            )
            self.assertEqual(switched.status_code, 200, switched.get_json())
            self.assertEqual(
                switched.get_json()["redirect"], "/lodging-operator/manage"
            )
            first_profile = client.get("/api/lodging-operator/me")
            self.assertEqual(first_profile.status_code, 200, first_profile.get_json())
            self.assertEqual(first_profile.get_json()["item"]["id"], lodging_ids[0])

            updated = client.put(
                "/api/lodging-operator/me",
                json={
                    "intro_text": "첫 번째 사업장만 변경",
                    "amenities": [],
                    "badges": [],
                },
            )
            self.assertEqual(updated.status_code, 200, updated.get_json())
            deleted_photo = client.delete("/api/lodging-operator/photo")
            self.assertEqual(
                deleted_photo.status_code, 200, deleted_photo.get_json()
            )

            second_context = next(
                item for item in lodging_contexts
                if item["business_id"] == lodging_ids[1]
            )
            switched = client.post(
                "/api/auth/context", json={"context_id": second_context["id"]}
            )
            self.assertEqual(switched.status_code, 200, switched.get_json())
            second_profile = client.get("/api/lodging-operator/me")
            self.assertEqual(second_profile.status_code, 200, second_profile.get_json())
            self.assertEqual(second_profile.get_json()["item"]["id"], lodging_ids[1])
            self.assertEqual(
                second_profile.get_json()["item"]["intro_text"], "기존 소개 2"
            )

            cur.execute(
                """SELECT id, intro_text, photo_url
                     FROM operator_lodging
                    WHERE id = ANY(%s)
                    ORDER BY id""",
                (lodging_ids,),
            )
            rows = {row["id"]: row for row in cur.fetchall()}
            self.assertEqual(rows[lodging_ids[0]]["intro_text"], "첫 번째 사업장만 변경")
            self.assertIsNone(rows[lodging_ids[0]]["photo_url"])
            self.assertEqual(rows[lodging_ids[1]]["intro_text"], "기존 소개 2")
            self.assertEqual(
                rows[lodging_ids[1]]["photo_url"],
                f"operator/photo/context-{suffix}-2.jpg",
            )
        finally:
            conn.rollback()
            if user_id is not None:
                cur.execute(
                    "DELETE FROM account_business_memberships WHERE user_id=%s",
                    (user_id,),
                )
                cur.execute(
                    "DELETE FROM account_role_memberships WHERE user_id=%s",
                    (user_id,),
                )
            if lodging_ids:
                cur.execute(
                    "DELETE FROM operator_lodging WHERE id = ANY(%s)",
                    (lodging_ids,),
                )
            if user_id is not None:
                cur.execute("DELETE FROM users WHERE id=%s", (user_id,))
            conn.commit()
            cur.close()
            conn.close()

    def test_claim_switch_settings_and_withdrawal(self):
        suffix = uuid.uuid4().hex[:12]
        email = f"unified-{suffix}@example.test"
        renamed_email = f"unified-renamed-{suffix}@example.test"
        current_password = f"Current-{suffix}-pw"
        legacy_passwords = [f"Legacy-{suffix}-{i}" for i in (1, 2)]
        conn = db.get_conn()
        cur = conn.cursor()
        user_id = None
        agent_ids = []
        unowned_id = None
        client = app_module.app.test_client()
        try:
            cur.execute(
                """INSERT INTO users
                   (email, password_hash, name, provider, status,
                    weekly_email_enabled, email_alert_enabled)
                   VALUES (%s, %s, '통합 테스트', 'email', 'active', TRUE, TRUE)
                   RETURNING id""",
                (email, generate_password_hash(current_password)),
            )
            user_id = cur.fetchone()["id"]
            for number, password in enumerate(legacy_passwords, 1):
                cur.execute(
                    """INSERT INTO agents
                       (office_name, owner_name, reg_number, email, status,
                        password_hash)
                       VALUES (%s, '테스트 대표', %s, %s, 'approved', %s)
                       RETURNING id""",
                    (
                        f"통합 테스트 사무소 {number}",
                        f"unified-reg-{suffix}-{number}",
                        email,
                        generate_password_hash(password),
                    ),
                )
                agent_ids.append(cur.fetchone()["id"])
            cur.execute(
                """INSERT INTO agents
                   (office_name, owner_name, reg_number, email, status,
                    password_hash)
                   VALUES ('타인 사무소', '타인 대표', %s, %s, 'approved', %s)
                   RETURNING id""",
                (
                    f"unified-unowned-{suffix}",
                    f"other-{suffix}@example.test",
                    generate_password_hash("Other-password"),
                ),
            )
            unowned_id = cur.fetchone()["id"]
            conn.commit()

            with client.session_transaction() as session:
                session["user_id"] = user_id

            for password in legacy_passwords:
                response = client.post(
                    "/api/auth/link-legacy-role",
                    json={
                        "role": "agent",
                        "current_password": current_password,
                        "legacy_password": password,
                    },
                )
                self.assertEqual(response.status_code, 200, response.get_json())
                self.assertTrue(response.get_json()["ok"])
            cur.execute(
                "SELECT id, password_hash FROM agents WHERE id = ANY(%s)",
                (agent_ids,),
            )
            migrated_agents = cur.fetchall()
            self.assertEqual({row["id"] for row in migrated_agents}, set(agent_ids))
            self.assertTrue(all(row["password_hash"] is None for row in migrated_agents))

            contexts_response = client.get("/api/auth/contexts")
            self.assertEqual(contexts_response.status_code, 200)
            contexts = contexts_response.get_json()["contexts"]
            self.assertEqual(len(contexts), 3)  # general + two agent businesses
            business_contexts = [
                item for item in contexts if item["role"] == "agent"
            ]
            self.assertEqual(
                {item["business_id"] for item in business_contexts},
                set(agent_ids),
            )

            second_context = next(
                item for item in business_contexts
                if item["business_id"] == agent_ids[1]
            )
            switched = client.post(
                "/api/auth/context",
                json={"context_id": second_context["id"]},
            )
            self.assertEqual(switched.status_code, 200, switched.get_json())
            self.assertEqual(switched.get_json()["business_id"], agent_ids[1])
            with client.session_transaction() as session:
                self.assertEqual(session["agent_id"], agent_ids[1])
                self.assertEqual(session["active_role"], "agent")

            denied = client.post(
                "/api/auth/context",
                json={
                    "role": "agent",
                    "business_table": "agents",
                    "business_id": unowned_id,
                },
            )
            self.assertEqual(denied.status_code, 403)

            weekly = client.put(
                "/api/auth/weekly-email", json={"enabled": False}
            )
            self.assertEqual(weekly.status_code, 200, weekly.get_json())
            self.assertFalse(weekly.get_json()["weekly_email_enabled"])
            email_change = client.put(
                "/api/auth/me",
                json={"email": renamed_email, "current_password": current_password},
            )
            self.assertEqual(email_change.status_code, 200, email_change.get_json())
            self.assertEqual(email_change.get_json()["email"], renamed_email)
            me = client.get("/api/auth/me").get_json()
            self.assertEqual(me["email"], renamed_email)
            self.assertFalse(me["weekly_email_enabled"])
            self.assertEqual(len(me["contexts"]), 3)

            withdrawn = client.delete(
                "/api/auth/me", json={"current_password": current_password}
            )
            self.assertEqual(withdrawn.status_code, 200, withdrawn.get_json())
            self.assertTrue(withdrawn.get_json()["ok"])
            with client.session_transaction() as session:
                self.assertNotIn("user_id", session)
                self.assertNotIn("agent_id", session)
                session["agent_id"] = agent_ids[1]
            stale_partner_session = client.get("/api/agent/me")
            self.assertEqual(stale_partner_session.status_code, 401)
            with client.session_transaction() as session:
                self.assertNotIn("agent_id", session)

            cur.execute(
                """SELECT status FROM account_role_memberships
                   WHERE user_id=%s""",
                (user_id,),
            )
            self.assertTrue(all(row["status"] == "withdrawn" for row in cur.fetchall()))
            cur.execute(
                """SELECT status FROM account_business_memberships
                   WHERE user_id=%s""",
                (user_id,),
            )
            self.assertTrue(all(row["status"] == "withdrawn" for row in cur.fetchall()))
        finally:
            # Memberships are user-owned and normally cascade, but explicit
            # cleanup keeps this test safe if a DB constraint changes.
            if user_id is not None:
                cur.execute(
                    "DELETE FROM account_business_memberships WHERE user_id=%s",
                    (user_id,),
                )
                cur.execute(
                    "DELETE FROM account_role_memberships WHERE user_id=%s",
                    (user_id,),
                )
                cur.execute("DELETE FROM users WHERE id=%s", (user_id,))
            if agent_ids or unowned_id is not None:
                cur.execute(
                    "DELETE FROM agents WHERE id = ANY(%s)",
                    (agent_ids + ([unowned_id] if unowned_id is not None else []),),
                )
            conn.commit()
            cur.close()
            conn.close()


if __name__ == "__main__":
    unittest.main()