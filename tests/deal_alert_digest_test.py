"""일일 관심단지 실거래 digest의 KST 범위·중복 방지·메일 구조를 검증한다."""

import os
import sys
import unittest
from datetime import date, datetime, timezone
import inspect

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import deal_alert_digest as digest


class _LogCursor:
    """UNIQUE(user_id, transaction_id, alert_date)를 흉내 내는 최소 커서."""

    def __init__(self):
        self.claimed = set()
        self.last_row = None
        self.sql = []

    def execute(self, sql, params):
        self.sql.append(sql)
        user_id, transaction_id, alert_date = params
        key = (user_id, transaction_id, alert_date)
        if key in self.claimed:
            self.last_row = None
        else:
            self.claimed.add(key)
            self.last_row = {"transaction_id": transaction_id}

    def fetchone(self):
        return self.last_row


class DealAlertDigestTests(unittest.TestCase):
    def test_kst_yesterday_and_utc_bounds(self):
        now = datetime(2026, 8, 24, 0, 30, tzinfo=timezone.utc)  # KST 09:30
        self.assertEqual(digest.kst_yesterday(now), date(2026, 8, 23))
        start, end = digest.kst_day_utc_bounds(date(2026, 8, 23))
        self.assertEqual(start, datetime(2026, 8, 22, 15, 0))
        self.assertEqual(end, datetime(2026, 8, 23, 15, 0))

    def test_same_user_transaction_and_day_is_claimed_once(self):
        cur = _LogCursor()
        day = date(2026, 8, 23)
        first = digest._claim_deals(cur, 7, [100, 101], day)
        second = digest._claim_deals(cur, 7, [100, 101], day)
        self.assertEqual(first, [100, 101])
        self.assertEqual(second, [])
        self.assertIn("ON CONFLICT (user_id, transaction_id, alert_date)", cur.sql[0])

    def test_email_keeps_zone_one_and_unsubscribe_link(self):
        body = digest.build_html(
            "테스터",
            [{
                "building_name": "테스트 호텔",
                "address": "서울 중구 1-1",
                "price": 25000,
                "deal_date": "2026-08-23",
                "deal_type": "중개거래",
                "area": 31.5,
                "floor": "8",
            }],
            "https://example.test/unsubscribe?token=abc",
        )
        self.assertIn("관심단지 실거래 알림", body)
        self.assertIn("테스트 호텔", body)
        self.assertIn("2억 5,000만원", body)
        self.assertIn("https://example.test/unsubscribe?token=abc", body)
        self.assertIn("관심단지와 실거래 더 보기", body)

    def test_recipients_use_enabled_deal_alert_subscriptions(self):
        query_source = inspect.getsource(digest._load_recipients)
        self.assertIn("JOIN user_alert_subscriptions", query_source)
        self.assertNotIn("JOIN user_favorites", query_source)


if __name__ == "__main__":
    unittest.main(verbosity=2)