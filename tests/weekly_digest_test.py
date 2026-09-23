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
os.environ.setdefault("SKIP_STARTUP_SCHEMA_INIT", "1")
import app as app_module
from app import _email_target_is_safe


def _public_api_payload(path, _app_module=None):
    if path == "/api/stats/consign-by-sido":
        return {"ok": True, "total": {"report_rate": 42.5}}
    if path == "/api/stats/price-change-top?direction=up":
        return {"ok": True, "items": [{
            "building_name": "상승 단지",
            "building_id": 12,
            "change_percent": 9.8,
        }]}
    if path == "/api/ranking":
        return {
            "price_highs": [],
            "most_traded": [{
                "building_name": "거래 단지",
                "building_id": 24,
                "deal_count": 7,
            }],
        }
    return {}


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


class _ConsumptionCursor:
    """관광소비 단일 원본 조회를 검증하는 최소 커서."""

    def __init__(self, rows):
        self.rows = rows
        self.query = None

    def execute(self, query):
        self.query = query

    def fetchall(self):
        return self.rows

    def close(self):
        pass


class _ConsumptionConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def close(self):
        pass


class _RankingCursor:
    def __init__(self, rows):
        self.result_sets = iter(rows)
        self.queries = []
        self.params = []

    def execute(self, query, params):
        self.queries.append(query)
        self.params.append(params)

    def fetchall(self):
        return next(self.result_sets)


class _ClaimCursor:
    def __init__(self):
        self.query = ""
        self.params = None

    def execute(self, query, params):
        self.query = query
        self.params = params

    def fetchone(self):
        return {
            "id": 10, "tracking_token": "opaque-token",
            "claim_token": "lease-token", "attempts": 1,
        }


class _FinishCursor:
    rowcount = 1

    def __init__(self):
        self.query = ""
        self.params = None

    def execute(self, query, params):
        self.query = query
        self.params = params


class _ReportClaimCursor:
    def __init__(self):
        self.query = ""
        self.params = None

    def execute(self, query, params):
        self.query = query
        self.params = params

    def fetchone(self):
        return {"id": 22, "claim_token": "report-lease", "attempts": 1}


class _CommitConnection:
    def commit(self):
        pass

    def rollback(self):
        pass


