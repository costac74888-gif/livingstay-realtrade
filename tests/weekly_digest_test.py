"""주간 이메일의 회차·제목·Zone 순서·통계 캐시 방어를 검증한다."""

import os
import re
import sys
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import weekly_digest as digest


class _CandidateCursor:
    """_resolve_building_ids 단위 테스트용 최소 커서."""

    def __init__(self, candidates):
        self.candidates = candidates
        self.query = None
        self.params = None

    def execute(self, query, params):
        self.query = query
        self.params = params

    def fetchall(self):
        return self.candidates


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

    def test_missing_building_ids_use_transaction_then_address_then_unique_name(self):
        cursor = _CandidateCursor([
            {
                "id": 8450,
                "building_name": "제주에어포트호텔",
                "road_address": "제주특별자치도 제주시 공항로 2",
                "jibun_address": "제주특별자치도 제주시 용담이동 1",
                "sgg_cd": "50110",
                "umd_nm": "용담이동",
                "jibun": "1",
            },
            {
                "id": 8451,
                "building_name": "제주에어포트호텔",
                "road_address": "제주특별자치도 제주시 공항로 99",
                "jibun_address": "제주특별자치도 제주시 용담이동 99",
                "sgg_cd": "50110",
                "umd_nm": "용담이동",
                "jibun": "99",
            },
            {
                "id": 302,
                "building_name": "주소 매칭 호텔",
                "road_address": "강원특별자치도 속초시 바다로 10",
                "jibun_address": None,
                "sgg_cd": "51820",
                "umd_nm": "대포동",
                "jibun": "20",
            },
            {
                "id": 303,
                "building_name": "전국 유일 호텔",
                "road_address": "서울특별시 중구 남대문로 1",
                "jibun_address": None,
                "sgg_cd": "11140",
                "umd_nm": "회현동",
                "jibun": "3",
            },
        ])
        rows = [
            {
                "building_name": "제주에어포트호텔",
                "sgg_cd": "50110",
                "umd_nm": "용담 이 동",
                "jibun": "1",
            },
            {
                "building_name": "주소 매칭 호텔",
                "address": "강원특별자치도 속초시 바다로 10",
            },
            {"building_name": "전국 유일 호텔"},
            {"building_name": "제주에어포트호텔"},
        ]

        self.assertEqual(digest._resolve_building_ids(cursor, rows), 3)
        self.assertEqual(rows[0]["building_id"], 8450)
        self.assertEqual(rows[1]["building_id"], 302)
        self.assertEqual(rows[2]["building_id"], 303)
        self.assertNotIn("building_id", rows[3])
        self.assertIn("CONCAT_WS", cursor.query)

    def test_all_building_name_links_in_generated_email_are_detail_links(self):
        html = digest.build_html(
            "테스터",
            [("관심 단지", "서울특별시 중구 테스트로 1", 101)],
            {
                ("관심 단지", "서울특별시 중구 테스트로 1"): {
                    "price": 10000,
                    "deal_date": "2026-08-26",
                    "building_id": 101,
                },
            },
            [{
                "master_building_id": 102,
                "building_name": "매물 의뢰 단지",
                "status": "submitted",
            }],
            [{
                "master_building_id": 103,
                "building_name": "매수 의뢰 단지",
                "status": "consulting",
            }],
            [{"building_id": 104, "building_name": "신고가 랭킹 단지", "pct_gain": 4.2}],
            [{"building_id": 105, "building_name": "거래량 랭킹 단지", "deal_count": 9}],
            {
                "report_rate": None,
                "price_change": {
                    "building_id": 106,
                    "building_name": "데이터랩 가격 단지",
                    "change_percent": 8.2,
                },
                "volume_top": {
                    "building_id": 8450,
                    "building_name": "제주에어포트호텔",
                    "deal_count": 17,
                },
            },
            None,
            "https://example.test/unsubscribe",
            signal_counts={"deal": 1},
        )

        expected_links = {
            "관심 단지": 101,
            "매물 의뢰 단지": 102,
            "매수 의뢰 단지": 103,
            "신고가 랭킹 단지": 104,
            "거래량 랭킹 단지": 105,
            "데이터랩 가격 단지": 106,
            "제주에어포트호텔 17건": 8450,
            "제주에어포트호텔": 8450,
        }
        for building_name, building_id in expected_links.items():
            self.assertRegex(
                html,
                rf'<a href="{re.escape(digest.SITE_URL)}/building/{building_id}"[^>]*>'
                rf'{re.escape(building_name)}</a>',
                building_name,
            )

    def test_unmatched_building_name_is_not_disguised_as_a_home_link(self):
        html = digest.build_html(
            "테스터", [], {}, [], [], [], [],
            {
                "report_rate": None,
                "price_change": {
                    "building_name": "미매칭 단지",
                    "change_percent": 3.1,
                },
                "volume_top": None,
            },
            None,
            "https://example.test/unsubscribe",
        )
        self.assertRegex(html, r'<span[^>]*>미매칭 단지</span>')
        self.assertIn("상세 정보 준비 중", html)
        self.assertNotRegex(html, r'<a [^>]*>미매칭 단지</a>')

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
            "관심단지 숙박알리미",
            "매물의뢰 진행 현황",
            "이번 주 시세 랭킹",
            "이번 주 기능 소개",
        ]
        indexes = [html.index(heading) for heading in headings]
        self.assertEqual(indexes, sorted(indexes))
        self.assertIn("관심단지를 등록하면 이런 알림을 받을 수 있어요", html)
        self.assertIn("지금 관심단지 등록하기", html)
        self.assertIn(
            f'href="{digest.SITE_URL}/?utm_source=weekly&utm_medium=email&utm_campaign=no_fav_cta"',
            html,
        )
        self.assertIn("제휴 중개법인 통해 수수료 0원", html)
        self.assertIn("/guide#listing-guide", html)
        self.assertNotIn("데이터랩 한눈에 보기", html)
        self.assertIn("기능 소개 제목", html)

    def test_zone1_empty_signal_cta_mentions_more_favorites(self):
        html = digest.build_html(
            "테스터",
            [("관심 단지", "서울특별시 중구 테스트로 1", 101)],
            {},
            [],
            [],
            [],
            [],
            {"report_rate": None, "price_change": None, "volume_top": None},
            None,
            "https://example.test/mypage",
            signal_counts={"deal": 0, "urgent": 0},
        )
        self.assertIn("이번 주 관심단지의 새로운 알림이 없었어요.", html)
        self.assertIn("관심단지를 더 추가하면 더 많은 알림을 받을 수 있어요.", html)
        self.assertIn(
            f'href="{digest.SITE_URL}/mypage?utm_source=weekly&utm_medium=email&utm_campaign=no_signal_cta"',
            html,
        )

    def test_urgent_signal_is_rendered_as_one_summary_row(self):
        html = digest.build_html(
            "테스터",
            [("관심 단지", "서울특별시 중구 테스트로 1", 101)],
            {},
            [],
            [],
            [],
            [],
            {"report_rate": None, "price_change": None, "volume_top": None},
            None,
            "https://example.test/mypage",
            signal_counts={"urgent": 3},
        )
        self.assertIn("🔥 급매", html)
        self.assertIn("3건", html)
        self.assertNotIn("금 급매", html)
        self.assertNotIn("은 급매", html)

    def test_zone0_prefers_report_rate_and_has_hero_style(self):
        html = digest.build_html(
            "테스터", [], {}, [], [], [], [],
            {
                "report_rate": 42.5,
                "price_change": {"building_name": "상승 단지", "change_percent": 9.8},
                "volume_top": {"building_name": "거래 단지", "deal_count": 7},
            },
            None, "https://example.test/mypage",
        )
        self.assertIn("전국 생숙 영업신고율", html)
        self.assertIn("42.5%", html)
        self.assertIn("데이터랩 전체 보기 →", html)
        self.assertIn(f'href="{digest.SITE_URL}/?datalab=consign"', html)
        self.assertIn("border-left:4px solid #B4863F", html)
        self.assertIn("background:#F8F4EE", html)

    def test_zone0_falls_back_to_volume_top_and_zone3_uses_cards(self):
        html = digest.build_html(
            "테스터", [], {}, [], [], [], [],
            {
                "report_rate": None,
                "price_change": {"building_name": "상승 단지", "change_percent": 9.8},
                "volume_top": {"building_id": 24, "building_name": "거래 단지", "deal_count": 7},
            },
            {
                "title": "기능 소개 제목",
                "body": "기능 설명",
                "cta_label": "자세히 보기",
                "cta_url": "/guide",
            },
            "https://example.test/mypage",
        )
        self.assertIn("거래 단지", html)
        self.assertIn("거래 단지 7건", html)
        self.assertIn(f'href="{digest.SITE_URL}/building/24"', html)
        self.assertIn("weekly-datalab-cards", html)
        self.assertEqual(html.count('<td class="weekly-datalab-card-cell"'), 3)
        self.assertIn(f'href="{digest.SITE_URL}/?datalab=lodging"', html)
        self.assertIn("background:#F0F4FF", html)

    def test_empty_zone3_and_zone4_are_omitted(self):
        html = digest.build_html(
            "테스터", [], {}, [], [], [], [],
            {"report_rate": None, "price_change": None, "volume_top": None},
            None, "https://example.test/mypage",
        )
        self.assertNotIn("데이터랩 한눈에 보기", html)
        self.assertNotIn("이번 주 기능 소개", html)
        self.assertNotIn("데이터랩 전체 보기 →", html)

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