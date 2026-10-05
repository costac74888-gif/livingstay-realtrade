"""Real SQL, rollback-only financial/entitlement/quota checks; no external notices."""
import os
os.environ["DISABLE_EXTERNAL_NOTIFICATIONS"] = "1"

import unittest
import uuid
from datetime import datetime
from unittest.mock import patch

import app as application
import membership_common as common
from db import get_conn


class Borrowed:
    def __init__(self, conn):
        self.conn = conn
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def cursor(self):
        return self.conn.cursor()
    def close(self):
        pass


class BankMembership(unittest.TestCase):
    def setUp(self):
        application.limiter.reset()
        self.conn = get_conn()
        self.addCleanup(self.conn.close)
        self.addCleanup(self.conn.rollback)
        borrowed = Borrowed(self.conn)
        for module in (application, common):
            mocked = patch.object(module, "get_conn", return_value=borrowed)
            mocked.start()
            self.addCleanup(mocked.stop)
        with self.conn.cursor() as cur:
            self.users = []
            for _ in range(2):
                cur.execute("INSERT INTO users(email,name) VALUES(%s,'자동검증') RETURNING id",
                            [uuid.uuid4().hex + "@example.invalid"])
                self.users.append(cur.fetchone()["id"])
            cur.execute("SELECT id FROM master_buildings ORDER BY id LIMIT 1")
            self.building = cur.fetchone()["id"]
            cur.execute("SELECT id FROM auction_items WHERE usage_name NOT LIKE '%오피스텔%' ORDER BY id LIMIT 1")
            self.auction = cur.fetchone()["id"]
        self.client = application.app.test_client()
        self.client.environ_base["HTTP_USER_AGENT"] = "Mozilla/5.0 BankMembershipTest"
        self.client.environ_base["HTTP_X_FORWARDED_FOR"] = "203.0.113.175"
        self.login()

    def login(self, user=None, admin=False):
        with self.client.session_transaction() as s:
            s.clear()
            if admin:
                s["admin"] = True
                s["admin_user_id"] = 1
            elif user is not False:
                s["user_id"] = user or self.users[0]

    def apply(self, **extra):
        return self.client.post("/api/membership/payments", json={
            "depositor_name": "자동검증", "request_token": uuid.uuid4().hex,
            "agree_terms": True, **extra})

    def admin_status(self, payment_id, status, note=""):
        self.login(admin=True)
        return self.client.post(f"/api/admin/membership/payments/{payment_id}/status",
                                json={"status": status, "note": note})

    def activate(self):
        self.login()
        payment = self.apply().get_json()["payment"]
        result = self.admin_status(payment["id"], "approved")
        self.assertEqual(result.status_code, 200)
        self.login()
        return payment

    def check(self, **extra):
        return self.client.post("/api/membership/checks", json={
            "building_id": self.building, "request_token": uuid.uuid4().hex,
            "memo": "", "agree_terms": True, **extra})

    def test_guest_cannot_request_or_see_bank_and_reports(self):
        self.login(user=False)
        me = self.client.get("/api/membership/me").get_json()
        self.assertFalse(me["logged_in"])
        self.assertIsNone(me["bank"])
        self.assertEqual(me["payments"], [])
        self.assertEqual(self.apply().status_code, 401)
        self.assertEqual(self.check().status_code, 401)
        self.assertEqual(self.client.get("/api/admin/membership/requests").status_code, 401)

    def test_pending_does_not_unlock_and_server_sets_amount(self):
        result = self.apply(amount=1, status="approved", visit_fee=1)
        self.assertEqual(result.status_code, 201)
        payment = result.get_json()["payment"]
        self.assertEqual(payment["amount"], 29000)
        self.assertEqual(payment["status"], "pending")
        self.assertEqual(set(payment["bank"]), {"bank_name", "bank_account", "bank_holder"})
        me = self.client.get("/api/membership/me").get_json()
        self.assertEqual(me["status"], "inactive")
        self.assertEqual(me["remaining"], 0)
        self.assertEqual(self.check().status_code, 403)
        building = self.client.get(f"/api/building/{self.building}")
        self.assertEqual(building.status_code, 200)
        self.assertTrue(building.get_json()["membership_access"]["required"])
        self.assertIn("no-store", building.headers["Cache-Control"])

    def test_payment_retry_and_parallel_tab_only_one_pending(self):
        key = uuid.uuid4().hex
        first = self.apply(request_token=key).get_json()["payment"]
        retry = self.apply(request_token=key)
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(retry.get_json()["payment"]["id"], first["id"])
        tab = self.apply().get_json()["payment"]
        self.assertEqual(tab["id"], first["id"])
        self.assertEqual(self.apply(request_token=key, depositor_name="다른입금자").status_code, 409)

    def test_cancel_ownership_and_admin_cannot_revive_canceled(self):
        payment = self.apply().get_json()["payment"]
        self.login(user=self.users[1])
        self.assertEqual(self.client.post(f"/api/membership/payments/{payment['id']}/cancel", json={}).status_code, 404)
        self.login()
        self.assertEqual(self.client.post(f"/api/membership/payments/{payment['id']}/cancel", json={}).status_code, 200)
        self.assertEqual(self.admin_status(payment["id"], "approved").status_code, 409)

    def test_admin_only_approval_atomic_and_idempotent(self):
        payment = self.apply().get_json()["payment"]
        self.assertEqual(self.client.post(f"/api/admin/membership/payments/{payment['id']}/status",
                                         json={"status": "approved"}).status_code, 401)
        self.assertEqual(self.admin_status(payment["id"], "approved").status_code, 200)
        self.assertEqual(self.admin_status(payment["id"], "approved").status_code, 200)
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM membership_periods WHERE payment_id=%s", [payment["id"]])
            self.assertEqual(cur.fetchone()["n"], 1)
        self.login()
        me = self.client.get("/api/membership/me").get_json()
        self.assertEqual(me["status"], "active")
        self.assertEqual(me["remaining"], 1)
        self.assertIsNotNone(me["period"])

    def test_active_official_records_only_paid_user_and_cache_private(self):
        self.activate()
        with patch.object(application, "_public_lodging_registry_records", return_value=[{
            "source_type": "lodging_registry", "business_name": "유료원장검증",
            "source_name": "숙박업 신고 원장", "permit_number": "12345678", "room_count": 5,
        }]) as registry:
            paid = self.client.get(f"/api/building/{self.building}")
            self.assertEqual(paid.status_code, 200)
            self.assertFalse(paid.get_json()["membership_access"]["required"])
            self.assertTrue(paid.get_json()["operating_records"])
            registry.assert_called_once()
            self.assertIn("private", paid.headers["Cache-Control"])
            self.assertIn("Cookie", paid.headers["Vary"])
            self.login(user=self.users[1])
            free = self.client.get(f"/api/building/{self.building}").get_json()
            self.assertTrue(free["membership_access"]["required"])
            self.assertEqual(free["operating_records"], [])

    def test_one_property_and_three_checks_not_visits_or_duplicate_debits(self):
        self.activate()
        key = uuid.uuid4().hex
        first = self.check(request_token=key)
        self.assertEqual(first.status_code, 201)
        check = first.get_json()["check"]
        for field in ("business_report", "operation_succession", "fee_arrears"):
            self.assertEqual(check[field], "need_check")
        retry = self.check(request_token=key)
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(retry.get_json()["check"]["id"], check["id"])
        self.assertEqual(self.check().status_code, 409)
        self.assertEqual(self.check(survey_type="visit").status_code, 400)
        me = self.client.get("/api/membership/me").get_json()
        self.assertEqual(me["remaining"], 0)
        self.assertEqual(len(me["checks"]), 1)

    def test_renewal_does_not_reset_current_quota_and_expiry_locks(self):
        self.activate()
        self.assertEqual(self.check().status_code, 201)
        second = self.apply().get_json()["payment"]
        self.assertEqual(self.admin_status(second["id"], "approved").status_code, 200)
        self.login()
        self.assertEqual(self.client.get("/api/membership/me").get_json()["remaining"], 0)
        with self.conn.cursor() as cur:
            cur.execute("SELECT * FROM membership_periods WHERE user_id=%s ORDER BY starts_at", [self.users[0]])
            periods = cur.fetchall()
            self.assertEqual(periods[0]["ends_at"], periods[1]["starts_at"])
            cur.execute("UPDATE membership_periods SET revoked_at=NOW() WHERE user_id=%s", [self.users[0]])
        self.assertEqual(self.client.get("/api/membership/me").get_json()["status"], "inactive")
        self.assertEqual(self.check().status_code, 403)

    def test_no_rollover_new_period_one_credit_and_server_expiry(self):
        self.activate()
        with self.conn.cursor() as cur:
            cur.execute("""UPDATE membership_periods SET starts_at=NOW()-INTERVAL '2 months',
              ends_at=NOW()-INTERVAL '1 month' WHERE user_id=%s""", [self.users[0]])
        self.assertEqual(self.client.get("/api/membership/me").get_json()["remaining"], 0)
        self.assertEqual(self.check().status_code, 403)
        self.activate()
        self.assertEqual(self.client.get("/api/membership/me").get_json()["remaining"], 1)

    def test_calendar_month_renewal_uses_korean_month_end_not_utc(self):
        self.activate()
        year = datetime.now().year + 2
        with self.conn.cursor() as cur:
            cur.execute("""UPDATE membership_periods SET starts_at=%s,ends_at=%s WHERE user_id=%s""",
                        [f"{year}-03-01T01:00:00+09", f"{year}-03-31T01:00:00+09", self.users[0]])
        renewal = self.apply().get_json()["payment"]
        self.assertEqual(self.admin_status(renewal["id"], "approved").status_code, 200)
        with self.conn.cursor() as cur:
            cur.execute("""SELECT starts_at AT TIME ZONE 'Asia/Seoul' AS start,
              ends_at AT TIME ZONE 'Asia/Seoul' AS end FROM membership_periods WHERE payment_id=%s""",
                        [renewal["id"]])
            period = cur.fetchone()
        self.assertEqual(period["start"].isoformat(), f"{year}-03-31T01:00:00")
        self.assertEqual(period["end"].isoformat(), f"{year}-04-30T01:00:00")

    def test_report_owner_only_and_admin_can_record_unconfirmed(self):
        self.activate()
        check = self.check().get_json()["check"]
        self.login(admin=True)
        updated = self.client.post(f"/api/admin/membership/checks/{check['id']}/status", json={
            "status": "reported", "business_report": "ok", "operation_succession": "need_check",
            "fee_arrears": "need_check", "report": "운영사와 관리주체 미응답으로 미확인"})
        self.assertEqual(updated.status_code, 200)
        self.login()
        self.assertIn("미확인", self.client.get("/api/membership/me").get_json()["checks"][0]["report"])
        self.login(user=self.users[1])
        self.assertEqual(self.client.get("/api/membership/me").get_json()["checks"], [])
        self.assertEqual(self.client.post(f"/api/admin/membership/checks/{check['id']}/status",
                                         json={"status": "reported"}).status_code, 401)

    def test_rejected_and_revoked_do_not_grant_membership(self):
        first = self.apply().get_json()["payment"]
        self.assertEqual(self.admin_status(first["id"], "rejected", "입금 내역 없음").status_code, 200)
        self.login()
        self.assertEqual(self.client.get("/api/membership/me").get_json()["status"], "inactive")
        paid = self.activate()
        self.assertEqual(self.admin_status(paid["id"], "revoked", "관리자 권한 회수").status_code, 200)
        self.login()
        self.assertEqual(self.check().status_code, 403)

    def test_cross_site_missing_consent_and_invalid_ids(self):
        self.assertEqual(self.apply(agree_terms=False).status_code, 400)
        self.assertEqual(self.client.post("/api/membership/payments", json={
            "depositor_name": "자동검증", "request_token": uuid.uuid4().hex, "agree_terms": True},
            headers={"Origin": "https://evil.invalid"}).status_code, 403)
        self.activate()
        self.assertEqual(self.check(building_id=True).status_code, 400)
        self.assertEqual(self.check(building_id=999999999).status_code, 404)
        self.assertEqual(self.client.get("/api/membership/me").get_json()["remaining"], 1)

    def test_auction_entry_uses_same_bundle_without_legacy_fee(self):
        self.activate()
        detail = self.client.get(f"/api/auctions/{self.auction}/survey-info")
        self.assertEqual(detail.status_code, 200)
        self.assertTrue(detail.get_json()["config"]["membership_included"])
        self.assertNotIn("base_fee", detail.get_json()["config"])
        result = self.client.post(f"/api/auctions/{self.auction}/survey-requests", json={
            "request_token": uuid.uuid4().hex, "agree_terms": True, "memo": "", "survey_type": "basic"})
        self.assertEqual(result.status_code, 201)
        self.assertEqual(result.get_json()["check"]["auction_id"], self.auction)
        self.assertEqual(self.check().status_code, 409)


if __name__ == "__main__":
    unittest.main()