"""주간 이메일의 회차·제목·Zone 순서·통계 캐시 방어를 검증한다."""

import os
import sys
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import weekly_digest as digest


class WeeklyDigestTests(unittest.TestCase):
    def test_iso_week_cycles_through_eight_feature_episodes(self):
        self.assertEqual(digest._weekly_feature_episode(date(2026, 1, 1)), 1)
        self.assertEqual(digest._weekly_feature_episode(date(2026, 2, 19)), 8)
        self.assertEqual(digest._weekly_feature_episode(date(2026, 2, 26)), 1)

    def test_datalab_summary_uses_only_successful_master_cache_sections(self):
        app_module = SimpleNamespace(
            _MASTER_STATS_CACHE={
                "sections": {
                    "consign_stats": {"status": "ok"},
                    "transaction_stats": {"status": "ok"},
                },
                "data": {
                    "consign_stats": {"total": {"report_rate": 42.5}},
                    "transaction_stats": {
                        "price_change": {"up": {"items": [{
                            "building_name": "상승 단지",
                            "building_id": 12,
                            "change_percent": 9.8,
                        }]}},
                        "volume_top": [{
                            "building_name": "거래 단지",
                            "building_id": 24,
                            "deal_count": 7,
                        }],
                    },
                },
            }
        )
        summary = digest._get_datalab_summary(app_module)
        self.assertEqual(summary["report_rate"], 42.5)
        self.assertEqual(summary["price_change"]["building_name"], "상승 단지")
        self.assertEqual(summary["volume_top"]["deal_count"], 7)

        app_module._MASTER_STATS_CACHE["sections"]["transaction_stats"] = {"status": "error"}
        partial = digest._get_datalab_summary(app_module)
        self.assertEqual(partial["report_rate"], 42.5)
        self.assertIsNone(partial["price_change"])
        self.assertIsNone(partial["volume_top"])

    @patch("weekly_digest._get_datalab_summary_db_fallback")
    def test_datalab_summary_falls_back_when_cache_is_unavailable(self, fallback):
        fallback.return_value = {
            "report_rate": 50.1,
            "price_change": {"building_name": "상승 단지", "change_percent": 4.2},
            "volume_top": {"building_name": "거래 단지", "deal_count": 9},
        }
        app_module = SimpleNamespace(_MASTER_STATS_CACHE={})

        self.assertEqual(digest._get_datalab_summary(app_module), fallback.return_value)
        fallback.assert_called_once_with()

    def test_email_zone_order_and_empty_state_ctas(self):
        tip = {
            "episode": 1,
            "title": "기능 소개 제목",
            "body": "기능 설명",
            "cta_label": "자세히 보기",
            "cta_url": "/guide",
        }
        html = digest.build_html(
            "테스터", [], {}, [], [], [], [],
            {"report_rate": None, "price_change": None, "volume_top": None},
            tip, "https://example.test/mypage",
        )
        headings = [
            "관심단지 실거래 알림",
            "매물의뢰 진행 현황",
            "이번 주 시세 랭킹",
            "이번 주 기능 소개",
        ]
        indexes = [html.index(heading) for heading in headings]
        self.assertEqual(indexes, sorted(indexes))
        self.assertIn("관심단지 등록하고 실거래 알림 받기", html)
        self.assertIn(f'href="{digest.SITE_URL}/"', html)
        self.assertIn("제휴 중개법인 통해 수수료 0원", html)
        self.assertIn("/guide#listing-guide", html)
        self.assertNotIn("데이터랩 한눈에 보기", html)
        self.assertIn("기능 소개 제목", html)

    def test_empty_zone3_and_zone4_are_omitted(self):
        html = digest.build_html(
            "테스터", [], {}, [], [], [], [],
            {"report_rate": None, "price_change": None, "volume_top": None},
            None, "https://example.test/mypage",
        )
        self.assertNotIn("데이터랩 한눈에 보기", html)
        self.assertNotIn("이번 주 기능 소개", html)

    def test_subject_priority_has_no_ad_prefix(self):
        tip = {"title": "이번 주 기능"}
        price = {"price_change": {"building_name": "상승 단지", "change_percent": 12.3}}
        self.assertIn(
            "관심단지 2곳 새 실거래",
            digest._build_subject(2, price, tip),
        )
        self.assertEqual(
            digest._build_subject(0, price, tip),
            "[홈앤스테이] 가격변동 TOP1 | 상승 단지 +12.3%",
        )
        self.assertEqual(
            digest._build_subject(0, {}, tip),
            "[홈앤스테이] 이번 주 기능",
        )
        self.assertEqual(
            digest._build_subject(0, {}, None),
            "[홈앤스테이] 이번 주 소식",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)