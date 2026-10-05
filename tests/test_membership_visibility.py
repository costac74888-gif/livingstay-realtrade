"""입금 확인 전에는 로그인·역할과 무관하게 상세 원장과 조사 신청을 차단한다."""
import unittest
from unittest.mock import patch

import app as application
import survey_service
from db import get_conn
from premium_membership import membership_access


class MembershipVisibilityTest(unittest.TestCase):
    def setUp(self):
        self.client = application.app.test_client()
        self.client.environ_base["HTTP_USER_AGENT"] = "Mozilla/5.0 MembershipBoundaryTest"
        self.client.environ_base["HTTP_X_FORWARDED_FOR"] = "203.0.113.157"

    def test_preparation_is_not_an_active_subscription(self):
        for feature in ("official_operating_records", "auction_survey"):
            access = membership_access(feature)
            self.assertTrue(access["required"])
            self.assertFalse(access["available"])
            self.assertEqual(access["status"], "inactive")
            self.assertEqual(access["info_url"], "/membership")

    def test_public_building_omits_records_but_keeps_free_summary(self):
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM master_buildings WHERE lodging_type='생활' AND units>0 ORDER BY id LIMIT 1")
                building_id = cur.fetchone()["id"]
        with patch.object(application, "_public_lodging_registry_records") as registry, \
             patch.object(application, "_public_annual_operating_records") as annual, \
             patch.object(application.annual_tourism_roster, "latest_linked_operating_info") as legacy, \
             patch.object(application, "_fetch_and_cache_building_detail"):
            for authenticated in (False, True):
                if authenticated:
                    with self.client.session_transaction() as session:
                        session["user_id"] = 987654321
                        session["role"] = "lodging_operator"
                result = self.client.get(f"/api/building/{building_id}")
                self.assertEqual(result.status_code, 200)
                data = result.get_json()
                self.assertEqual(data["operating_records"], [])
                self.assertIsNone(data["operating_info"])
                self.assertIsNone(data["operating_primary"])
                self.assertIsNone(data["operating_record_count"])
                self.assertTrue(data["membership_access"]["required"])
                for field in ("lodgings", "lodging_room_total", "units", "property_info"):
                    self.assertIn(field, data)
            registry.assert_not_called()
            annual.assert_not_called()
            legacy.assert_not_called()

    def test_survey_configuration_and_new_order_are_blocked_before_db_access(self):
        with patch.object(survey_service, "survey_connection") as db_access:
            for actor in ("anonymous", "member", "operator"):
                self.client.environ_base["HTTP_X_FORWARDED_FOR"] = {
                    "anonymous": "203.0.113.158", "member": "203.0.113.159", "operator": "203.0.113.160"
                }[actor]
                if actor != "anonymous":
                    with self.client.session_transaction() as session:
                        session["user_id"] = 987654321
                        session["role"] = actor
                for result in (
                    self.client.get("/api/survey/config"),
                    self.client.post("/api/auctions/1/survey-requests", json={}),
                ):
                    self.assertEqual(result.status_code, 403)
                    data = result.get_json()
                    self.assertEqual(data["code"], "MEMBERSHIP_REQUIRED")
                    self.assertNotIn("config", data)
                    self.assertNotIn("receipt", data)
                    self.assertIn("no-store", result.headers["Cache-Control"])
            db_access.assert_not_called()

    def test_survey_information_is_a_notice_not_a_hidden_payload(self):
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM auction_items WHERE usage_name NOT LIKE '%오피스텔%' ORDER BY id LIMIT 1")
                item_id = cur.fetchone()["id"]
        with patch.object(survey_service, "load_settings") as settings, \
             patch.object(survey_service, "load_quote") as quote, \
             patch.object(survey_service, "load_item") as item:
            result = self.client.get(f"/api/auctions/{item_id}/survey-info")
            self.assertEqual(result.status_code, 200)
            data = result.get_json()
            self.assertTrue(data["ok"])
            self.assertIsNone(data["item"])
            self.assertTrue(data["membership_access"]["required"])
            for field in ("config", "checklist", "comparison", "analysis_links", "availability"):
                self.assertNotIn(field, data)
            settings.assert_not_called()
            quote.assert_not_called()
            item.assert_not_called()
        self.assertEqual(self.client.get("/api/auctions/999999999/survey-info").status_code, 404)

    def test_membership_page_describes_approved_bank_scope_without_auto_activation(self):
        response = self.client.get("/membership")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('id="membershipApp"', html)
        self.assertIn("/static/js/membership.js", html)
        self.assertNotIn("현재 멤버십 가입 및 유료 기능 활성화는 제공되지 않습니다.", html)
        for text in ("29,000", "무제한", "영업신고", "위탁운영", "관리비", "미확인", "이월", "현장"):
            self.assertIn(text, html)
        self.assertRegex(html, r"월\s*1")
        self.assertRegex(html, r"동일|같은")
        self.assertNotIn("가격, 구독 기간, 결제 방법과 멤버십 활성화 일정은 아직 확정", html)
        self.assertNotIn('id="surveyRequestForm"', html)
        self.assertNotIn("data-purchase", html)


if __name__ == "__main__":
    unittest.main()