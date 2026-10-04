"""Real SQL/API tests are rollback-only and suppress external notifications."""
import os
os.environ["DISABLE_EXTERNAL_NOTIFICATIONS"] = "1"

import unittest
import uuid
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

from flask import Flask, request
from flask_limiter import Limiter
from psycopg2.extras import Json
from db import get_conn
from survey_defaults import DEFAULT_SETTINGS
import survey_service as service


class BorrowedTransaction:
    """Requests see real SQL but cannot commit a test's temporary data."""
    def __init__(self, conn):
        self.conn = conn
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def cursor(self, *args, **kwargs):
        return self.conn.cursor(*args, **kwargs)
    def close(self):
        pass


class SurveyRules(unittest.TestCase):
    def test_promo_date_includes_last_korean_day_then_expires(self):
        settings = deepcopy(DEFAULT_SETTINGS)
        settings.update(promo_enabled=True, promo_end_date="2026-10-04")
        self.assertEqual(service.public_config(settings, datetime(2026, 10, 4, 14, 59, tzinfo=timezone.utc))["effective_base_fee"], 49000)
        self.assertEqual(service.public_config(settings, datetime(2026, 10, 4, 15, 0, tzinfo=timezone.utc))["effective_base_fee"], 79000)
        settings["promo_enabled"] = False
        self.assertFalse(service.public_config(settings)["promo_active"])

    def test_settings_validation(self):
        self.assertEqual(service.validate_settings(deepcopy(DEFAULT_SETTINGS)), DEFAULT_SETTINGS)
        for key, value in (("base_fee", -1), ("base_fee", 79000.5), ("visit_fee", None),
                           ("payment_hours", 0), ("report_business_days", True), ("bank_holder", ""),
                           ("promo_end_date", "bad"), ("checklist_descriptions", {})):
            data = deepcopy(DEFAULT_SETTINGS); data[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                service.validate_settings(data)
        settings = deepcopy(DEFAULT_SETTINGS)
        settings.update(base_fee=0, visit_fee=0, cutoff_days=0, promo_base_fee=None)
        self.assertEqual(service.validate_settings(settings)["base_fee"], 0)

    def test_three_required_consents(self):
        payload = SurveyAPI.payload()
        for key in ("agree_terms", "agree_refund", "agree_privacy"):
            payload[key] = "true"
            with self.assertRaises(ValueError):
                service.validate_applicant(payload)
            payload[key] = True

    def test_existing_analysis_units_and_missing_values(self):
        links = service.analysis_links({"master_building_id": 9557, "area_m2": 20.3, "min_bid_price": 78500000})
        self.assertEqual(len(links), 3)
        for link in links:
            params = parse_qs(urlparse(link["url"]).query)
            self.assertEqual(params["p_area"], ["20.3"])
            self.assertEqual(params["p_purchase"], ["7850"])
        self.assertEqual(parse_qs(urlparse(links[2]["url"]).query)["buy"], ["7850"])
        self.assertEqual(parse_qs(urlparse(links[1]["url"]).query)["r_purchase"], ["7850"])
        for price in (None, 78500001, 999999999999):
            links = service.analysis_links({"master_building_id": 1, "area_m2": 20.3, "min_bid_price": price})
            self.assertTrue(all("p_purchase" not in link["url"] for link in links))
        self.assertEqual(service.analysis_links({"master_building_id": None}), [])

    def test_cutoff_exact_boundary_and_unknown_date(self):
        now = datetime(2026, 10, 4, tzinfo=timezone.utc)
        item = {"status": "bidding", "bid_end_at": now + timedelta(days=3)}
        self.assertFalse(service.availability(item, DEFAULT_SETTINGS, now)["can_apply"])
        item["bid_end_at"] += timedelta(seconds=1)
        self.assertTrue(service.availability(item, DEFAULT_SETTINGS, now)["can_apply"])
        item["bid_end_at"] = None
        self.assertIn("확인필요", service.availability(item, DEFAULT_SETTINGS, now)["reason"])


class SurveyAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import require_admin
        cls.app = Flask("survey-tests")
        cls.app.secret_key = "local-test-only"
        cls.limiter = Limiter(lambda: request.remote_addr, app=cls.app, storage_uri="memory://")
        service.register_survey_routes(cls.app, cls.limiter, lambda name: name, require_admin)

    @staticmethod
    def payload():
        return {"survey_type": "visit", "applicant_name": "자동검증 신청자", "phone": "010-0000-0000",
                "email": "", "memo": "롤백 전용 테스트", "depositor_name": "자동검증",
                "agree_terms": True, "agree_refund": True, "agree_privacy": True}

    def setUp(self):
        self.limiter.reset()
        self.conn = get_conn()
        self.connection_patch = patch.object(service, "get_conn", return_value=BorrowedTransaction(self.conn))
        self.connection_patch.start()
        self.addCleanup(self.connection_patch.stop)
        self.addCleanup(self.conn.close)
        self.addCleanup(self.conn.rollback)
        self.client = self.app.test_client()
        with self.conn.cursor() as cur:
            cur.execute("SET LOCAL app.disable_admin_notifications='on'")
            cur.execute("UPDATE app_meta SET value=%s WHERE key='survey_settings'", [Json(DEFAULT_SETTINGS)])
            cur.execute("""INSERT INTO auction_items(source,source_item_id,pbct_cdtn_no,title,status,bid_end_at)
              VALUES('manual',%s,'test','자동검증 공매','bidding',NOW()+INTERVAL '10 days') RETURNING id""", [uuid.uuid4().hex])
            self.item_id = cur.fetchone()["id"]

    def admin(self):
        with self.client.session_transaction() as sess:
            sess["admin"] = True
            sess["admin_user_id"] = 1

    def create(self, **changes):
        return self.client.post(f"/api/auctions/{self.item_id}/survey-requests",
                                json={**self.payload(), **changes})

    def row(self):
        with self.conn.cursor() as cur:
            cur.execute("SELECT * FROM survey_requests WHERE auction_item_id=%s ORDER BY id DESC", [self.item_id])
            return cur.fetchone()

    def test_server_amount_snapshot_and_immediate_settings(self):
        old = self.create(base_fee=1, visit_fee=1, total_fee=2)
        self.assertEqual(old.status_code, 201)
        self.assertEqual(old.json["receipt"]["total_fee"], 178000)
        self.admin()
        changed = deepcopy(DEFAULT_SETTINGS); changed.update(base_fee=89000, visit_fee=120000)
        changed["bank_account"] = "검증용 계좌"
        result = self.client.put("/api/admin/survey/settings", json=changed)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(self.client.get("/api/survey/config").json["config"]["effective_base_fee"], 89000)
        with self.conn.cursor() as cur:
            cur.execute("SELECT total_fee,settings_snapshot FROM survey_requests WHERE request_no=%s", [old.json["receipt"]["request_no"]])
            row = cur.fetchone()
            self.assertEqual(row["total_fee"], 178000)
            self.assertEqual(row["settings_snapshot"]["bank_account"], DEFAULT_SETTINGS["bank_account"])
        new = self.create(total_fee=1)
        self.assertEqual(new.json["receipt"]["total_fee"], 209000)
        self.assertEqual(new.json["receipt"]["bank_account"], "검증용 계좌")
        self.assertEqual(result.json["history"][0]["before"]["base_fee"], 79000)

    def test_promo_enabled_disabled_and_expired(self):
        self.admin()
        settings = deepcopy(DEFAULT_SETTINGS)
        settings.update(promo_enabled=True, promo_end_date=(service.utcnow().astimezone(service.KST).date()+timedelta(days=1)).isoformat())
        self.assertEqual(self.client.put("/api/admin/survey/settings", json=settings).status_code, 200)
        self.assertEqual(self.create(survey_type="basic").json["receipt"]["total_fee"], 49000)
        settings["promo_enabled"] = False
        self.client.put("/api/admin/survey/settings", json=settings)
        self.assertEqual(self.create(survey_type="basic").json["receipt"]["total_fee"], 79000)
        settings.update(promo_enabled=True, promo_end_date="2000-01-01")
        self.client.put("/api/admin/survey/settings", json=settings)
        self.assertEqual(self.create(survey_type="basic").json["receipt"]["total_fee"], 79000)

    def test_consents_missing_or_false_rejected(self):
        self.assertEqual(self.create(agree_terms=False).status_code, 400)
        self.assertEqual(self.create(agree_refund=False).status_code, 400)
        self.assertEqual(self.create(agree_privacy=False).status_code, 400)
        self.assertIsNone(self.row())

    def test_guest_creation_and_no_public_pii(self):
        result = self.create()
        self.assertEqual(result.status_code, 201)
        self.assertNotIn("applicant_name", result.json["receipt"])
        self.assertNotIn("phone", result.json["receipt"])
        self.assertFalse(any(key in self.client.get("/api/survey/config").json["config"] for key in ("applicant_name", "phone", "email")))
        info = self.client.get(f"/api/auctions/{self.item_id}/survey-info")
        self.assertEqual(info.status_code, 200)
        self.assertEqual(info.json["analysis_links"], [])
        self.assertTrue(info.json["availability"]["can_apply"])
        self.assertTrue(all(row["check_status"]=="need_check" for row in info.json["checklist"]))

    def test_admin_guards_all_methods_and_cross_site(self):
        for path, method in (("/api/admin/survey/settings", "get"), ("/api/admin/survey/settings", "put"),
                             ("/api/admin/survey/requests", "get"), ("/api/admin/survey/requests/1", "get"),
                             ("/api/admin/survey/requests/1/status", "post")):
            self.assertIn(getattr(self.client, method)(path).status_code, (401, 403))
        self.assertEqual(self.client.post(f"/api/auctions/{self.item_id}/survey-requests",
                         json=self.payload(), headers={"Sec-Fetch-Site": "cross-site"}).status_code, 403)

    def test_request_cutoff_on_server(self):
        with self.conn.cursor() as cur:
            cur.execute("UPDATE auction_items SET bid_end_at=NOW()+INTERVAL '2 days' WHERE id=%s", [self.item_id])
        self.assertEqual(self.create().status_code, 409)
        with self.conn.cursor() as cur:
            cur.execute("UPDATE auction_items SET bid_end_at=NULL WHERE id=%s", [self.item_id])
        self.assertEqual(self.create().status_code, 409)
        self.assertIsNone(self.row())

    def test_idempotent_retry_and_changed_quote(self):
        token = uuid.uuid4().hex
        first = self.create(request_token=token)
        second = self.create(request_token=token)
        self.assertEqual(first.json["receipt"]["request_no"], second.json["receipt"]["request_no"])
        self.assertEqual(second.status_code, 200)
        self.assertEqual(self.create(request_token=token, survey_type="basic").status_code, 409)
        self.assertEqual(self.create(config_version="old-quote").status_code, 409)

    def test_terms_edit_requires_renewed_agreement(self):
        quote = self.client.get("/api/survey/config").json["config"]
        with self.conn.cursor() as cur:
            cur.execute("UPDATE legal_documents SET content=content || '<p>검증용 개정</p>' WHERE doc_type='survey_terms'")
        self.assertEqual(self.create(config_version=quote["version"]).status_code, 409)
        new_quote = self.client.get("/api/survey/config").json["config"]
        self.assertNotEqual(quote["terms_version"], new_quote["terms_version"])
        self.assertEqual(self.create(config_version=new_quote["version"]).status_code, 201)

    def test_ip_five_per_hour(self):
        for _ in range(5):
            self.assertEqual(self.create().status_code, 201)
        self.assertEqual(self.create().status_code, 429)

    def test_auto_cancel_idempotent_and_paid_is_preserved(self):
        self.create()
        row_id = self.row()["id"]
        with self.conn.cursor() as cur:
            cur.execute("UPDATE survey_requests SET payment_deadline=NOW()-INTERVAL '1 second' WHERE id=%s", [row_id])
            self.assertEqual(service.cancel_expired(cur), 1)
            self.assertEqual(service.cancel_expired(cur), 0)
            cur.execute("SELECT * FROM survey_request_history WHERE request_id=%s ORDER BY id DESC", [row_id])
            self.assertIn("자동취소", cur.fetchone()["note"])
        self.assertEqual(self.row()["status"], "canceled")
        self.create()
        with self.conn.cursor() as cur:
            cur.execute("UPDATE survey_requests SET status='paid',payment_deadline=NOW()-INTERVAL '1 second' WHERE id=%s", [self.row()["id"]])
            self.assertEqual(service.cancel_expired(cur), 0)

    def test_admin_status_flow_history_and_search(self):
        self.create()
        row = self.row(); self.admin()
        for state in ("paid", "investigating", "reported", "refunded"):
            self.assertEqual(self.client.post(f"/api/admin/survey/requests/{row['id']}/status",
                             json={"status": state, "note": "검증 메모"}).status_code, 200)
        self.assertEqual(self.client.post(f"/api/admin/survey/requests/{row['id']}/status", json={"status":"received"}).status_code, 409)
        result = self.client.get("/api/admin/survey/requests", query_string={"q":row["request_no"],"status":"refunded"})
        self.assertEqual(result.json["total"], 1)
        history = self.client.get(f"/api/admin/survey/requests/{row['id']}").json["history"]
        self.assertEqual(len(history), 5)

    def test_expired_payment_confirmation_cannot_revive(self):
        self.create()
        row_id = self.row()["id"]; self.admin()
        with self.conn.cursor() as cur:
            cur.execute("UPDATE survey_requests SET payment_deadline=NOW()-INTERVAL '1 second' WHERE id=%s", [row_id])
        result = self.client.post(f"/api/admin/survey/requests/{row_id}/status", json={"status":"paid","note":"늦은 확인"})
        self.assertEqual(result.status_code, 409)
        self.assertEqual(self.row()["status"], "canceled")

    def test_settings_invalid_required_fields_and_cannot_override_server_fields(self):
        self.admin()
        settings = deepcopy(DEFAULT_SETTINGS); settings["base_fee"] = None
        self.assertEqual(self.client.put("/api/admin/survey/settings", json=settings).status_code, 400)
        self.assertEqual(self.client.get("/api/admin/survey/settings").json["settings"]["base_fee"], 79000)

    def test_admin_notification_insert_is_atomic_and_idempotent(self):
        self.create()
        row = self.row()
        with self.conn.cursor() as cur:
            cur.execute("SET LOCAL app.disable_admin_notifications='off'")
            # Uncommitted opt-out avoids outbox delivery even by other running workers.
            cur.execute("UPDATE admin_event_subscriptions SET in_app_enabled=TRUE,email_enabled=FALSE WHERE event_type='survey_request'")
            service.notify_admin(cur, row["id"], row["request_no"])
            service.notify_admin(cur, row["id"], row["request_no"])
            cur.execute("SELECT COUNT(*) AS n FROM admin_notifications WHERE source_table='survey_requests' AND source_id=%s", [row["id"]])
            count = cur.fetchone()["n"]
            cur.execute("SELECT COUNT(*) AS n FROM admin_event_subscriptions WHERE event_type='survey_request'")
            self.assertEqual(count, cur.fetchone()["n"])


if __name__ == "__main__":
    unittest.main()