"""Development-Postgres integration coverage for partner favorites/delivery.

The suite is deliberately refused when DATABASE_URL is the configured
production URL.  It creates only uniquely named rows and removes them in
tearDownClass; no mail or notification code is invoked.
"""

import os
import sys
import unittest
import uuid
from datetime import date, timedelta

import psycopg2
from psycopg2.extras import RealDictCursor

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("SKIP_STARTUP_SCHEMA_INIT", "1")

import app as app_module
import db
import weekly_digest


DEV_DSN = os.environ.get("DATABASE_URL")
PROD_DSN = os.environ.get("PROD_DATABASE_URL")


@unittest.skipUnless(
    DEV_DSN and DEV_DSN != PROD_DSN,
    "development DATABASE_URL is required and must differ from PROD_DATABASE_URL",
)
class PartnerApiIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # This test class is only eligible for a separately configured
        # development URL.  init_db is intentionally never pointed at prod.
        probe = psycopg2.connect(DEV_DSN, connect_timeout=5)
        try:
            if PROD_DSN:
                prod = psycopg2.connect(PROD_DSN, connect_timeout=5)
                try:
                    with probe.cursor() as cur:
                        cur.execute(
                            "SELECT current_database(), inet_server_addr()::text, inet_server_port()"
                        )
                        dev_fingerprint = cur.fetchone()
                    with prod.cursor() as cur:
                        cur.execute(
                            "SELECT current_database(), inet_server_addr()::text, inet_server_port()"
                        )
                        prod_fingerprint = cur.fetchone()
                    if dev_fingerprint == prod_fingerprint:
                        raise unittest.SkipTest("DATABASE_URL resolves to production")
                finally:
                    prod.close()
        finally:
            probe.close()
        db.init_db()
        cls.conn = psycopg2.connect(DEV_DSN)
        cls.conn.autocommit = True
        cls.suffix = uuid.uuid4().hex[:12]
        cls.master_ids = []
        cls.partner_ids = {"agent": [], "operator": [], "loan_consultant": []}
        cls._create_fixtures()

    @classmethod
    def _create_fixtures(cls):
        cur = cls.conn.cursor()
        try:
            def master(name, sgg, umd, jibun):
                cur.execute(
                    """INSERT INTO master_buildings
                       (building_name, road_address, sgg_cd, umd_nm, jibun)
                       VALUES (%s, %s, %s, %s, %s) RETURNING id""",
                    (name, "통합테스트 주소 " + name, sgg, umd, jibun),
                )
                ident = cur.fetchone()[0]
                cls.master_ids.append(ident)
                return ident

            # A/B intentionally share a cadastral location.  C is unique.
            cls.mb_a = master("통합테스트 A " + cls.suffix, "99901", "테스트동", "1-1")
            cls.mb_b = master("통합테스트 B " + cls.suffix, "99901", "테스트동", "1-1")
            cls.mb_c = master("통합테스트 C " + cls.suffix, "99902", "단일동", "2-2")

            for i in range(2):
                cur.execute(
                    """INSERT INTO agents
                       (office_name, owner_name, reg_number, email, status)
                       VALUES (%s, %s, %s, %s, 'approved') RETURNING id""",
                    (f"통합중개{i}-{cls.suffix}", "테스트", f"INT-A-{cls.suffix}-{i}",
                     f"int-agent-{cls.suffix}-{i}@example.test"),
                )
                cls.partner_ids["agent"].append(cur.fetchone()[0])
            for i in range(2):
                cur.execute(
                    """INSERT INTO operators
                       (company_name, owner_name, category, email, status)
                       VALUES (%s, %s, '청소', %s, 'approved') RETURNING id""",
                    (f"통합운영{i}-{cls.suffix}", "테스트",
                     f"int-operator-{cls.suffix}-{i}@example.test"),
                )
                cls.partner_ids["operator"].append(cur.fetchone()[0])
            for i in range(2):
                cur.execute(
                    """INSERT INTO loan_consultants
                       (office_name, owner_name, license_number, email, status)
                       VALUES (%s, %s, %s, %s, 'approved') RETURNING id""",
                    (f"통합상담{i}-{cls.suffix}", "테스트",
                     f"INT-L-{cls.suffix}-{i}",
                     f"int-loan-{cls.suffix}-{i}@example.test"),
                )
                cls.partner_ids["loan_consultant"].append(cur.fetchone()[0])

            # A transaction named A must not be attributed to B. C relies on
            # the unique-location fallback and intentionally has a different name.
            cur.execute(
                """INSERT INTO transactions
                   (building_name, address, sgg_cd, umd_nm, jibun, price,
                    deal_date, transaction_scope, raw_key)
                   VALUES (%s, %s, %s, %s, %s, 100, %s, 'unit', %s)""",
                (f"통합테스트 A {cls.suffix}", "통합테스트 주소 A",
                 "99901", "테스트동", "1-1", date.today().isoformat(),
                 "integration-" + cls.suffix + "-a"),
            )
            cur.execute(
                """INSERT INTO transactions
                   (building_name, address, sgg_cd, umd_nm, jibun, price,
                    deal_date, transaction_scope, raw_key)
                   VALUES (%s, %s, %s, %s, %s, 200, %s, 'unit', %s)""",
                ("거래 원문명", "통합테스트 주소 C", "99902", "단일동", "2-2",
                 date.today().isoformat(), "integration-" + cls.suffix + "-c"),
            )
        finally:
            cur.close()

    @classmethod
    def tearDownClass(cls):
        if not getattr(cls, "conn", None):
            return
        cur = cls.conn.cursor()
        try:
            for table, column in (
                ("agents", "id"), ("operators", "id"),
                ("loan_consultants", "id"),
            ):
                ids = cls.partner_ids.get({
                    "agents": "agent", "operators": "operator",
                    "loan_consultants": "loan_consultant",
                }[table], [])
                if ids:
                    cur.execute(f"DELETE FROM {table} WHERE id=ANY(%s)", (ids,))
            cur.execute(
                "DELETE FROM transactions WHERE raw_key LIKE %s",
                ("integration-" + cls.suffix + "-%",),
            )
            if cls.master_ids:
                cur.execute("DELETE FROM master_buildings WHERE id=ANY(%s)", (cls.master_ids,))
        finally:
            cur.close()
            cls.conn.close()

    def client_for(self, kind, ident):
        client = app_module.app.test_client()
        with client.session_transaction() as sess:
            sess[{
                "agent": "agent_id", "operator": "operator_id",
                "loan_consultant": "loan_consultant_id",
            }[kind]] = ident
        return client

    def test_schema_defaults_checks_indexes_and_delivery_partial_uniqueness(self):
        cur = self.conn.cursor()
        try:
            cur.execute(
                """SELECT table_name, column_default, is_nullable
                   FROM information_schema.columns
                   WHERE table_name IN ('agents','operators','loan_consultants')
                     AND column_name='weekly_unsubscribe_token'"""
            )
            columns = cur.fetchall()
            self.assertEqual(len(columns), 3)
            for _, default, nullable in columns:
                self.assertIn("gen_random_uuid()", default)
                self.assertEqual(nullable, "NO")
            cur.execute(
                """SELECT COUNT(*) FROM pg_constraint
                   WHERE conname='partner_favorites_one_owner'"""
            )
            self.assertEqual(cur.fetchone()[0], 1)
            cur.execute(
                """SELECT indexname, indexdef FROM pg_indexes
                   WHERE tablename='weekly_email_deliveries'
                     AND indexname LIKE 'uq_weekly_email_deliveries_%_week'"""
            )
            delivery_indexes = cur.fetchall()
            self.assertGreaterEqual(len(delivery_indexes), 4)
            self.assertTrue(all("recipient_type" in definition
                                for _, definition in delivery_indexes))
        finally:
            cur.close()

    def test_all_partner_types_authenticated_crud_idor_idempotency_and_consent(self):
        for kind, ids in self.partner_ids.items():
            route = {
                "agent": "/api/agent/favorites",
                "operator": "/api/operator/favorites",
                "loan_consultant": "/api/loan-consultant/favorites",
            }[kind]
            client = self.client_for(kind, ids[0])
            self.assertEqual(client.get(route).status_code, 200)
            first = client.post(route, json={"master_building_id": self.mb_a})
            self.assertEqual(first.status_code, 200)
            self.assertTrue(first.get_json()["weekly_email_enabled"])
            duplicate = client.post(route, json={"master_building_id": self.mb_a})
            self.assertEqual(duplicate.status_code, 200)
            self.assertTrue(duplicate.get_json()["idempotent"])

            other = self.client_for(kind, ids[1])
            self.assertEqual(other.delete(route + f"/{self.mb_a}").status_code, 404)
            self.assertEqual(client.put(
                {"agent": "/api/agent/weekly-email",
                 "operator": "/api/operator/weekly-email",
                 "loan_consultant": "/api/loan-consultant/weekly-email"}[kind],
                json={"enabled": True},
            ).status_code, 200)
            self.assertEqual(client.get(route).get_json()["count"], 1)
            self.assertEqual(client.put(
                {"agent": "/api/agent/weekly-email",
                 "operator": "/api/operator/weekly-email",
                 "loan_consultant": "/api/loan-consultant/weekly-email"}[kind],
                json={"enabled": False},
            ).status_code, 200)
            self.assertEqual(client.delete(route + f"/{self.mb_a}").status_code, 200)

    def test_token_default_and_typed_partner_unsubscribe_mutation(self):
        cur = self.conn.cursor()
        try:
            ident = self.partner_ids["agent"][0]
            cur.execute(
                "SELECT weekly_unsubscribe_token FROM agents WHERE id=%s", (ident,)
            )
            token = str(cur.fetchone()[0])
            cur.execute(
                "UPDATE agents SET weekly_email_enabled=TRUE WHERE id=%s", (ident,)
            )
        finally:
            cur.close()
        response = app_module.app.test_client().get(
            f"/unsubscribe?type=agent&token={token}"
        )
        self.assertEqual(response.status_code, 200)
        cur = self.conn.cursor()
        try:
            cur.execute(
                "SELECT weekly_email_enabled FROM agents WHERE id=%s", (ident,)
            )
            self.assertFalse(cur.fetchone()[0])
        finally:
            cur.close()

    def test_transaction_attribution_rejects_same_location_cross_report(self):
        cur = self.conn.cursor()
        try:
            cur.execute(
                "INSERT INTO partner_favorites (agent_id, master_building_id) VALUES (%s,%s),(%s,%s)",
                (self.partner_ids["agent"][0], self.mb_a,
                 self.partner_ids["agent"][0], self.mb_b),
            )
            digest_cur = self.conn.cursor(cursor_factory=RealDictCursor)
            result = weekly_digest._personalize_partner_recipient(
                digest_cur, {"id": self.partner_ids["agent"][0], "recipient_type": "agent"},
                (date.today() - timedelta(days=7)).isoformat(),
            )
            ids = {deal["building_id"] for deal in result["deals_by_fav"].values()}
            self.assertIn(self.mb_a, ids)
            self.assertNotIn(self.mb_b, ids)
        finally:
            cur.close()
            digest_cur.close()
            cleanup = self.conn.cursor()
            cleanup.execute(
                "DELETE FROM partner_favorites WHERE agent_id=%s",
                (self.partner_ids["agent"][0],),
            )
            cleanup.close()

    def test_transaction_attribution_uses_unique_location_fallback(self):
        cur = self.conn.cursor()
        try:
            cur.execute(
                "INSERT INTO partner_favorites (operator_id, master_building_id) VALUES (%s,%s)",
                (self.partner_ids["operator"][0], self.mb_c),
            )
            digest_cur = self.conn.cursor(cursor_factory=RealDictCursor)
            result = weekly_digest._personalize_partner_recipient(
                digest_cur, {"id": self.partner_ids["operator"][0], "recipient_type": "operator"},
                (date.today() - timedelta(days=7)).isoformat(),
            )
            self.assertIn(
                self.mb_c,
                {deal["building_id"] for deal in result["deals_by_fav"].values()},
            )
        finally:
            cur.close()
            digest_cur.close()
            cleanup = self.conn.cursor()
            cleanup.execute(
                "DELETE FROM partner_favorites WHERE operator_id=%s",
                (self.partner_ids["operator"][0],),
            )
            cleanup.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)