class WeeklyDigestTests(unittest.TestCase):
    def test_kst_cohort_and_eight_week_assignment_are_stable(self):
        self.assertEqual(digest.cohort_for_user(2), "tue")
        self.assertEqual(digest.cohort_for_user(3), "thu")
        self.assertEqual(digest.experiment_week(date(2026, 9, 15)), 1)
        self.assertEqual(digest.experiment_week(date(2026, 11, 2)), 8)
        self.assertIsNone(digest.experiment_week(date(2026, 11, 9)))
        self.assertIsNone(digest.experiment_week(digest.experiment_report_date()))
        self.assertEqual(digest.scheduled_cohort(date(2026, 9, 15)), "tue")
        self.assertEqual(digest.scheduled_cohort(date(2026, 9, 17)), "thu")
        self.assertIsNone(digest.scheduled_cohort(date(2026, 9, 16)))

    def test_tracking_wraps_internal_links_but_not_unsubscribe(self):
        body = digest.build_html(
            "테스터", [], {}, [], [], [], [],
            {"report_rate": 42.5}, None,
            "https://example.test/unsubscribe?token=abc",
            tracking_token="00000000-0000-0000-0000-000000000001",
        )
        self.assertIn("/email/open?token=", body)
        self.assertIn("/email/click?token=", body)
        self.assertIn('href="https://example.test/unsubscribe?token=abc"', body)

    def test_experiment_report_counts_unique_events_and_rates(self):
        metrics = digest.calculate_experiment_report([
            {"cohort": "tue", "status": "sent", "attempts": 1,
             "open_count": 2, "click_count": 1},
            {"cohort": "tue", "status": "failed", "attempts": 3,
             "open_count": 0, "click_count": 0},
            {"cohort": "thu", "status": "sent", "attempts": 2,
             "open_count": 1, "click_count": 0},
        ])
        self.assertEqual(metrics["tue"]["targeted"], 2)
        self.assertEqual(metrics["tue"]["unique_opens"], 1)
        self.assertEqual(metrics["tue"]["unique_clicks"], 1)
        self.assertEqual(metrics["tue"]["attempts"], 4)
        self.assertEqual(metrics["tue"]["click_rate"], 1.0)
        self.assertEqual(digest._choose_experiment_winner(metrics), "tue")

    def test_report_waits_until_week_nine_thursday(self):
        self.assertEqual(digest.experiment_report_date(), date(2026, 11, 12))
        self.assertLess(date(2026, 11, 5), digest.experiment_report_date())

    def test_claim_sql_excludes_sent_and_has_retry_guards(self):
        cursor = _ClaimCursor()
        claim = digest._claim_delivery(cursor, 4, date(2026, 9, 14), "tue")
        self.assertEqual(claim["attempts"], 1)
        self.assertIn("status <> 'sent'", cursor.query)
        self.assertIn("status = 'failed'", cursor.query)
        self.assertIn("claimed_at", cursor.query)
        self.assertIn("attempts < %s", cursor.query)
        self.assertEqual(cursor.params[-1], digest.MAX_DELIVERY_ATTEMPTS)

    def test_finish_sql_is_fenced_by_claim_token(self):
        cursor = _FinishCursor()
        digest._finish_delivery(cursor, 10, "lease-token", True, "ok", "subject")
        self.assertIn("claim_token=%s", cursor.query)
        self.assertIn("status='sending'", cursor.query)
        self.assertEqual(cursor.params[-1], "lease-token")

    def test_claim_sql_refreshes_and_returns_fence_token(self):
        source_path = os.path.join(os.path.dirname(__file__), "..", "weekly_digest.py")
        with open(source_path, encoding="utf-8") as source_file:
            source = source_file.read()
        self.assertIn("claim_token = gen_random_uuid()", source)
        self.assertIn("RETURNING id, tracking_token, claim_token, attempts", source)
        self.assertEqual(source.count("stale sending lease expired%%"), 2)

    def test_report_claim_and_finish_are_fenced(self):
        cursor = _ReportClaimCursor()
        claim = digest._claim_report(cursor, date(2026, 9, 14))
        self.assertEqual(claim["claim_token"], "report-lease")
        self.assertIn("claim_token", cursor.query)
        self.assertIn("gen_random_uuid()", cursor.query)
        finish_cursor = _FinishCursor()
        digest._finish_report(finish_cursor, 22, "report-lease", True)
        self.assertIn("claim_token=%s", finish_cursor.query)
        self.assertIn("status='sending'", finish_cursor.query)
        self.assertEqual(finish_cursor.params[-1], "report-lease")

    def test_report_schema_has_fencing_token_migration(self):
        db_path = os.path.join(os.path.dirname(__file__), "..", "db.py")
        with open(db_path, encoding="utf-8") as source_file:
            source = source_file.read()
        self.assertIn("claim_token UUID NOT NULL DEFAULT gen_random_uuid()", source)
        self.assertIn("ALTER TABLE weekly_email_reports", source)

    @patch("weekly_digest.send_email")
    @patch("weekly_digest.build_html", side_effect=RuntimeError("personalization render"))
    def test_claimed_recipient_failure_is_finished_without_provider_call(
        self, _render, sender,
    ):
        cursor = _FinishCursor()
        ok, message = digest._send_claimed_recipient(
            _CommitConnection(), cursor,
            {"id": 4, "email": "member@example.test", "name": "회원"},
            {"id": 10, "tracking_token": "stable-token",
             "claim_token": "lease-token", "attempts": 1},
            "[subject]", [], {}, [], [], [], [], {}, None,
            "https://example.test/unsubscribe", 0, {}, date(2026, 9, 14), "tue",
        )
        self.assertFalse(ok)
        self.assertIn("personalization render", message)
        sender.assert_not_called()
        self.assertIn("claim_token=%s", cursor.query)

    def test_report_sql_uses_equal_seven_day_event_window(self):
        with open(digest.__file__, encoding="utf-8") as source_file:
            source = source_file.read()
        self.assertIn("first_opened_at <= sent_at + INTERVAL '7 days'", source)
        self.assertIn("first_clicked_at <= sent_at + INTERVAL '7 days'", source)
        self.assertIn("AS immature_sent", source)
        self.assertIn("AS any_sending", source)
        self.assertIn("stale sending lease expired; not retryable", source)
        self.assertIn("status='failed'", source)

    def test_email_target_validator_rejects_open_redirect_shapes(self):
        self.assertTrue(_email_target_is_safe("/building/12?q=x"))
        for target in ("https://evil.test/", "//evil.test/", r"/\\evil.test",
                       "/\x00evil", "javascript:alert(1)"):
            self.assertFalse(_email_target_is_safe(target), target)

    def test_tracking_routes_are_page_view_and_default_limit_exempt(self):
        with app_module.app.test_request_context("/email/open"):
            self.assertTrue(app_module._rate_limit_exempt())
            response = app_module.Response("ok", status=200)
            with patch.object(app_module, "_record_page_view") as recorder:
                app_module._log_page_view(response)
            recorder.assert_not_called()

    @patch("weekly_digest.company_email", return_value="admin@example.test")
    @patch("weekly_digest.send_email", return_value=(True, "발송 성공"))
    def test_admin_report_contains_counts_without_member_addresses(self, sender, _company):
        ok, _ = digest._send_admin_delivery_report(27, 26, 1)
        self.assertTrue(ok)
        recipient, subject, body = sender.call_args.args
        self.assertEqual(recipient, "admin@example.test")
        self.assertIn("성공 26건 / 실패 1건", subject)
        self.assertIn("발송 대상</th><td>27건", body)
        self.assertNotIn("member@", body)
        self.assertIn("idempotency_key", sender.call_args.kwargs)

    @patch("weekly_digest.company_email", return_value="admin@example.test")
    @patch("weekly_digest.send_email", return_value=(True, "발송 성공"))
    def test_admin_receives_same_weekly_digest_without_member_data(self, sender, _company):
        ok, _ = digest._send_admin_digest_copy(
            [], [], {"report_rate": 61.1}, {"title": "이번 주 기능", "episode": 5},
        )
        self.assertTrue(ok)
        recipient, subject, body = sender.call_args.args
        self.assertEqual(recipient, "admin@example.test")
        self.assertTrue(subject.startswith("[관리자 사본] [홈앤스테이]"))
        self.assertIn("관리자님", body)
        self.assertNotIn("member@", body)
        self.assertIn("weekly-digest-admin-copy-", sender.call_args.kwargs["idempotency_key"])

    @patch("weekly_digest.company_email", return_value="admin@example.test")
    @patch("weekly_digest.send_email", return_value=(True, "발송 성공"))
    def test_explicit_admin_resend_uses_a_new_idempotency_key(self, sender, _company):
        digest._send_admin_digest_copy([], [], {}, None, force_resend=True)
        key = sender.call_args.kwargs["idempotency_key"]
        self.assertIn("-resend-", key)

    def test_iso_week_cycles_through_eight_feature_episodes(self):
        self.assertEqual(digest._weekly_feature_episode(date(2026, 1, 1)), 1)
        self.assertEqual(digest._weekly_feature_episode(date(2026, 2, 19)), 8)
        self.assertEqual(digest._weekly_feature_episode(date(2026, 2, 26)), 1)

    @patch("weekly_digest._get_public_api_payload", side_effect=_public_api_payload)
    def test_datalab_summary_uses_only_public_homepage_responses(self, public_api):
        app_module = SimpleNamespace()
        summary = digest._get_datalab_summary(app_module)
        self.assertEqual(summary["report_rate"], 42.5)
        self.assertEqual(summary["price_change"]["building_name"], "상승 단지")
        self.assertEqual(summary["volume_top"]["deal_count"], 7)
        self.assertIsNone(summary["consumption_summary"])
        self.assertGreaterEqual(public_api.call_count, 3)

    @patch("weekly_digest._get_consumption_summary_db")
    @patch("weekly_digest._get_public_api_payload", side_effect=_public_api_payload)
    def test_public_homepage_summary_never_uses_consumption_db_fallback(
        self, _public_api, consumption_db,
    ):
        summary = digest._get_datalab_summary(SimpleNamespace())
        self.assertEqual(summary["report_rate"], 42.5)
        self.assertIsNone(summary["consumption_summary"])
        consumption_db.assert_not_called()

    def test_consumption_summary_uses_latest_two_nationwide_months(self):
        summary = digest._consumption_summary([
            {
                "sido_name": "전국", "ref_yearmonth": "2025-11",
                "metric_name": "지출액(천원)", "metric_value": 100000,
                "dimensions": {"중분류": "기타숙박"},
            },
            {
                "sido_name": "전국", "ref_yearmonth": "2025-12",
                "metric_name": "지출액(천원)", "metric_value": 125000,
                "dimensions": {"중분류": "기타숙박"},
            },
            {
                "sido_name": "전국", "ref_yearmonth": "2025-12",
                "metric_name": "지출액(천원)", "metric_value": 200000,
                "dimensions": {"중분류": "호텔"},
            },
            {
                "sido_name": "전국", "ref_yearmonth": "2025-12",
                "metric_name": "지출액(천원)", "metric_value": 300000,
                "dimensions": {"중분류": "캠핑장/펜션"},
            },
        ])
        self.assertEqual(summary["ref_yearmonth"], "2025-12")
        self.assertEqual(summary["amounts"]["호텔"], 200000)
        self.assertEqual(summary["amounts"]["캠핑장/펜션"], 300000)
        self.assertEqual(summary["other_lodging_mom"], 25.0)

    def test_consumption_summary_omits_missing_or_non_nationwide_rows(self):
        self.assertIsNone(digest._consumption_summary([]))
        self.assertIsNone(digest._consumption_summary([{
            "sido_name": "서울", "ref_yearmonth": "2025-12",
            "metric_name": "지출액(천원)", "metric_value": 100000,
            "dimensions": {"중분류": "기타숙박"},
        }]))

    def test_lightweight_consumption_query_isolates_latest_source_file(self):
        cursor = _ConsumptionCursor([
            {
                "ref_yearmonth": "2025-12", "category": "기타숙박",
                "metric_value": 125000,
            },
            {
                "ref_yearmonth": "2025-11", "category": "기타숙박",
                "metric_value": 100000,
            },
        ])
        with patch(
            "weekly_digest.get_conn",
            return_value=_ConsumptionConnection(cursor),
        ):
            summary = digest._get_consumption_summary_db()

        self.assertEqual(summary["amounts"]["기타숙박"], 125000)
        self.assertIn("WITH latest_source AS", cursor.query)
        self.assertIn("ORDER BY collected_at DESC, source_file DESC", cursor.query)
        self.assertEqual(
            cursor.query.count("JOIN latest_source l ON l.source_file = t.source_file"),
            2,
        )
        self.assertIn(
            "t.ref_yearmonth IN (SELECT ref_yearmonth FROM latest_months)",
            cursor.query,
        )

    @patch("weekly_digest._get_datalab_summary_db_fallback")
    @patch("weekly_digest._get_public_api_payload", return_value={})
    def test_public_api_unavailable_does_not_create_replacement_stats(
        self, _public_api, fallback,
    ):
        summary = digest._get_datalab_summary(SimpleNamespace())
        self.assertIsNone(summary["report_rate"])
        self.assertIsNone(summary["price_change"])
        self.assertIsNone(summary["volume_top"])
        fallback.assert_not_called()

    @patch("weekly_digest._get_public_api_payload", side_effect=RuntimeError("route failed"))
    def test_public_ranking_exception_becomes_no_new_transactions(self, _public_api):
        self.assertEqual(digest._get_public_homepage_ranking(SimpleNamespace()), ([], []))
        html = digest._zone2([], [])
        self.assertIn("최근 30일 거래 데이터가 없습니다", html)

    @patch("weekly_digest._get_public_api_payload")
    def test_public_ranking_warming_becomes_no_new_transactions(self, public_api):
        public_api.return_value = {
            "ok": False,
            "status": "warming",
            "price_highs": [],
            "most_traded": [],
        }
        self.assertEqual(digest._get_public_homepage_ranking(SimpleNamespace()), ([], []))

    @patch("weekly_digest._get_public_api_payload")
    def test_public_ranking_uses_existing_new_price_field(self, public_api):
        public_api.return_value = {
            "ok": True,
            "price_highs": [{"building_name": "신고가 단지", "new_price": 125000,
                             "pct_gain": 5.0}],
            "most_traded": [],
        }
        price_rows, _ = digest._get_public_homepage_ranking(SimpleNamespace())
        self.assertEqual(len(price_rows), 1)
        self.assertEqual(price_rows[0]["price"], 125000)
        self.assertEqual(price_rows[0]["new_price"], 125000)

    @patch("weekly_digest._get_public_api_payload")
    def test_malformed_public_ranking_rows_become_no_new_transactions(self, public_api):
        public_api.return_value = {
            "price_highs": [{}, {"building_name": "가격 없는 건물"}],
            "most_traded": [{}, {"building_name": "건수 없는 건물"}],
        }
        price_rows, volume_rows = digest._get_public_homepage_ranking(SimpleNamespace())
        self.assertEqual((price_rows, volume_rows), ([], []))
        html = digest.build_html(
            "테스터", [], {}, [], [], price_rows, volume_rows,
            {"report_rate": None, "price_change": None, "volume_top": None},
            None, "https://example.test/mypage",
        )
        self.assertIn("최근 30일 거래 데이터가 없습니다", html)

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
            {"report_rate": None, "price_change": None, "volume_top": None},
            None,
            "https://example.test/unsubscribe",
        )
        self.assertNotIn("미매칭 단지", html)

        html = digest.build_html(
            "테스터", [], {}, [], [],
            [{"building_name": "미매칭 단지", "pct_gain": 3.1}],
            [], {}, None, "https://example.test/unsubscribe", news_items=[],
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
        self.assertIn("매물 내놓기 — 제휴 중개법인 통해 수수료 0원", html)
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
        self.assertIn("실거래 없는 건물 (1곳):", html)
        self.assertIn("관심 단지", html)
        self.assertIn(
            f'href="{digest.SITE_URL}/mypage?utm_source=weekly&amp;utm_medium=email&amp;utm_campaign=no_signal_cta"',
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

    def test_report_rate_and_datalab_cards_are_not_rendered_in_weekly_email(self):
        email = digest.build_html(
            "테스터", [], {}, [], [], [], [],
            {
                "report_rate": 42.5,
                "price_change": {"building_name": "상승 단지", "change_percent": 9.8},
                "volume_top": {"building_id": 24, "building_name": "거래 단지", "deal_count": 7},
            },
            None, "https://example.test/mypage", news_items=[],
        )
        self.assertNotIn("42.5%", email)
        self.assertNotIn("영업신고율", email)
        self.assertNotIn("데이터랩 한눈에 보기", email)
        self.assertNotIn("weekly-datalab-cards", email)
        self.assertNotIn("거래 단지", email)

    def test_empty_zone4_is_omitted(self):
        html = digest.build_html(
            "테스터", [], {}, [], [], [], [],
            {"report_rate": None, "price_change": None, "volume_top": None},
            None, "https://example.test/mypage", news_items=[],
        )
        self.assertNotIn("데이터랩 한눈에 보기", html)
        self.assertNotIn("이번 주 기능 소개", html)

    def test_empty_rankings_are_omitted_instead_of_sending_blank_tables(self):
        html = digest.build_html(
            "테스터", [], {}, [], [], [], [],
            {"report_rate": None, "price_change": None, "volume_top": None},
            None, "https://example.test/mypage",
            period_start="2026-08-26", period_end="2026-09-24",
            news_items=[],
        )
        self.assertIn("최근 30일 시세 랭킹", html)
        self.assertIn("최근 30일 거래 데이터가 없습니다", html)
        self.assertIn("2026-08-26 — 2026-09-24", html)

    def test_admin_copy_explicitly_omits_personalized_sections(self):
        html = digest.build_html(
            "관리자", [], {}, [], [], [], [],
            {"report_rate": None, "price_change": None, "volume_top": None},
            None, "https://example.test/admin",
            include_personalized=False,
        )
        self.assertIn("관리자 검수본에는 회원별 관심단지와 의뢰 현황이 포함되지 않습니다", html)
        self.assertNotIn("관심단지를 등록하면 이런 알림을 받을 수 있어요", html)

    def test_out_of_range_public_report_rate_is_hidden_without_stopping_email(self):
        def payload(path, _app_module=None):
            if path == "/api/stats/consign-by-sido":
                return {"ok": True, "total": {"report_rate": 124.2}}
            return {}
        with patch("weekly_digest._get_public_api_payload", side_effect=payload):
            summary = digest._get_datalab_summary(SimpleNamespace())
        self.assertIsNone(summary["report_rate"])
        self.assertNotIn("quality_errors", summary)

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

    def test_zero_signal_favorites_still_render_and_keep_alert_off_hint(self):
        html = digest._zone1_1(
            [("저장한 건물", "주소", 321)], {}, {}, alert_off_count=4
        )
        self.assertIn("실거래 없는 건물 (1곳):", html)
        self.assertIn("저장한 건물", html)
        self.assertEqual(html.count("실거래 없는 건물"), 1)
        self.assertIn("관심단지 · 최신 실거래", html)
        self.assertIn("알림이 꺼진 관심단지가 4건", html)
        self.assertIn("관심단지 추가·알림 설정 확인", html)
        self.assertNotIn("이번 주 신호</th>", html)

    def test_favorite_recent_trades_precede_compact_no_trade_names(self):
        html = digest._zone1_1(
            [
                ("미거래 A", "주소 A", 1),
                ("거래 건물", "주소 B", 2),
                ("미거래 B", "주소 C", 3),
            ],
            {
                ("거래 건물", "주소 B"): {
                    "price": 12500, "deal_date": "2026-09-20", "building_id": 2,
                },
            },
            {"deal": 1},
            period_start="2026-08-26",
            period_end="2026-09-24",
        )
        self.assertLess(html.index("거래 건물"), html.index("실거래 없는 건물 (2곳):"))
        self.assertIn("2026-09-20", html)
        self.assertIn("1억 2,500만원", html)
        self.assertEqual(html.count("실거래 없는 건물"), 1)
        self.assertIn("미거래 A", html)
        self.assertIn("미거래 B", html)
        self.assertLess(html.index("미거래 A"), html.index("미거래 B"))
        self.assertIn('미거래 A</a>, <a', html)
        self.assertNotIn("상세 정보 준비 중", html)
        self.assertIn("2026-08-26", html)

    def test_no_trade_names_are_escaped(self):
        html = digest._zone1_1([("<가짜 & 단지>", "주소", None)], {})
        self.assertIn("&lt;가짜 &amp; 단지&gt;", html)
        self.assertNotIn("<가짜 & 단지>", html)

    def test_30_day_rankings_use_historical_max_and_exact_labeled_period(self):
        cursor = _RankingCursor([
            [{"building_id": 10, "building_name": "신고가", "price": 20000,
              "deal_date": "2026-09-24", "pct_gain": 10.0}],
            [{"building_id": 11, "building_name": "거래량", "deal_count": 4}],
        ])
        highs, volumes, period_start, period_end = digest._get_30_day_rankings(
            cursor, date(2026, 9, 24),
        )
        self.assertEqual((period_start, period_end), ("2026-08-26", "2026-09-24"))
        self.assertEqual(highs[0]["building_id"], 10)
        self.assertEqual(volumes[0]["deal_count"], 4)
        self.assertIn("historical_max AS", cursor.queries[0])
        self.assertIn("MAX(price) AS old_max", cursor.queries[0])
        self.assertIn("deal_date < %s", cursor.queries[0])
        self.assertIn("price > old_max", cursor.queries[0])
        self.assertIn("transaction_scope='unit'", cursor.queries[0])
        self.assertIn("LIMIT 5", cursor.queries[0])
        self.assertEqual(cursor.params[0], ("2026-08-26", "2026-08-26",
                                             "2026-09-24"))
        self.assertEqual(cursor.params[1], ("2026-08-26", "2026-09-24"))

    def test_verified_news_links_are_escaped_and_invalid_links_are_omitted(self):
        rendered = digest._zone_news([
            {"title": '정책 <속보> & 확인', "url": 'https://news.test/a?x="y"',
             "source": "<출처>", "published": "2026-09-24"},
            {"title": "가짜 링크", "url": "javascript:alert(1)"},
        ])
        self.assertIn("정책 &lt;속보&gt; &amp; 확인", rendered)
        self.assertIn('href="https://news.test/a?x=&quot;y&quot;"', rendered)
        self.assertIn("&lt;출처&gt;", rendered)
        self.assertIn("2026-09-24", rendered)
        self.assertNotIn("가짜 링크", rendered)
        empty = digest._zone_news([])
        self.assertIn("현재 확인된 원문 링크가 있는", empty)

    @patch("weekly_digest_news.get_recent_news", return_value=[])
    def test_digest_calls_news_provider_with_three_item_limit(self, get_news):
        self.assertEqual(digest._get_recent_news(), [])
        get_news.assert_called_once_with(limit=3)

    def test_digest_keeps_three_news_rows(self):
        news_items = [
            {
                "title": f"Hotel industry report {number}",
                "url": f"https://news.example/article-{number}",
                "source": "Publisher",
                "published": "2026-09-24",
            }
            for number in range(6)
        ]

        rendered = digest._zone_news(news_items)

        self.assertEqual(rendered.count("<tr>"), 3)
        self.assertEqual(rendered.count("<a href="), 3)
        self.assertNotIn("Hotel industry report 3", rendered)

    def test_untrusted_greeting_favorite_and_request_values_are_escaped(self):
        rendered = digest.build_html(
            '<img src=x onerror=alert(1)>',
            [('<script>favorite</script>', "주소", None)],
            {
                ("<script>favorite</script>", "주소"): {
                    "price": 10000, "deal_date": "2026-09-24",
                },
            },
            [{
                "building_name": '<script>request</script>',
                "status": '<img src=x onerror=alert(1)>',
            }],
            [],
            [], [], {}, None, "https://example.test/unsubscribe",
            news_items=[],
        )
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;님", rendered)
        self.assertIn("&lt;script&gt;favorite&lt;/script&gt;", rendered)
        self.assertIn("&lt;script&gt;request&lt;/script&gt;", rendered)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", rendered)
        self.assertNotIn("<script>", rendered)

    def test_30_day_deal_lookback_does_not_expand_other_weekly_alerts(self):
        with open(digest.__file__, encoding="utf-8") as source_file:
            source = source_file.read()
        user_personalization = source.split(
            "def _personalize_recipient", 1
        )[1].split("def _personalize_partner_recipient", 1)[0]
        partner_personalization = source.split(
            "def _personalize_partner_recipient", 1
        )[1].split("def _send_claimed_recipient", 1)[0]
        self.assertIn("deals_since or week_ago", user_personalization)
        self.assertIn("(uid, week_ago, favorite_ids)", user_personalization)
        self.assertIn("deals_since or week_ago", partner_personalization)

    def test_extreme_price_change_is_not_the_email_subject(self):
        extreme = {"price_change": {
            "building_name": "이상치", "change_percent": 478.8,
        }}
        self.assertEqual(
            digest._build_subject(0, extreme, {"title": "이번 주 기능"}),
            "[홈앤스테이] 이번 주 기능",
        )
        self.assertEqual(
            digest._build_subject(0, extreme, None),
            "[홈앤스테이] 이번 주 소식",
        )

    def test_listing_cta_restores_partner_no_fee_copy(self):
        self.assertIn(
            "매물 내놓기 — 제휴 중개법인 통해 수수료 0원",
            digest._zone1_2([], []),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)