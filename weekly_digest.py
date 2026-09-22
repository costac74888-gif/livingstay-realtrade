#!/usr/bin/env python3
"""
홈앤스테이 주간 소식 이메일 발송
===================================
대상  : weekly_email_enabled = TRUE 인 일반 회원 + 승인된 파트너
Zone 0   : 이번 주 핵심 수치 (데이터가 없으면 생략)
Zone 1-1 : 관심단지 신규 실거래 (없으면 CTA 버튼)
Zone 1-2 : 매물의뢰 / 매수의뢰 진행 현황 (없으면 CTA 버튼)
Zone 2   : 이번 주 시세 랭킹 — 신고가 TOP5, 거래량 TOP5
Zone 3   : 데이터랩 요약 — 전국 신고율, 가격변동·거래량 TOP1
Zone 4   : ISO 주차 기반 기능 소개 시리즈

실행:
  python weekly_digest.py                  # 전체 발송
  python weekly_digest.py --dry-run        # 발송 없이 로그만 출력
  python weekly_digest.py --user-id 4     # 특정 회원만 (테스트)
"""

import os
import sys
import argparse
import html
import hashlib
import logging
import re
import time
from datetime import date, datetime, timedelta
from urllib.parse import quote, urlparse
from zoneinfo import ZoneInfo

import psycopg2
import psycopg2.extras

from addr_norm import normalize_jibun_prefix, normalize_road_prefix
from email_util import send_email
from admin_action_center import company_email

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL", "")
_dev_domain  = os.environ.get("REPLIT_DEV_DOMAIN", "")
_fallback    = f"https://{_dev_domain}" if _dev_domain else "https://livingstay-realtrade.replit.app"
SITE_URL     = os.environ.get("SITE_URL", _fallback).rstrip("/")
KST = ZoneInfo("Asia/Seoul")
CLAIM_STALE_AFTER = timedelta(minutes=30)
MAX_DELIVERY_ATTEMPTS = 3
EXPERIMENT_START = date.fromisoformat(
    os.environ.get("WEEKLY_EMAIL_EXPERIMENT_START", "2026-09-15")
)


def kst_today(now=None):
    """오늘 날짜는 배치 서버의 로컬 timezone이 아닌 Asia/Seoul을 사용한다."""
    current = now or datetime.now(tz=KST)
    if current.tzinfo is None:
        current = current.replace(tzinfo=KST)
    return current.astimezone(KST).date()


def week_start_for(value):
    if isinstance(value, datetime):
        value = value.date()
    value = value if isinstance(value, date) else date.fromisoformat(str(value))
    return value - timedelta(days=value.weekday())


def cohort_for_user(user_id):
    """회원 ID 자체로 나누므로 실행 날짜나 DB 조회 순서에 영향을 받지 않는다."""
    return "tue" if int(user_id) % 2 == 0 else "thu"


def cohort_for_partner(partner_type, partner_id):
    """파트너 유형·ID를 stable digest로 나눈다 (Python hash() 금지)."""
    key = f"{str(partner_type).strip().lower()}:{int(partner_id)}".encode("utf-8")
    return "tue" if int.from_bytes(hashlib.sha256(key).digest()[:8], "big") % 2 == 0 else "thu"


def cohort_for_recipient(recipient_type, recipient_id):
    return cohort_for_user(recipient_id) if recipient_type == "user" else cohort_for_partner(
        recipient_type, recipient_id
    )


def experiment_week(value):
    """실험 시작 주를 1주차로 하는 ISO 주차(1..8, 그 밖은 None)."""
    current_week = week_start_for(value)
    start_week = week_start_for(EXPERIMENT_START)
    index = (current_week - start_week).days // 7 + 1
    return index if 1 <= index <= 8 else None


def scheduled_cohort(value=None):
    """화/목만 자동 발송하고, 다른 요일에는 None을 반환한다."""
    weekday = (value or kst_today()).weekday()
    return {1: "tue", 3: "thu"}.get(weekday)


def experiment_report_date():
    """보고서는 8주차 목요일 이후 7일 관찰창이 끝난 9주차 목요일부터 가능하다."""
    return week_start_for(EXPERIMENT_START) + timedelta(days=7 * 8 + 3)


def get_conn():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)


# ── 유틸 ──────────────────────────────────────────────────────────────────────

def _fmt_price(won_man):
    """만원 단위 정수 → '3억 2,500만원' 형태 문자열"""
    if not won_man:
        return "-"
    v = int(won_man)
    uk = v // 10000
    man = v % 10000
    if uk and man:
        return f"{uk:,}억 {man:,}만원"
    if uk:
        return f"{uk:,}억원"
    return f"{man:,}만원"


def _status_label(status):
    return {
        "submitted":  "신규접수",
        "consulting": "상담중",
        "matched":    "중개사 매칭완료",
        "completed":  "완료",
        "cancelled":  "취소",
    }.get(status or "", status or "-")


def _status_badge_style(status):
    ok_statuses = {"completed", "matched"}
    if status in ok_statuses:
        return "background:#EEF6E6;color:#4A7A18;"
    return "background:#FFF3CD;color:#856404;"


# ── DB 조회 ──────────────────────────────────────────────────────────────────


def _get_ranking(cur):
    """신고가 갱신 TOP5, 거래량 TOP5 (최근 7일)"""
    week_ago = (date.today() - timedelta(days=7)).isoformat()

    # 신고가 갱신: 이번 주 거래 중 해당 건물의 역대 최고가를 경신한 것.
    # building_id가 비어도 발송 직전 거래 식별자(sgg_cd·umd_nm·jibun)로 보정할 수
    # 있도록 거래 원본 키와 주소를 함께 반환한다.
    cur.execute("""
        WITH this_week AS (
            SELECT building_name, address, sgg_cd, umd_nm, jibun,
                   MAX(price) AS new_peak
            FROM transactions
            WHERE transaction_scope = 'unit' AND deal_date >= %s
            GROUP BY building_name, address, sgg_cd, umd_nm, jibun
        ),
        prev_peak AS (
            SELECT building_name, address, sgg_cd, umd_nm, jibun,
                   MAX(price) AS old_peak
            FROM transactions
            WHERE transaction_scope = 'unit' AND deal_date < %s
            GROUP BY building_name, address, sgg_cd, umd_nm, jibun
        )
        SELECT t.building_name, t.address, t.sgg_cd, t.umd_nm, t.jibun,
               t.new_peak AS price,
               (SELECT mb2.id FROM master_buildings mb2
                WHERE mb2.sgg_cd = t.sgg_cd
                  AND REPLACE(mb2.umd_nm, ' ', '') = REPLACE(t.umd_nm, ' ', '')
                  AND mb2.jibun = t.jibun
                ORDER BY mb2.id LIMIT 1)  AS building_id,
               ROUND((t.new_peak - COALESCE(p.old_peak, 0))::numeric
                     * 100.0 / NULLIF(COALESCE(p.old_peak, t.new_peak), 0), 1) AS pct_gain
        FROM this_week t
        LEFT JOIN prev_peak p
               ON p.building_name = t.building_name
              AND p.address = t.address
              AND p.sgg_cd = t.sgg_cd
              AND REPLACE(p.umd_nm, ' ', '') = REPLACE(t.umd_nm, ' ', '')
              AND p.jibun = t.jibun
        WHERE t.new_peak > COALESCE(p.old_peak, 0)
        ORDER BY pct_gain DESC NULLS LAST
        LIMIT 5
    """, (week_ago, week_ago))
    price_highs = cur.fetchall()

    # 거래량 TOP5 (최근 7일) — 위와 같이 거래 식별자를 유지한다.
    cur.execute("""
        SELECT t.building_name, t.address, t.sgg_cd, t.umd_nm, t.jibun,
               COUNT(*) AS deal_count,
               (SELECT mb2.id FROM master_buildings mb2
                WHERE mb2.sgg_cd = t.sgg_cd
                  AND REPLACE(mb2.umd_nm, ' ', '') = REPLACE(t.umd_nm, ' ', '')
                  AND mb2.jibun = t.jibun
                ORDER BY mb2.id LIMIT 1)  AS building_id
        FROM transactions t
        WHERE t.transaction_scope = 'unit' AND t.deal_date >= %s
        GROUP BY t.building_name, t.address, t.sgg_cd, t.umd_nm, t.jibun
        ORDER BY deal_count DESC
        LIMIT 5
    """, (week_ago,))
    most_traded = cur.fetchall()

    return price_highs, most_traded


def _weekly_feature_episode(today=None, series_length=8):
    """ISO 주차를 1~8회차 기능 소개 시리즈로 순환한다."""
    current = today or date.today()
    return ((current.isocalendar().week - 1) % series_length) + 1


_WEEKLY_FEATURE_TIP_DEFAULTS = [
    (1, "실거래가 무료조회", "로그인 없이 건물명만 입력하면 국토부 실거래가 바로 확인", "/"),
    (2, "관심단지 등록하면 실거래 알림이 와요", "매주 이메일로 자동 알림", "/"),
    (3, "데이터랩 숙박통계", "전국 생숙 건물수·호실수·신고율 한눈에", "/?datalab=lodging"),
    (4, "매물내놓기 제한공개", "영업 중인 사실 보호하며 조용히 매각 시작", "/guide#disclosure-guide"),
    (5, "방재고 관리", "객실별 상태·보증금·월세·채널·만기일 한 곳에서", "/guide#business-guide"),
    (6, "거래 체크리스트 14개 항목", "건물전체 매물 거래 전 필수 확인", "/guide"),
    (7, "보류 기능", "철회 없이 매물을 잠시 중단하는 방법", "/mypage"),
    (8, "영업신고현황", "시도별 생숙 신고율을 데이터랩에서 확인", "/?datalab=consign"),
]


def _get_active_feature_tip(cur, today=None):
    """기능 팁을 조회하고, 빈 테이블이면 보존형 초기 시드를 채운다."""
    try:
        cur.execute("""
            SELECT EXISTS (
                SELECT 1 FROM weekly_feature_tips
            ) AS has_rows
        """)
        has_rows = bool((cur.fetchone() or {}).get("has_rows"))
        if not has_rows:
            cur.executemany("""
                INSERT INTO weekly_feature_tips
                    (episode, title, body, cta_label, cta_url, is_active)
                VALUES (%s, %s, %s, '지금 바로 써보기 →', %s, TRUE)
                ON CONFLICT (episode) DO NOTHING
            """, _WEEKLY_FEATURE_TIP_DEFAULTS)
            cur.connection.commit()
            log.info("weekly_feature_tips 초기 데이터 8건을 등록했습니다.")

        episode = _weekly_feature_episode(today)
        cur.execute("""
            SELECT id, episode, title, body, cta_label, cta_url
            FROM weekly_feature_tips
            WHERE episode = %s AND is_active = TRUE
            LIMIT 1
        """, (episode,))
        row = cur.fetchone()
        return dict(row) if row else None
    except Exception:
        log.warning("기능 소개를 읽지 못했습니다. 해당 Zone을 생략합니다.", exc_info=True)
        try:
            cur.connection.rollback()
        except Exception:
            pass
        return None


def _consumption_summary(rows):
    """전국 관광소비 원본 행에서 이메일용 숙박 소비 요약을 만든다.

    원본은 ``dimensions['중분류']``에 업종을, ``metric_value``에 천원 단위
    지출액을 보관한다. 불완전한 업로드는 억지로 0으로 표시하지 않고 생략한다.
    """
    categories = ("기타숙박", "호텔", "캠핑장/펜션")
    monthly = {}
    for row in rows or []:
        try:
            dimensions = row.get("dimensions") or {}
            category = row.get("category") or dimensions.get("중분류")
            yearmonth = str(row.get("ref_yearmonth") or "").strip()
            metric_name = row.get("metric_name")
            sido_name = row.get("sido_name")
            if (
                category not in categories
                or not yearmonth
                or (metric_name is not None and metric_name != "지출액(천원)")
                or (sido_name is not None and sido_name != "전국")
            ):
                continue
            value = float(row.get("metric_value"))
        except (AttributeError, TypeError, ValueError):
            continue
        monthly.setdefault(yearmonth, {})[category] = value

    months = sorted(monthly, reverse=True)
    if not months:
        return None
    latest = months[0]
    amounts = monthly[latest]
    latest_other = amounts.get("기타숙박")
    previous_other = monthly.get(months[1], {}).get("기타숙박") if len(months) > 1 else None
    other_mom = None
    if latest_other is not None and previous_other not in (None, 0):
        other_mom = 100.0 * (latest_other - previous_other) / previous_other
    return {
        "ref_yearmonth": latest,
        "amounts": {category: amounts[category] for category in categories if category in amounts},
        "other_lodging_mom": other_mom,
    }


def _get_consumption_summary_db():
    """관광소비 블록만 위한 짧은 원본 조회. 원본이 없으면 조용히 생략한다."""
    conn = cur = None
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            WITH latest_source AS (
                SELECT source_file
                FROM tourism_stats
                WHERE stat_type = 'consumption_trend'
                ORDER BY collected_at DESC, source_file DESC
                LIMIT 1
            ),
            latest_months AS (
                SELECT t.ref_yearmonth
                FROM tourism_stats t
                JOIN latest_source l ON l.source_file = t.source_file
                WHERE t.stat_type = 'consumption_trend'
                  AND t.metric_name = '지출액(천원)'
                  AND t.sido_name = '전국'
                GROUP BY t.ref_yearmonth
                ORDER BY t.ref_yearmonth DESC
                LIMIT 2
            )
            SELECT t.ref_yearmonth, t.dimensions->>'중분류' AS category, t.metric_value
            FROM tourism_stats t
            JOIN latest_source l ON l.source_file = t.source_file
            WHERE t.stat_type = 'consumption_trend'
              AND t.metric_name = '지출액(천원)'
              AND t.sido_name = '전국'
              AND t.dimensions->>'중분류' IN ('기타숙박', '호텔', '캠핑장/펜션')
              AND t.ref_yearmonth IN (SELECT ref_yearmonth FROM latest_months)
            ORDER BY t.ref_yearmonth DESC
        """)
        return _consumption_summary(cur.fetchall())
    except Exception:
        return None
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def _get_datalab_summary_db_fallback():
    """캐시를 사용할 수 없을 때 주간 이메일이 직접 읽는 최소 통계."""
    empty = {
        "report_rate": None, "price_change": None, "volume_top": None,
        "consumption_summary": None,
    }
    conn = cur = None
    try:
        conn = get_conn()
        cur = conn.cursor()

        # 생활숙박 신고율은 원본 중복 제거·활성 생활업종 필터·건물별 호실수
        # cap이 모두 필요하다. 축약 계산은 같은 신고를 여러 건물에 더해 100%를
        # 넘길 수 있으므로 검증된 통계 섹션이 없을 때는 이 지표를 표시하지 않는다.
        report_rate = None

        # fallback ② 최근 30일 거래량 TOP1. 같은 이름의 다른 건물을 합치지 않고,
        # 이름·주소·거래 식별자를 함께 보존해 상세 링크를 안전하게 찾는다.
        cur.execute("""
            SELECT building_name, address, sgg_cd, umd_nm, jibun,
                   COUNT(*) AS deal_count
            FROM transactions
            WHERE transaction_scope = 'unit'
              AND deal_date >= TO_CHAR(NOW() - INTERVAL '30 days', 'YYYY-MM-DD')
              AND price > 0
            GROUP BY building_name, address, sgg_cd, umd_nm, jibun
            ORDER BY deal_count DESC
            LIMIT 1
        """)
        volume_row = cur.fetchone()

        # fallback ③ 최근 30일 동일 건물·주소·전용면적의 첫값 대비 최근값 TOP1
        cur.execute("""
            WITH grouped AS (
                SELECT
                    building_name,
                    address,
                    MIN(sgg_nm) AS sgg_nm,
                    sgg_cd,
                    umd_nm,
                    jibun,
                    COUNT(*) AS transaction_count,
                    (array_agg(price ORDER BY deal_date ASC, id ASC))[1] AS first_price,
                    (array_agg(price ORDER BY deal_date DESC, id DESC))[1] AS latest_price,
                    (array_agg(deal_date ORDER BY deal_date ASC, id ASC))[1] AS first_deal_date,
                    (array_agg(deal_date ORDER BY deal_date DESC, id DESC))[1] AS latest_deal_date,
                    area AS area_sqm
                FROM transactions
                WHERE transaction_scope = 'unit'
                  AND deal_date IS NOT NULL
                  AND deal_date >= TO_CHAR(CURRENT_DATE - INTERVAL '30 days', 'YYYY-MM-DD')
                  AND area > 0
                  AND price > 0
                GROUP BY building_name, address, sgg_cd, umd_nm, jibun, area
                HAVING COUNT(*) >= 2
            ),
            changed AS (
                SELECT *,
                       100.0 * (latest_price - first_price) / NULLIF(first_price, 0)
                         AS change_percent
                FROM grouped
            )
            SELECT
                building_name, address, sgg_nm, sgg_cd, umd_nm, jibun, transaction_count,
                first_price, latest_price, first_deal_date, latest_deal_date,
                area_sqm, change_percent,
                (SELECT id FROM master_buildings
                 WHERE sgg_cd = changed.sgg_cd
                   AND REPLACE(umd_nm, ' ', '') = REPLACE(changed.umd_nm, ' ', '')
                   AND jibun = changed.jibun
                 ORDER BY id LIMIT 1) AS building_id
            FROM changed
            WHERE change_percent > 0
            ORDER BY change_percent DESC, building_name, address, area_sqm
            LIMIT 1
        """)
        price_row = cur.fetchone()

        result = dict(empty)
        result["report_rate"] = report_rate
        if volume_row:
            result["volume_top"] = {
                "building_name": volume_row.get("building_name"),
                "address": volume_row.get("address"),
                "sgg_cd": volume_row.get("sgg_cd"),
                "umd_nm": volume_row.get("umd_nm"),
                "jibun": volume_row.get("jibun"),
                "deal_count": int(volume_row.get("deal_count") or 0),
            }
        if price_row:
            result["price_change"] = {
                "building_name": price_row.get("building_name"),
                "building_id": price_row.get("building_id"),
                "address": price_row.get("address"),
                "sgg_cd": price_row.get("sgg_cd"),
                "umd_nm": price_row.get("umd_nm"),
                "jibun": price_row.get("jibun"),
                "change_percent": round(float(price_row.get("change_percent")), 1),
            }
        result["consumption_summary"] = _get_consumption_summary_db()
        return result
    except Exception:
        log.warning("데이터랩 DB 폴백 집계에 실패했습니다.", exc_info=True)
        return empty
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def _get_datalab_summary(app_module=None):
    """통합 통계 원본 캐시에서 이메일용 최소 요약만 안전하게 꺼낸다.

    weekly_digest는 별도 프로세스로 실행되므로 최초에는 자기 프로세스의 캐시가
    비어 있다. 이 경우 app의 섹션 접근자를 한 번 호출해 통합 캐시를 채운 뒤 읽고,
    어떤 섹션이 실패해도 해당 지표만 None으로 남겨 이메일 발송은 계속한다.
    """
    empty = {
        "report_rate": None, "price_change": None, "volume_top": None,
        "consumption_summary": None,
    }
    cache_fill_failed = False
    try:
        if app_module is None:
            import app as app_module

        cache = getattr(app_module, "_MASTER_STATS_CACHE", {}) or {}
        if not (cache.get("data") or {}):
            section_reader = getattr(app_module, "_master_stats_section", None)
            if callable(section_reader):
                try:
                    section_reader("consign_stats")
                except Exception:
                    cache_fill_failed = True
            else:
                cache_fill_failed = True
            cache = getattr(app_module, "_MASTER_STATS_CACHE", {}) or {}
            if not (cache.get("data") or {}):
                cache_fill_failed = True

        data = cache.get("data") or {}
        sections = cache.get("sections") or {}

        def section_ok(name):
            return sections.get(name, {}).get("status") == "ok"

        result = dict(empty)
        if section_ok("consign_stats"):
            total = (data.get("consign_stats") or {}).get("total") or {}
            rate = total.get("report_rate")
            if rate is not None:
                rate = float(rate)
                if 0.0 <= rate <= 100.0:
                    result["report_rate"] = rate
                else:
                    result["quality_errors"] = [
                        f"전국 생숙 영업신고율 범위 오류: {rate:.1f}%"
                    ]

        if result["report_rate"] is None and not result.get("quality_errors"):
            report_reader = getattr(app_module, "_report_rate_by_sido_payload", None)
            if callable(report_reader):
                report_payload = report_reader() or {}
                rate = (report_payload.get("total") or {}).get("report_rate")
                if rate is not None:
                    rate = float(rate)
                    if 0.0 <= rate <= 100.0:
                        result["report_rate"] = rate
                    else:
                        result["quality_errors"] = [
                            f"전국 생숙 영업신고율 범위 오류: {rate:.1f}%"
                        ]

        if section_ok("transaction_stats"):
            transactions = data.get("transaction_stats") or {}
            price_items = (
                ((transactions.get("price_change") or {}).get("up") or {}).get("items")
                or []
            )
            volume_items = transactions.get("volume_top") or []
            result["price_change"] = dict(price_items[0]) if price_items else None
            result["volume_top"] = dict(volume_items[0]) if volume_items else None
        tourism_data = (
            data.get("consumption_trend")
            or (data.get("tourism_stats") or {}).get("consumption_trend")
            or (data.get("tourism") or {}).get("consumption_trend")
            or []
        )
        result["consumption_summary"] = (
            _consumption_summary(tourism_data)
            if tourism_data else _get_consumption_summary_db()
        )
        if cache_fill_failed:
            fallback = _get_datalab_summary_db_fallback()
            # 순위·관광소비는 가벼운 DB fallback을 쓰되, 신고율은 위에서 실행한
            # 중복제거·호실수 cap 적용 공식 집계값만 유지한다.
            fallback["report_rate"] = result.get("report_rate")
            if result.get("quality_errors"):
                fallback["quality_errors"] = result["quality_errors"]
            return fallback
        return result
    except Exception:
        log.warning("데이터랩 요약 캐시를 읽지 못했습니다. DB 폴백을 시도합니다.", exc_info=True)
        return _get_datalab_summary_db_fallback()


# ── 건물 링크 보정 ─────────────────────────────────────────────────────────────

def _compact(value):
    return "".join(str(value or "").split())


def _transaction_key(row):
    """거래의 법정동 식별자가 모두 있을 때만 매칭 키를 만든다."""
    sgg_cd = str(row.get("sgg_cd") or "").strip()
    umd_nm = _compact(row.get("umd_nm"))
    jibun = str(row.get("jibun") or "").strip()
    return (sgg_cd, umd_nm, jibun) if sgg_cd and umd_nm and jibun else None


def _address_keys(row):
    """도로명·지번 prefix를 함께 써서 표기 차이에도 같은 주소를 찾는다."""
    values = (
        row.get("address"),
        row.get("road_address"),
        row.get("jibun_address"),
    )
    keys = set()
    for value in values:
        if not value:
            continue
        for normalizer in (normalize_road_prefix, normalize_jibun_prefix):
            key = normalizer(value)
            if key:
                keys.add(key)
    return keys


def _valid_building_id(value):
    try:
        building_id = int(value)
    except (TypeError, ValueError):
        return None
    return building_id if building_id > 0 else None


def _resolve_building_ids(cur, rows):
    """이메일 행의 누락 building_id를 안전한 우선순위로 일괄 보정한다.

    거래 법정동 키가 가장 정확하고, 다음은 건물명+주소, 마지막은 전국에서 이름이
    하나뿐인 건물명이다. 어느 단계에서도 후보가 복수면 연결하지 않는다.
    """
    unresolved = []
    for row in rows:
        current_id = _valid_building_id(
            row.get("building_id") or row.get("master_building_id")
        )
        if current_id:
            row["building_id"] = current_id
            if "master_building_id" in row:
                row["master_building_id"] = current_id
        elif _compact(row.get("building_name")):
            unresolved.append(row)

    if not unresolved:
        return 0

    names = sorted({_compact(row.get("building_name")) for row in unresolved})
    transaction_keys = {
        _transaction_key(row) for row in unresolved if _transaction_key(row)
    }
    compact_addresses = {
        _compact(value)
        for row in unresolved
        for value in (row.get("address"), row.get("road_address"), row.get("jibun_address"))
        if _compact(value)
    }
    where_clauses = [
        "REPLACE(COALESCE(mb.building_name, ''), ' ', '') = ANY(%s)",
    ]
    params = [names]
    if transaction_keys:
        where_clauses.append(
            "CONCAT_WS(CHR(31), mb.sgg_cd, REPLACE(mb.umd_nm, ' ', ''), mb.jibun) = ANY(%s)"
        )
        params.append([CHR.join(key) for key in sorted(transaction_keys)])
    if compact_addresses:
        where_clauses.append(
            "(REPLACE(COALESCE(mb.road_address, ''), ' ', '') = ANY(%s) "
            "OR REPLACE(COALESCE(mb.jibun_address, ''), ' ', '') = ANY(%s))"
        )
        params.extend([sorted(compact_addresses), sorted(compact_addresses)])

    cur.execute(f"""
        SELECT mb.id, mb.building_name, mb.road_address, mb.jibun_address,
               mb.sgg_cd, mb.umd_nm, mb.jibun
        FROM master_buildings mb
        WHERE {' OR '.join(where_clauses)}
    """, params)
    candidates = [dict(row) for row in cur.fetchall()]
    for candidate in candidates:
        candidate["_name_key"] = _compact(candidate.get("building_name"))
        candidate["_transaction_key"] = _transaction_key(candidate)
        candidate["_address_keys"] = _address_keys(candidate)

    resolved = 0
    for row in unresolved:
        name_key = _compact(row.get("building_name"))
        tx_key = _transaction_key(row)
        address_keys = _address_keys(row)

        def unique_id(matches):
            ids = {candidate["id"] for candidate in matches}
            return next(iter(ids)) if len(ids) == 1 else None

        matches = []
        if tx_key:
            matches = [candidate for candidate in candidates
                       if candidate["_transaction_key"] == tx_key]
            if len(matches) > 1:
                named_matches = [candidate for candidate in matches
                                 if candidate["_name_key"] == name_key]
                matches = named_matches or matches

        building_id = unique_id(matches)
        if not building_id and address_keys:
            building_id = unique_id([
                candidate for candidate in candidates
                if candidate["_name_key"] == name_key
                and candidate["_address_keys"] & address_keys
            ])
        if not building_id:
            building_id = unique_id([
                candidate for candidate in candidates
                if candidate["_name_key"] == name_key
            ])

        if building_id:
            row["building_id"] = building_id
            if "master_building_id" in row:
                row["master_building_id"] = building_id
            resolved += 1

    if resolved != len(unresolved):
        log.warning(
            "주간 이메일 건물 상세 링크 %d/%d건을 보정하지 못했습니다. 이름은 링크 없이 표시합니다.",
            len(unresolved) - resolved, len(unresolved),
        )
    return resolved


CHR = chr(31)


# ── HTML 조립 ─────────────────────────────────────────────────────────────────

def _zone0(summary):
    """데이터랩 요약에서 이번 주 핵심 수치 하나를 보여준다."""
    summary = summary or {}
    rate = summary.get("report_rate")
    volume = summary.get("volume_top") or {}

    hero_value = hero_label = hero_href = None
    if rate is not None:
        try:
            hero_value = f"{float(rate):.1f}%"
            hero_label = "전국 생숙 영업신고율"
            hero_href = f"{SITE_URL}/?datalab=consign"
        except (TypeError, ValueError):
            pass

    if hero_value is None and volume.get("building_name"):
        volume_count = int(volume.get("deal_count") or 0)
        hero_value = _building_link(
            volume.get("building_id"),
            f"{volume.get('building_name')} {volume_count:,}건",
            "font-size:28px;line-height:1.2;font-weight:800;"
            "color:#B4863F;text-decoration:none;overflow-wrap:anywhere;",
        )
        hero_label = "최근 30일 거래량 TOP1"

    if hero_value is None:
        return ""

    if hero_href:
        hero_value_html = f"""
           <a href="{hero_href}"
              style="font-size:28px;line-height:1.2;font-weight:800;
                     color:#B4863F;text-decoration:none;overflow-wrap:anywhere;">
             {hero_value}
           </a>"""
    else:
        hero_value_html = hero_value

    return f"""
     <table width="100%" cellpadding="0" cellspacing="0" role="presentation"
            style="border-collapse:collapse;background:#F8F4EE;
                   border-left:4px solid #B4863F;">
       <tr>
         <td style="padding:17px 22px 16px;">
           {hero_value_html}
           <div style="font-size:11px;color:#888;margin-top:5px;">
             {hero_label}
           </div>
           <a href="{SITE_URL}/?datalab=lodging"
              style="display:inline-block;margin-top:9px;font-size:12px;
                     color:#8F6A2F;text-decoration:none;font-weight:700;">
             데이터랩 전체 보기 →
           </a>
         </td>
       </tr>
     </table>"""


def _bld_url(building_id):
    """검증된 ID에만 상세 페이지 URL을 만든다. 미매칭 행은 링크로 만들지 않는다."""
    building_id = _valid_building_id(building_id)
    return f"{SITE_URL}/building/{building_id}" if building_id else None


def _building_link(building_id, building_name, style):
    """건물명은 상세 링크로만 표시하고, 미매칭 이름을 홈 링크로 위장하지 않는다."""
    name = html.escape(str(building_name or "-"))
    if not building_name:
        return name
    url = _bld_url(building_id)
    if url:
        return f'<a href="{html.escape(url, quote=True)}" style="{style}">{name}</a>'
    return (
        f'<span style="{style}">{name}</span>'
        '<span style="display:block;margin-top:2px;font-size:11px;color:#999;'
        'font-weight:400;">상세 정보 준비 중</span>'
    )


def _zone1_1(favs, deals_by_fav, signal_counts=None, alert_off_count=0):
    """관심단지의 실거래·급매·신규매물·신고변동을 한 영역에 요약한다."""
    if not favs:
        return f"""
        <table width="100%" cellpadding="0" cellspacing="0">
          <tr>
            <td style="padding:18px;background:#FFFDF7;border-radius:8px;
                        border:1px solid #E8D9BB;">
              <p style="color:#7D4A00;font-size:15px;font-weight:700;
                        margin:0 0 10px;">
                📌 관심단지를 등록하면 이런 알림을 받을 수 있어요
              </p>
              <table cellpadding="0" cellspacing="0" style="margin:0 0 16px;">
                <tr><td style="padding:4px 0;color:#555;font-size:13px;">
                  ✅ &nbsp;새 실거래 발생 시 즉시 이메일
                </td></tr>
                <tr><td style="padding:4px 0;color:#555;font-size:13px;">
                  ✅ &nbsp;급매 등록 시 즉시 알림
                </td></tr>
                <tr><td style="padding:4px 0;color:#555;font-size:13px;">
                  ✅ &nbsp;숙박업 신고변동 (폐업·신규·호실수 변경)
                </td></tr>
                <tr><td style="padding:4px 0;color:#555;font-size:13px;">
                  ✅ &nbsp;매주 금요일 관심단지 요약 리포트
                </td></tr>
              </table>
              <a href="{SITE_URL}/?utm_source=weekly&utm_medium=email&utm_campaign=no_fav_cta"
                 style="display:inline-block;background:#B4863F;color:#fff;
                        text-decoration:none;padding:11px 26px;border-radius:6px;
                        font-size:14px;font-weight:700;letter-spacing:0.3px;">
                지금 관심단지 등록하기 →
              </a>
              <p style="margin:10px 0 0;font-size:11.5px;color:#999;">
                건물명 또는 주소 검색 후 ♡ 버튼을 누르면 등록됩니다.
              </p>
            </td>
          </tr>
        </table>"""

    signal_counts = signal_counts or {}
    total_signals = sum(int(v or 0) for v in signal_counts.values())
    if not total_signals:
        return f"""
        <p style="color:#555;font-size:14px;margin:0 0 8px;">
          이번 주 관심단지의 새로운 알림이 없었어요.
        </p>
        <p style="color:#888;font-size:12.5px;margin:0 0 12px;">
          관심단지를 더 추가하면 더 많은 알림을 받을 수 있어요.
        </p>
        <a href="{SITE_URL}/mypage?utm_source=weekly&utm_medium=email&utm_campaign=no_signal_cta"
           style="display:inline-block;background:#B4863F;color:#fff;
                  text-decoration:none;padding:10px 22px;border-radius:6px;
                  font-size:14px;font-weight:700;">
          관심단지 추가·알림 설정 확인 →
        </a>"""

    summary_rows = [
        ("새 실거래", signal_counts.get("deal", 0), "#B4863F"),
        ("🔥 급매", signal_counts.get("urgent", 0), "#C85A36"),
        ("신규매물", signal_counts.get("new_listing", 0), "#4A7A18"),
        ("신규신고", signal_counts.get("permit_new", 0), "#4A7A18"),
        ("폐업", signal_counts.get("permit_closed", 0), "#A44B4B"),
        ("영업상태 변경", signal_counts.get("permit_status", 0), "#6E5A9E"),
        ("호실수 변경", signal_counts.get("permit_room", 0), "#356D9A"),
    ]
    rows = "".join(
        f"""<tr>
          <td style="padding:8px 4px;border-bottom:1px solid #eee;color:#555;">{label}</td>
          <td style="padding:8px 4px;border-bottom:1px solid #eee;text-align:right;font-weight:700;color:{color};">{int(count or 0)}건</td>
        </tr>"""
        for label, count, color in summary_rows if int(count or 0) > 0
    )
    for bname, addr, mid in favs:
        deal = deals_by_fav.get((bname, addr))
        name_html = _building_link(
            mid or (deal and deal.get("building_id")),
            bname,
            "color:#16202E;font-weight:700;text-decoration:none;",
        )
        if deal:
            rows += f"""
            <tr>
              <td style="padding:8px 4px;border-bottom:1px solid #eee;vertical-align:top;">
                {name_html}
              </td>
              <td style="padding:8px 4px;border-bottom:1px solid #eee;text-align:right;
                         white-space:nowrap;font-weight:700;color:#B4863F;">
                {_fmt_price(deal['price'])}
              </td>
              <td style="padding:8px 4px;border-bottom:1px solid #eee;text-align:right;
                         white-space:nowrap;color:#888;font-size:12px;">
                {deal['deal_date']}
              </td>
            </tr>"""
        else:
            rows += f"""
            <tr>
              <td colspan="3" style="padding:8px 4px;border-bottom:1px solid #eee;color:#888;">
                {name_html}
                <span style="margin-left:8px;font-size:12px;">— 이번 주 새로운 실거래가 없었어요</span>
              </td>
            </tr>"""

    alert_off_hint = ""
    if alert_off_count > 0:
        mypage_url = f"{SITE_URL}/mypage"
        alert_off_hint = f"""
    <p style="margin:10px 0 0;font-size:12px;color:#B4863F;">
      🔔 알림이 꺼진 관심단지가 {alert_off_count}건 있어요 —
      <a href="{mypage_url}" style="color:#B4863F;font-weight:700;text-decoration:underline;">마이페이지에서 켜기 →</a>
    </p>"""

    return f"""
    <table style="width:100%;border-collapse:collapse;font-size:13px;">
      <thead>
        <tr>
          <th style="text-align:left;padding:6px 4px;color:#888;font-weight:600;
                     border-bottom:2px solid #eee;">이번 주 신호</th>
          <th style="text-align:right;padding:6px 4px;color:#888;font-weight:600;
                     border-bottom:2px solid #eee;">건수</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>{alert_off_hint}"""


def _zone1_2(listing_reqs, buy_reqs):
    """매물의뢰 / 매수의뢰 현황"""
    all_reqs = [("매물내놓기", r) for r in listing_reqs] + \
               [("매수의뢰",   r) for r in buy_reqs]

    if not all_reqs:
        return f"""
        <p style="color:#555;font-size:14px;margin:0 0 12px;">
          현재 진행 중인 의뢰가 없습니다.<br>
          건물을 찾아 매물 등록을 시작해 보세요.
        </p>
        <a href="{SITE_URL}/guide#listing-guide"
           style="display:inline-block;background:#B4863F;color:#fff;
                  text-decoration:none;padding:10px 22px;border-radius:6px;
                  font-size:14px;font-weight:700;">
          매물 등록 방법 확인하기 →
        </a>"""

    rows = ""
    for kind, r in all_reqs:
        name = r.get("building_name") or "-"
        name_html = _building_link(
            r.get("master_building_id") or r.get("building_id"),
            name,
            "color:#16202E;text-decoration:none;",
        )
        badge_style = _status_badge_style(r["status"])
        rows += f"""
        <tr>
          <td style="padding:8px 4px;border-bottom:1px solid #eee;font-size:12px;
                     color:#888;white-space:nowrap;">{kind}</td>
          <td style="padding:8px 4px;border-bottom:1px solid #eee;font-weight:700;">
            {name_html}
          </td>
          <td style="padding:8px 4px;border-bottom:1px solid #eee;">
            <span style="{badge_style}padding:2px 8px;border-radius:10px;
                          font-size:12px;font-weight:700;">
              {_status_label(r['status'])}
            </span>
          </td>
        </tr>"""

    return f"""
    <table style="width:100%;border-collapse:collapse;font-size:13px;">
      <thead>
        <tr>
          <th style="text-align:left;padding:6px 4px;color:#888;font-weight:600;
                     border-bottom:2px solid #eee;">구분</th>
          <th style="text-align:left;padding:6px 4px;color:#888;font-weight:600;
                     border-bottom:2px solid #eee;">건물</th>
          <th style="text-align:left;padding:6px 4px;color:#888;font-weight:600;
                     border-bottom:2px solid #eee;">상태</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>"""


def _zone2(price_highs, most_traded):
    """시세 랭킹"""
    if not price_highs and not most_traded:
        return ""

    def price_rows():
        if not price_highs:
            return "<tr><td colspan='3' style='padding:8px 4px;color:#888;font-size:13px;'>이번 주 신고가 갱신 건물이 없습니다.</td></tr>"
        html = ""
        for i, r in enumerate(price_highs, 1):
            name_html = _building_link(
                r.get("building_id"),
                r["building_name"],
                "color:#16202E;font-weight:700;text-decoration:none;",
            )
            gain = f"+{r['pct_gain']}%" if r.get("pct_gain") else ""
            html += f"""
            <tr>
              <td style="padding:6px 4px;border-bottom:1px solid #f0f0f0;
                         color:#aaa;width:20px;font-size:13px;">{i}</td>
              <td style="padding:6px 4px;border-bottom:1px solid #f0f0f0;font-size:13px;">
                {name_html}
              </td>
              <td style="padding:6px 4px;border-bottom:1px solid #f0f0f0;text-align:right;
                         color:#E53E3E;font-weight:700;white-space:nowrap;font-size:13px;">
                {gain}
              </td>
            </tr>"""
        return html

    def vol_rows():
        if not most_traded:
            return "<tr><td colspan='3' style='padding:8px 4px;color:#888;font-size:13px;'>이번 주 거래 데이터가 없습니다.</td></tr>"
        html = ""
        for i, r in enumerate(most_traded, 1):
            name_html = _building_link(
                r.get("building_id"),
                r["building_name"],
                "color:#16202E;font-weight:700;text-decoration:none;",
            )
            html += f"""
            <tr>
              <td style="padding:6px 4px;border-bottom:1px solid #f0f0f0;
                         color:#aaa;width:20px;font-size:13px;">{i}</td>
              <td style="padding:6px 4px;border-bottom:1px solid #f0f0f0;font-size:13px;">
                {name_html}
              </td>
              <td style="padding:6px 4px;border-bottom:1px solid #f0f0f0;text-align:right;
                         font-weight:700;white-space:nowrap;color:#B4863F;font-size:13px;">
                {r['deal_count']}건
              </td>
            </tr>"""
        return html

    return f"""
    <table style="width:100%;border-collapse:collapse;margin-bottom:20px;">
      <thead>
        <tr>
          <th colspan="3"
              style="text-align:left;padding:6px 4px;color:#16202E;font-size:13px;
                     font-weight:700;border-bottom:2px solid #eee;">
            🏆 신고가 갱신 TOP5
          </th>
        </tr>
      </thead>
      <tbody>{price_rows()}</tbody>
    </table>
    <table style="width:100%;border-collapse:collapse;">
      <thead>
        <tr>
          <th colspan="3"
              style="text-align:left;padding:6px 4px;color:#16202E;font-size:13px;
                     font-weight:700;border-bottom:2px solid #eee;">
            🔥 거래량 TOP5
          </th>
        </tr>
      </thead>
      <tbody>{vol_rows()}</tbody>
    </table>"""


def _zone3(summary):
     """데이터랩 원본 캐시의 전국 요약을 카드로 표시한다."""
     summary = summary or {}
     rate = summary.get("report_rate")
     price = summary.get("price_change") or {}
     volume = summary.get("volume_top") or {}
     consumption = summary.get("consumption_summary") or {}

     if rate is None and not price and not volume and not consumption:
         return ""

     rate_text = f"{float(rate):.1f}%" if isinstance(rate, (int, float)) else None
     if price:
         pct = price.get("change_percent")
         pct_text = f"{float(pct):+.1f}%" if pct is not None else "변동률 집계 중"
         price_text = (
             _building_link(
                 price.get("building_id"),
                 price.get("building_name") or "",
                 "color:#16202E;font-weight:800;text-decoration:none;"
                 "overflow-wrap:anywhere;",
             )
             + f'<br><span style="font-size:13px;color:#B4863F;">{pct_text}</span>'
         )
     else:
         price_text = None

     consign_url = html.escape(f"{SITE_URL}/?datalab=consign", quote=True)
     rate_link = (
         f'<a href="{consign_url}" '
         'style="color:#B4863F;font-weight:700;text-decoration:none;">'
         f'{rate_text}</a>'
     ) if rate_text else None

     if volume:
         volume_text = (
             _building_link(
                 volume.get("building_id"),
                 volume.get("building_name") or "",
                 "color:#16202E;font-weight:800;text-decoration:none;"
                 "overflow-wrap:anywhere;",
             )
             + f'<br><span style="font-size:13px;color:#B4863F;">'
             + f'{int(volume.get("deal_count") or 0):,}건</span>'
         )
     else:
         volume_text = None

     consumption_block = ""
     amounts = consumption.get("amounts") if isinstance(consumption, dict) else None
     if isinstance(amounts, dict) and amounts:
         entries = []
         display_amounts = [
             ("기타숙박", amounts.get("기타숙박")),
             ("호텔", amounts.get("호텔")),
             ("캠핑·펜션", amounts.get("캠핑장/펜션")),
         ]
         for category, amount in display_amounts:
             try:
                 if amount is None:
                     continue
                 amount_text = f"{float(amount) / 100000:,.0f}억원"
             except (TypeError, ValueError):
                 continue
             mom_text = ""
             if category == "기타숙박":
                 try:
                     mom = consumption.get("other_lodging_mom")
                     if mom is not None:
                         mom_value = float(mom)
                         mom_symbol = "▲" if mom_value > 0 else ("▼" if mom_value < 0 else "–")
                         mom_color = "#C23B32" if mom_value > 0 else ("#185FA5" if mom_value < 0 else "#888888")
                         mom_text = (
                             f' <span style="color:{mom_color};">'
                             f'전월比 {mom_symbol}{abs(mom_value):.1f}%</span>'
                         )
                 except (TypeError, ValueError):
                     pass
             entries.append(
                 f'<span style="white-space:nowrap;"><b>{html.escape(category)}</b> '
                 f'{html.escape(amount_text)}{mom_text}</span>'
             )
         if entries:
             raw_yearmonth = str(consumption.get("ref_yearmonth") or "").strip()
             month_match = re.fullmatch(r"(\d{4})[-.]?(\d{2})", raw_yearmonth)
             month_label = (
                 f"{month_match.group(1)}년 {int(month_match.group(2))}월"
                 if month_match else "최근"
             )
             ref_yearmonth = html.escape(month_label)
             tourism_url = html.escape(f"{SITE_URL}/?datalab=tourism_consume", quote=True)
             consumption_block = f"""
      <div style="margin:10px 4px 0;padding:10px 12px;background:#FFFFFF;
                  border:1px solid #EEEEEE;border-radius:8px;font-size:12px;
                  line-height:1.7;color:#555;">
        🏨 <strong style="color:#16202E;">{ref_yearmonth} 숙박 관광소비</strong><br>
        {' · '.join(entries)}
      </div>
      <p style="margin:6px 4px 0;text-align:right;">
        <a href="{tourism_url}" style="font-size:12px;color:#B4863F;text-decoration:none;">
          관광소비 열지도 보기 →
        </a>
      </p>"""

     cards = [
         ("영업신고율", rate_link),
         ("가격변동 TOP1", price_text),
         ("거래량 TOP1", volume_text),
     ]
     cards = [(label, value) for label, value in cards if value]

     def card(label, value):
         width = max(33, 100 // max(1, len(cards)))
         return f"""
         <td class="weekly-datalab-card-cell"
             width="{width}%"
             style="width:{width}%;vertical-align:top;padding:4px;min-width:0;">
           <table class="weekly-datalab-card" width="100%" cellpadding="0" cellspacing="0"
                  role="presentation"
                  style="width:100%;min-width:0;border:1px solid #EEEEEE;
                         border-radius:8px;background:#FFFFFF;">
             <tr>
               <td style="padding:12px 8px;text-align:center;min-width:0;">
                 <div style="font-size:11px;color:#888;margin-bottom:7px;">
                   {label}
                 </div>
                 <div style="font-size:18px;line-height:1.35;font-weight:800;
                             color:#B4863F;overflow-wrap:anywhere;word-break:break-word;">
                   {value}
                 </div>
               </td>
             </tr>
           </table>
         </td>"""

     return f"""
     <table class="weekly-datalab-cards" width="100%" cellpadding="0" cellspacing="0"
            role="presentation"
            style="width:100%;border-collapse:separate;border-spacing:0;
                   table-layout:fixed;font-size:13px;">
       <tr>
          {''.join(card(label, value) for label, value in cards)}
       </tr>
     </table>
      {consumption_block}
     <p style="margin:10px 0 0;text-align:right;">
       <a href="{SITE_URL}/?datalab=lodging"
          style="font-size:12px;color:#B4863F;text-decoration:none;">
         데이터랩 전체 보기 →
       </a>
     </p>"""


def _zone4(feature_tip):
    """활성 회차가 없으면 Zone 자체를 생략한다."""
    if not feature_tip:
        return ""

    title = html.escape(str(feature_tip.get("title") or "이번 주 기능 소개"))
    body = html.escape(str(feature_tip.get("body") or "")).replace("\n", "<br>")
    cta_label = html.escape(str(feature_tip.get("cta_label") or "기능 자세히 보기"))
    cta_suffix = "" if cta_label.endswith("→") else " →"
    cta_url = str(feature_tip.get("cta_url") or "").strip()
    href = cta_url if cta_url.startswith(("https://", "http://")) else f"{SITE_URL}{cta_url if cta_url.startswith('/') else '/'}"
    return f"""
    <p style="font-size:14px;font-weight:700;color:#16202E;margin:0 0 7px;">{title}</p>
    <p style="font-size:13px;color:#555;line-height:1.65;margin:0 0 13px;">{body}</p>
    <a href="{html.escape(href, quote=True)}"
       style="display:inline-block;background:#16202E;color:#fff;text-decoration:none;
              padding:9px 16px;border-radius:6px;font-size:13px;font-weight:700;">
       {cta_label}{cta_suffix}
    </a>"""


def _instrument_tracking(html_body, tracking_token):
    """회원별 링크를 opaque token redirect로 감싼다.

    외부 사이트 링크는 추적 대상으로 만들지 않는다. 내부 링크만 상대 경로로
    저장해 redirect가 임의의 외부 URL을 열 수 없게 한다. 이메일 open은
    프록시·캐시가 이미지를 대신 요청할 수 있어 근사치라는 점도 의도적으로
    문서화한다.
    """
    if not tracking_token:
        return html_body
    site = urlparse(SITE_URL)
    token = quote(str(tracking_token), safe="")

    def replace(match):
        raw = html.unescape(match.group(1))
        parsed = urlparse(raw)
        if parsed.path.rstrip("/") == "/unsubscribe":
            return match.group(0)
        if parsed.scheme or parsed.netloc:
            if parsed.netloc and parsed.netloc != site.netloc:
                return match.group(0)
            path = parsed.path or "/"
        elif raw.startswith("/") and not raw.startswith("//"):
            path = parsed.path or "/"
        else:
            return match.group(0)
        target = path
        if parsed.query:
            target += "?" + parsed.query
        if parsed.fragment:
            target += "#" + parsed.fragment
        redirect_url = (
            f"{SITE_URL}/email/click?token={token}&url="
            f"{quote(target, safe='')}"
        )
        return f'href="{html.escape(redirect_url, quote=True)}"'

    tracked = re.sub(r'href="([^"]+)"', replace, html_body, flags=re.IGNORECASE)
    pixel = (
        f'<img src="{SITE_URL}/email/open?token={token}" width="1" height="1" '
        'alt="" style="display:block;border:0;width:1px;height:1px;" />'
    )
    return tracked.replace("</body>", pixel + "</body>")


def build_html(user_name, favs, deals_by_fav,
                listing_reqs, buy_reqs,
               price_highs, most_traded,
               datalab_summary, feature_tip,
                 unsubscribe_url, alert_off_count=0, signal_counts=None,
                 tracking_token=None, include_personalized=True):
    z0  = _zone0(datalab_summary)
    z1  = _zone1_1(favs, deals_by_fav, signal_counts, alert_off_count)
    z12 = _zone1_2(listing_reqs, buy_reqs)
    z2  = _zone2(price_highs, most_traded)
    z3  = _zone3(datalab_summary)
    z4  = _zone4(feature_tip)

    personalized_blocks = f"""
  <tr>
    <td style="padding:20px 28px 0;">
      <h2 style="font-size:15px;font-weight:700;color:#16202E;margin:0 0 12px;
                 padding-bottom:8px;border-bottom:2px solid #B4863F;">
         📌 관심단지 숙박알리미
      </h2>
      {z1}
    </td>
  </tr>
  <tr>
    <td style="padding:20px 28px 0;">
      <h2 style="font-size:15px;font-weight:700;color:#16202E;margin:0 0 12px;
                 padding-bottom:8px;border-bottom:2px solid #B4863F;">
        📋 매물의뢰 진행 현황
      </h2>
      {z12}
    </td>
  </tr>""" if include_personalized else """
  <tr><td style="padding:16px 28px 0;">
    <div style="padding:12px;background:#F4F5F7;color:#666;font-size:12px;border-radius:6px;">
      관리자 검수본에는 회원별 관심단지와 의뢰 현황이 포함되지 않습니다.
    </div>
  </td></tr>"""

    zone2_block = f"""
  <tr>
    <td style="padding:20px 28px 0;">
      <h2 style="font-size:15px;font-weight:700;color:#16202E;margin:0 0 12px;
                 padding-bottom:8px;border-bottom:2px solid #B4863F;">
        📊 이번 주 시세 랭킹
      </h2>
      {z2}
    </td>
  </tr>""" if z2 else ""

    zone0_block = f"""
  <tr>
    <td style="padding:20px 28px 0;">
      {z0}
    </td>
  </tr>""" if z0 else ""

    zone3_block = f"""
  <tr>
    <td style="padding:20px 28px 0;background:#F8F4EE;">
      <h2 style="font-size:15px;font-weight:700;color:#16202E;margin:0 0 12px;
                 padding-bottom:8px;border-bottom:2px solid #B4863F;">
        📈 데이터랩 한눈에 보기
      </h2>
      {z3}
    </td>
  </tr>""" if z3 else ""

    zone4_block = f"""
  <tr>
    <td style="padding:20px 28px 0;background:#F0F4FF;">
      <h2 style="font-size:15px;font-weight:700;color:#16202E;margin:0 0 12px;
                 padding-bottom:8px;border-bottom:2px solid #B4863F;">
        ✨ 이번 주 기능 소개
      </h2>
      {z4}
    </td>
  </tr>""" if z4 else ""

    rendered = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>홈앤스테이 주간 소식</title>
<style>
@media only screen and (max-width:580px) {{
  .weekly-datalab-cards {{ table-layout:auto !important; }}
  .weekly-datalab-card-cell {{
    display:block !important;
    width:100% !important;
    padding:4px 0 !important;
  }}
  .weekly-datalab-card {{ width:100% !important; }}
}}
</style>
</head>
<body style="margin:0;padding:0;background:#f4f5f7;
             font-family:'Apple SD Gothic Neo','Noto Sans KR',sans-serif;">

<table width="100%" cellpadding="0" cellspacing="0"
       style="background:#f4f5f7;padding:24px 0;">
<tr><td align="center">

<table width="100%" style="max-width:580px;background:#fff;
       border-radius:12px;overflow:hidden;
       box-shadow:0 2px 12px rgba(0,0,0,0.08);">

  <!-- ── 헤더 ── -->
  <tr>
    <td style="background:#16202E;padding:20px 28px;text-align:center;">
      <a href="{SITE_URL}">
        <img src="{SITE_URL}/static/images/logo-email.png"
             alt="HOME &amp; STAY"
             width="180" height="auto"
             style="display:inline-block;height:auto;max-height:44px;border:0;" />
      </a>
       <p style="color:#9aa5b1;font-size:11px;margin:4px 0 0;
                 letter-spacing:.04em;">주간 소식</p>
       <p style="color:#B4863F;font-size:11px;font-weight:700;
                 margin:4px 0 0;letter-spacing:.02em;">
         대한민국 숙박부동산 데이터 플랫폼
       </p>
    </td>
  </tr>

  <!-- ── 인사말 ── -->
  <tr>
    <td style="padding:24px 28px 0;">
      <p style="font-size:15px;font-weight:700;color:#16202E;margin:0 0 4px;">
        {user_name}님, 이번 주 홈앤스테이 소식을 전달해드려요.
      </p>
      <p style="font-size:13px;color:#888;margin:0;">
         실거래부터 영업현황·매물·중개·운영·금융까지 — 이번 주 소식을 전달해드려요.
      </p>
    </td>
  </tr>

  {zone0_block}

  {personalized_blocks}
  {zone2_block}

  {zone3_block}
  {zone4_block}

  <!-- ── 푸터 ── -->
  <tr>
    <td style="padding:20px 28px 24px;">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td style="padding-top:16px;border-top:1px solid #eee;text-align:center;">
            <p style="font-size:11px;color:#B4863F;font-weight:700;
                      margin:0 0 4px;text-align:center;">
              대한민국 숙박부동산 데이터 플랫폼
            </p>
            <p style="font-size:11px;color:#aaa;margin:0 0 4px;">
              홈앤스테이 | 사업자등록번호 301-41-68319
            </p>
            <p style="font-size:11px;color:#aaa;margin:0;">
              이 메일은 홈앤스테이 회원가입 시 동의하신 주간 소식 수신 설정에 따라 발송됩니다.
              <a href="{unsubscribe_url}" style="color:#aaa;text-decoration:underline;">수신거부</a>
            </p>
          </td>
        </tr>
      </table>
    </td>
  </tr>

</table>
</td></tr>
</table>
</body>
</html>"""
    return _instrument_tracking(rendered, tracking_token)


def _build_subject(new_deal_count, datalab_summary, feature_tip):
    """관심단지 실거래 → 가격변동 TOP1 → 기능 팁 → 기본 제목 순서."""
    if new_deal_count:
        headline = f"관심단지 {new_deal_count}곳 새 실거래"
    else:
        price = (datalab_summary or {}).get("price_change") or {}
        if price.get("building_name"):
            pct = price.get("change_percent")
            pct_text = f" {float(pct):+.1f}%" if pct is not None else ""
            headline = f"가격변동 TOP1 | {price['building_name']}{pct_text}"
        elif feature_tip and feature_tip.get("title"):
            headline = str(feature_tip["title"])
        else:
            headline = "이번 주 소식"
    return f"[홈앤스테이] {headline}"


def _claim_delivery(cur, user_id, week_start, cohort, recipient_type="user"):
    """한 수신자·주차를 원자적으로 선점한다. sent는 절대 갱신하지 않는다.

    user 경로는 기존 SQL/원장과 완전히 호환하고, 파트너는 owner FK와
    recipient_type을 함께 기록한다.
    """
    if recipient_type != "user":
        owner_column = {
            "agent": "agent_id", "operator": "operator_id",
            "loan_consultant": "loan_consultant_id",
        }.get(recipient_type)
        if not owner_column:
            raise ValueError("unknown recipient type")
        cur.execute(
            f"""
            INSERT INTO weekly_email_deliveries
                ({owner_column}, recipient_type, week_start, cohort, status,
                 attempts, claimed_at, claim_token)
            VALUES (%s, %s, %s, %s, 'sending', 1, NOW(), gen_random_uuid())
            ON CONFLICT DO NOTHING
            RETURNING id, tracking_token, claim_token, attempts
            """,
            (user_id, recipient_type, week_start, cohort),
        )
        claim = cur.fetchone()
        if claim:
            return claim
        # Existing failed/stale rows are reclaimed with the same fence rules.
        cur.execute(
            f"""
            UPDATE weekly_email_deliveries
               SET status='sending', attempts=attempts + 1, claimed_at=NOW(),
                   failed_at=NULL, error_message=NULL,
                   claim_token=gen_random_uuid(), updated_at=NOW()
             WHERE {owner_column}=%s AND recipient_type=%s AND week_start=%s
               AND status <> 'sent'
               AND ((status='failed' AND COALESCE(error_message,'')
                     NOT LIKE 'stale sending lease expired%%' AND attempts < %s)
                OR (status='sending' AND claimed_at < NOW() -
                    (%s * INTERVAL '1 minute') AND attempts < %s))
             RETURNING id, tracking_token, claim_token, attempts
            """,
            (user_id, recipient_type, week_start, MAX_DELIVERY_ATTEMPTS,
             int(CLAIM_STALE_AFTER.total_seconds() // 60), MAX_DELIVERY_ATTEMPTS),
        )
        return cur.fetchone()
    cur.execute(
        """
        INSERT INTO weekly_email_deliveries
            (user_id, week_start, cohort, status, attempts, claimed_at, claim_token)
        VALUES (%s, %s, %s, 'sending', 1, NOW(), gen_random_uuid())
        ON CONFLICT ON CONSTRAINT weekly_email_deliveries_user_id_week_start_key DO UPDATE
           SET status = 'sending', attempts = weekly_email_deliveries.attempts + 1,
               claimed_at = NOW(), failed_at = NULL, error_message = NULL,
               claim_token = gen_random_uuid(),
               updated_at = NOW()
         WHERE weekly_email_deliveries.status <> 'sent'
           AND ((weekly_email_deliveries.status = 'failed'
                 AND COALESCE(weekly_email_deliveries.error_message, '')
                      NOT LIKE 'stale sending lease expired%%'
                 AND weekly_email_deliveries.attempts < %s)
             OR (weekly_email_deliveries.status = 'sending'
                 AND weekly_email_deliveries.claimed_at <
                     NOW() - (%s * INTERVAL '1 minute')
                 AND weekly_email_deliveries.attempts < %s))
        RETURNING id, tracking_token, claim_token, attempts
        """,
        (user_id, week_start, cohort, MAX_DELIVERY_ATTEMPTS,
         int(CLAIM_STALE_AFTER.total_seconds() // 60), MAX_DELIVERY_ATTEMPTS),
    )
    return cur.fetchone()


def _finish_delivery(cur, delivery_id, claim_token, ok, message=None, subject=None):
    """수락된 메일만 sent로 확정하고, 실패는 재시도 가능한 원장으로 남긴다."""
    if ok:
        cur.execute(
            """UPDATE weekly_email_deliveries
               SET status='sent', sent_at=NOW(), subject=COALESCE(%s, subject),
                   error_message=NULL, updated_at=NOW()
             WHERE id=%s AND claim_token=%s AND status='sending'""",
            (subject, delivery_id, claim_token),
        )
    else:
        cur.execute(
            """UPDATE weekly_email_deliveries
               SET status='failed', failed_at=NOW(), subject=COALESCE(%s, subject),
                   error_message=%s, updated_at=NOW()
             WHERE id=%s AND claim_token=%s AND status='sending'""",
            (subject, str(message or "email delivery failed")[:500], delivery_id, claim_token),
        )
    return cur.rowcount == 1


def calculate_experiment_report(rows):
    """DB 행을 개인정보 없이 cohort별 8주 실험 요약으로 변환한다."""
    result = {}
    for cohort in ("tue", "thu"):
        subset = [r for r in rows if r.get("cohort") == cohort]
        targeted = len(subset)
        sent = sum(1 for r in subset if r.get("status") == "sent")
        failed = sum(1 for r in subset if r.get("status") == "failed")
        # SQL report rows alias the seven-day-window booleans as these fields.
        # Keeping the aliases also makes this calculator useful in pure tests.
        opens = sum(1 for r in subset if int(r.get("open_count") or 0) > 0)
        clicks = sum(1 for r in subset if int(r.get("click_count") or 0) > 0)
        attempts = sum(int(r.get("attempts") or 0) for r in subset)
        result[cohort] = {
            "targeted": targeted, "sent": sent, "failed": failed,
            "unique_opens": opens, "unique_clicks": clicks,
            "open_rate": opens / sent if sent else 0.0,
            "click_rate": clicks / sent if sent else 0.0,
            "attempts": attempts,
        }
    return result


def _choose_experiment_winner(metrics):
    """클릭률 우선, 동률일 때 오픈률, 완전 동률은 tue를 선택한다."""
    tue, thu = metrics["tue"], metrics["thu"]
    return "tue" if (tue["click_rate"], tue["open_rate"]) >= (
        thu["click_rate"], thu["open_rate"]
    ) else "thu"


def _claim_report(cur, experiment_start):
    key = f"weekly-email-ab-{experiment_start.isoformat()}"
    cur.execute(
        """
        INSERT INTO weekly_email_reports
            (experiment_start, report_key, status, attempts, claimed_at, claim_token)
        VALUES (%s, %s, 'sending', 1, NOW(), gen_random_uuid())
        ON CONFLICT (report_key) DO UPDATE
           SET status='sending', attempts=weekly_email_reports.attempts + 1,
               claimed_at=NOW(), claim_token=gen_random_uuid(),
               error_message=NULL, updated_at=NOW()
         WHERE (weekly_email_reports.status='failed')
            OR (weekly_email_reports.status='sending'
                AND weekly_email_reports.claimed_at < NOW() - INTERVAL '30 minutes')
        RETURNING id, claim_token, attempts
        """,
        (experiment_start, key),
    )
    return cur.fetchone()


def _finish_report(cur, report_id, claim_token, ok, message=None):
    if ok:
        cur.execute(
            """UPDATE weekly_email_reports
                  SET status='sent', sent_at=NOW(), updated_at=NOW(),
                      error_message=NULL
                WHERE id=%s AND claim_token=%s AND status='sending'""",
            (report_id, claim_token),
        )
    else:
        cur.execute(
            """UPDATE weekly_email_reports
                  SET status='failed', error_message=%s, updated_at=NOW()
                WHERE id=%s AND claim_token=%s AND status='sending'""",
            (str(message or "report failed")[:500], report_id, claim_token),
        )
    return cur.rowcount == 1


def _send_experiment_report(conn, today):
    """8주차 목요일부터 보고서를 확인한다. 실패 원장만 다음 목요일 재시도한다."""
    if today.weekday() != 3:
        return False, "not report day"
    start_week = week_start_for(EXPERIMENT_START)
    if today < experiment_report_date():
        return False, "experiment incomplete"
    cur = conn.cursor()
    # A provider timeout is ambiguous after the lease has been stale for
    # longer than the claim window. Fence that old worker and make the row
    # terminal rather than retrying outside the provider's idempotency window.
    cur.execute(
        """
        UPDATE weekly_email_deliveries
           SET status='failed', failed_at=NOW(),
               error_message='stale sending lease expired; not retryable',
               claimed_at=NULL, claim_token=gen_random_uuid(), updated_at=NOW()
         WHERE week_start >= %s AND week_start < %s
           AND status='sending'
           AND (claimed_at IS NULL
                OR claimed_at < NOW() - INTERVAL '30 minutes')
        """,
        (start_week, start_week + timedelta(days=56)),
    )
    cur.execute(
        """
        SELECT
          EXISTS (
            SELECT 1
              FROM weekly_email_deliveries
             WHERE week_start >= %s AND week_start < %s
               AND status = 'sent'
               AND (sent_at IS NULL OR sent_at + INTERVAL '7 days' > NOW())
          ) AS immature_sent,
          EXISTS (
            SELECT 1
              FROM weekly_email_deliveries
             WHERE week_start >= %s AND week_start < %s
               AND status = 'sending'
          ) AS any_sending
        """,
        (start_week, start_week + timedelta(days=56),
         start_week, start_week + timedelta(days=56)),
    )
    readiness = cur.fetchone() or {}
    if readiness.get("immature_sent") or readiness.get("any_sending"):
        conn.rollback()
        return False, "pending"
    claim = _claim_report(cur, start_week)
    if not claim:
        conn.commit()
        return False, "already sent or exhausted"
    cur.execute(
        """SELECT cohort, status, attempts,
                      CASE WHEN status='sent'
                                AND first_opened_at IS NOT NULL
                                AND first_opened_at >= sent_at
                                AND first_opened_at <= sent_at + INTERVAL '7 days'
                           THEN 1 ELSE 0 END AS open_count,
                      CASE WHEN status='sent'
                                AND first_clicked_at IS NOT NULL
                                AND first_clicked_at >= sent_at
                                AND first_clicked_at <= sent_at + INTERVAL '7 days'
                           THEN 1 ELSE 0 END AS click_count
             FROM weekly_email_deliveries
            WHERE week_start >= %s AND week_start < %s""",
        (start_week, start_week + timedelta(days=56)),
    )
    rows = [dict(r) for r in cur.fetchall()]
    metrics = calculate_experiment_report(rows)
    winner = _choose_experiment_winner(metrics)
    parts = [
        "<div style=\"font-family:sans-serif\"><h2>주간 이메일 A/B 실험 결과</h2>",
        "<p>회원 이메일 주소와 user_id를 포함하지 않은 집계 보고서입니다.</p>",
    ]
    for cohort in ("tue", "thu"):
        m = metrics[cohort]
        parts.append(
            f"<h3>{cohort.upper()} cohort</h3><p>"
            f"대상 {m['targeted']} / 성공 {m['sent']} / 실패 {m['failed']} · "
            f"오픈 {m['unique_opens']} ({m['open_rate']:.1%}) · "
            f"클릭 {m['unique_clicks']} ({m['click_rate']:.1%}) · "
            f"시도 {m['attempts']}</p>"
        )
    parts.append(f"<p>우승 cohort: <strong>{winner.upper()}</strong></p></div>")
    # Re-check the fenced report lease directly before the provider call.
    cur.execute(
        """SELECT id FROM weekly_email_reports
            WHERE id=%s AND claim_token=%s AND status='sending'
            FOR UPDATE""",
        (claim["id"], claim["claim_token"]),
    )
    if not cur.fetchone():
        conn.rollback()
        return False, "report claim was fenced by another worker"
    ok, message = send_email(
        company_email(),
        "[홈앤스테이] 주간 이메일 A/B 실험 8주 결과",
        "".join(parts),
        idempotency_key=f"weekly-email-ab-report-{start_week.isoformat()}",
    )
    finished = _finish_report(
        cur, claim["id"], claim["claim_token"], ok, message,
    )
    conn.commit()
    if not finished:
        return False, "report claim was fenced by another worker"
    return ok, message


def _run_report_only(today):
    """Post-window scheduled invocations never create member/admin deliveries."""
    conn = get_conn()
    try:
        ok, message = _send_experiment_report(conn, today)
        log.info("8주 실험 보고서 전용 실행: %s", message)
        return 0 if ok or message in {"already sent or exhausted", "pending"} else 1
    finally:
        conn.close()


def _send_admin_delivery_report(target_count, sent, errors, test=False, cohort=None):
    """회원별 주소를 노출하지 않는 주간 발송 결과를 회사 문의 이메일로 보낸다."""
    now = datetime.now().astimezone()
    title = "테스트" if test else "주간 이메일 발송 결과"
    subject = f"[홈앤스테이 관리자] {title} — 성공 {sent}건 / 실패 {errors}건"
    body = f"""
    <div style="font-family:'Apple SD Gothic Neo','Malgun Gothic',sans-serif;line-height:1.65;color:#222">
      <h2 style="margin:0 0 16px">홈앤스테이 {html.escape(title)}</h2>
      <p>실행시각: {html.escape(now.strftime('%Y-%m-%d %H:%M:%S %Z'))}</p>
      <table style="border-collapse:collapse">
        <tr><th style="text-align:left;padding:7px 18px 7px 0">발송 대상</th><td>{int(target_count):,}건</td></tr>
        <tr><th style="text-align:left;padding:7px 18px 7px 0">발송 성공</th><td>{int(sent):,}건</td></tr>
        <tr><th style="text-align:left;padding:7px 18px 7px 0">발송 실패</th><td>{int(errors):,}건</td></tr>
      </table>
      <p style="color:#777;font-size:12px">개인정보 보호를 위해 회원 이메일 주소는 보고서에 포함하지 않습니다.</p>
    </div>"""
    cohort_key = cohort or "all"
    return send_email(
        company_email(),
        subject,
        body,
        idempotency_key=(
            f"weekly-digest-admin-test-{now:%Y%m%d%H%M}"
            if test else f"weekly-digest-admin-{now:%G-W%V}-{cohort_key}"
        ),
    )


def _send_admin_digest_copy(
    price_highs, most_traded, datalab_summary, feature_tip, force_resend=False,
    cohort=None,
):
    """개인 회원 데이터 없이 공통 주간 이메일 본문을 관리자에게도 보낸다."""
    subject = "[관리자 사본] " + _build_subject(0, datalab_summary, feature_tip)
    body = build_html(
        "관리자", [], {}, [], [],
        price_highs, most_traded,
        datalab_summary, feature_tip,
        f"{SITE_URL}/admin", 0,
        signal_counts={},
        include_personalized=False,
    )
    now = datetime.now().astimezone()
    cohort = cohort or scheduled_cohort(kst_today()) or "manual"
    idempotency_key = f"weekly-digest-admin-copy-{now:%G-W%V}-{cohort}"
    if force_resend:
        idempotency_key += f"-resend-{now:%Y%m%d%H%M%S}"
    return send_email(
        company_email(),
        subject,
        body,
        idempotency_key=idempotency_key,
    )


def _personalize_recipient(cur, user, week_ago):
    """Load one member's digest data; callers can fail this recipient only."""
    uid = user["id"]
    recipient_type = user.get("recipient_type", "user")
    cur.execute("""
        SELECT uf.building_name, uf.address,
               COALESCE(uf.master_building_id, bid.id, bid2.id) AS master_building_id
        FROM user_favorites uf
        LEFT JOIN LATERAL (
            SELECT mb.id FROM transactions t2
            JOIN master_buildings mb ON mb.sgg_cd=t2.sgg_cd AND mb.umd_nm=t2.umd_nm
             AND mb.jibun=t2.jibun
            WHERE ((uf.building_name IS NULL AND t2.building_name IS NULL)
                   OR t2.building_name=uf.building_name)
              AND t2.address=uf.address
            ORDER BY (mb.building_name=uf.building_name) DESC NULLS LAST, mb.id LIMIT 1
        ) bid ON TRUE
        LEFT JOIN LATERAL (
            SELECT mb.id FROM master_buildings mb
            WHERE mb.road_address=uf.address
               OR REPLACE(mb.umd_nm || mb.jibun, ' ', '')=REPLACE(uf.address, ' ', '')
            ORDER BY (mb.building_name=uf.building_name) DESC NULLS LAST, mb.id LIMIT 1
        ) bid2 ON TRUE
        WHERE uf.user_id=%s ORDER BY uf.created_at DESC, uf.id DESC
    """, (uid,))
    favorite_rows = [dict(r) for r in cur.fetchall()]
    _resolve_building_ids(cur, favorite_rows)
    favs = [(r["building_name"], r["address"], r["master_building_id"])
            for r in favorite_rows]

    alert_off_count = 0
    if favs:
        cur.execute("""
            SELECT COUNT(*) AS cnt FROM (
                SELECT building_name, address FROM user_favorites WHERE user_id=%s
                EXCEPT
                SELECT building_name, address FROM user_alert_subscriptions WHERE user_id=%s
            ) sub
        """, (uid, uid))
        alert_off_count = (cur.fetchone() or {}).get("cnt", 0) or 0

    deals_by_fav = {}
    if favs:
        names, addresses = [f[0] for f in favs], [f[1] for f in favs]
        cur.execute("""
            SELECT DISTINCT ON (t.building_name, t.address)
                   t.building_name, t.address, t.price, t.deal_date,
                   t.sgg_cd, t.umd_nm, t.jibun, mb.id AS building_id
              FROM transactions t
              LEFT JOIN master_buildings mb ON mb.sgg_cd=t.sgg_cd
               AND REPLACE(mb.umd_nm, ' ', '')=REPLACE(t.umd_nm, ' ', '')
               AND mb.jibun=t.jibun
             WHERE t.building_name=ANY(%s) AND t.address=ANY(%s)
               AND t.transaction_scope='unit' AND t.deal_date >= %s
             ORDER BY t.building_name, t.address, t.deal_date DESC
        """, (names, addresses, week_ago))
        valid = {(f[0], f[1]) for f in favs}
        deals_by_fav = {
            (r["building_name"], r["address"]): dict(r)
            for r in cur.fetchall()
            if (r["building_name"], r["address"]) in valid
        }

    signal_counts = {
        "deal": len(deals_by_fav), "urgent": 0, "new_listing": 0,
        "permit_new": 0, "permit_closed": 0, "permit_status": 0, "permit_room": 0,
    }
    favorite_ids = [f[2] for f in favs if f[2] is not None]
    if favorite_ids:
        cur.execute("""
            SELECT COALESCE(ul.tier, '') AS tier, COUNT(*) AS cnt
              FROM urgent_listing_alert_logs ul
              JOIN listing_requests lr ON lr.id=ul.listing_request_id
             WHERE ul.user_id=%s AND ul.created_at >= %s
               AND lr.master_building_id=ANY(%s)
             GROUP BY COALESCE(ul.tier, '')
        """, (uid, week_ago, favorite_ids))
        for row in cur.fetchall():
            if row["tier"] in ("gold", "silver", "urgent"):
                signal_counts["urgent"] += int(row["cnt"] or 0)
        cur.execute("""
            SELECT COUNT(*) AS cnt FROM new_listing_alert_logs nl
            JOIN listing_requests lr ON lr.id=nl.listing_request_id
            WHERE nl.user_id=%s AND nl.created_at >= %s
              AND lr.master_building_id=ANY(%s)
        """, (uid, week_ago, favorite_ids))
        signal_counts["new_listing"] = int((cur.fetchone() or {}).get("cnt") or 0)
        cur.execute("""
            SELECT pcl.change_summary
              FROM permit_change_alert_deliveries pcd
              JOIN permit_change_alert_logs pcl ON pcl.id=pcd.permit_change_alert_log_id
             WHERE pcd.user_id=%s AND pcd.created_at >= %s
               AND pcl.master_building_id=ANY(%s)
        """, (uid, week_ago, favorite_ids))
        for row in cur.fetchall():
            summary = dict(row.get("change_summary") or {})
            for source_key, target_key in (
                ("new", "permit_new"), ("closed", "permit_closed"),
                ("status", "permit_status"), ("room", "permit_room"),
            ):
                signal_counts[target_key] += int(summary.get(source_key) or 0)

    cur.execute("""
        SELECT lr.id, lr.status, lr.master_building_id, mb.building_name
          FROM listing_requests lr LEFT JOIN master_buildings mb ON mb.id=lr.master_building_id
         WHERE lr.user_id=%s AND lr.status NOT IN ('cancelled','completed')
         ORDER BY lr.created_at DESC LIMIT 5
    """, (uid,))
    listing_reqs = [dict(r) for r in cur.fetchall()]
    cur.execute("""
        SELECT br.id, br.status, br.master_building_id, mb.building_name
          FROM buy_requests br LEFT JOIN master_buildings mb ON mb.id=br.master_building_id
         WHERE br.user_id=%s AND br.status NOT IN ('cancelled','completed')
         ORDER BY br.created_at DESC LIMIT 5
    """, (uid,))
    buy_reqs = [dict(r) for r in cur.fetchall()]
    _resolve_building_ids(cur, [*deals_by_fav.values(), *listing_reqs, *buy_reqs])
    n_deals = sum(1 for f in favs if deals_by_fav.get((f[0], f[1])))
    return {
        "favs": favs, "deals_by_fav": deals_by_fav,
        "listing_reqs": listing_reqs, "buy_reqs": buy_reqs,
        "alert_off_count": alert_off_count, "signal_counts": signal_counts,
        "new_deal_count": n_deals,
    }


def _personalize_partner_recipient(cur, partner, week_ago):
    """파트너 관심단지 UNION 활성 담당 단지뱃지 범위만 개인화한다."""
    kind = partner["recipient_type"]
    owner_column = {
        "agent": "agent_id", "operator": "operator_id",
        "loan_consultant": "loan_consultant_id",
    }[kind]
    assigned_table = {
        "agent": "agent_buildings", "operator": "operator_buildings",
        "loan_consultant": "loan_consultant_buildings",
    }[kind]
    cur.execute(
        f"""
        WITH scope AS (
            SELECT master_building_id
              FROM partner_favorites
             WHERE {owner_column}=%s
            UNION
            SELECT master_building_id
              FROM {assigned_table}
             WHERE {owner_column}=%s
               AND has_priority_badge=TRUE
               AND (premium_expires_at IS NULL OR premium_expires_at > NOW())
        )
        SELECT mb.id AS master_building_id, mb.building_name,
               COALESCE(mb.road_address, mb.jibun, mb.sgg_text) AS address
          FROM scope s JOIN master_buildings mb ON mb.id=s.master_building_id
         ORDER BY mb.building_name, mb.id
        """,
        (partner["id"], partner["id"]),
    )
    scoped = [dict(r) for r in cur.fetchall()]
    favs = [(r["building_name"], r["address"], r["master_building_id"]) for r in scoped]
    deals_by_fav = {}
    building_ids = [r["master_building_id"] for r in scoped]
    if building_ids:
        cur.execute(
            """
            WITH candidates AS (
                SELECT mb.id AS building_id,
                       t.id AS transaction_id, t.building_name, t.address, t.price, t.deal_date,
                       t.sgg_cd, t.umd_nm, t.jibun,
                       (
                           SELECT COUNT(*)
                             FROM master_buildings mb_loc
                            WHERE mb_loc.sgg_cd=t.sgg_cd
                              AND REPLACE(mb_loc.umd_nm, ' ', '') =
                                  REPLACE(t.umd_nm, ' ', '')
                              AND mb_loc.jibun=t.jibun
                       ) AS location_match_count,
                       regexp_replace(COALESCE(t.building_name, ''), E'\\s+', '', 'g')
                           AS transaction_building_name,
                       regexp_replace(COALESCE(mb.building_name, ''), E'\\s+', '', 'g')
                           AS master_building_name
                  FROM transactions t
                  JOIN master_buildings mb
                    ON mb.id=ANY(%s)
                   AND mb.sgg_cd=t.sgg_cd
                   AND REPLACE(mb.umd_nm, ' ', '')=REPLACE(t.umd_nm, ' ', '')
                   AND mb.jibun=t.jibun
                 WHERE t.transaction_scope='unit'
                   AND t.deal_date >= %s
            )
            SELECT DISTINCT ON (building_id) building_id,
                   t.building_name, t.address, t.price, t.deal_date,
                   t.sgg_cd, t.umd_nm, t.jibun
              FROM candidates t
             WHERE (
                       t.transaction_building_name <> ''
                   AND t.transaction_building_name=t.master_building_name
                   )
                OR t.location_match_count=1
             ORDER BY building_id, t.deal_date DESC, t.transaction_id DESC
            """,
            (building_ids, week_ago),
        )
        deals_by_id = {int(r["building_id"]): dict(r) for r in cur.fetchall()}
        deals_by_fav = {
            (f[0], f[1]): deals_by_id[f[2]]
            for f in favs if f[2] in deals_by_id
        }
    return {
        "favs": favs, "deals_by_fav": deals_by_fav,
        "listing_reqs": [], "buy_reqs": [], "alert_off_count": 0,
        "signal_counts": {
            "deal": len(deals_by_fav), "urgent": 0, "new_listing": 0,
            "permit_new": 0, "permit_closed": 0, "permit_status": 0, "permit_room": 0,
        },
        "new_deal_count": len(deals_by_fav),
    }


def _send_claimed_recipient(
    conn, cur, user, delivery, subject, favs, deals_by_fav, listing_reqs,
    buy_reqs, price_highs, most_traded, datalab_summary, feature_tip,
    unsubscribe_url, alert_off_count, signal_counts, week_start, cohort,
    recipient_type=None,
):
    """Render/send one already-claimed recipient and fence every DB mutation."""
    uid = user["id"]
    recipient_type = recipient_type or user.get("recipient_type", "user")
    try:
        html_body = build_html(
            user["name"], favs, deals_by_fav, listing_reqs, buy_reqs,
            price_highs, most_traded, datalab_summary, feature_tip,
            unsubscribe_url, alert_off_count, signal_counts=signal_counts,
            tracking_token=delivery["tracking_token"],
        )
        # 수신거부가 claim 이후에 발생한 경우 provider 제출 직전에 다시
        # 확인한다. 테스트용 최소 커서에는 조회 API가 없으므로 생략한다.
        if hasattr(cur, "fetchone"):
            if recipient_type == "user":
                eligibility_sql = (
                    "SELECT NOT (weekly_email_enabled IS FALSE "
                    "AND updated_weekly_email_at IS NOT NULL) AS enabled "
                    "FROM users WHERE id=%s AND COALESCE(status, 'active') <> 'withdrawn'"
                )
                eligibility_params = (uid,)
            else:
                owner_table = {
                    "agent": "agents", "operator": "operators",
                    "loan_consultant": "loan_consultants",
                }.get(recipient_type)
                eligibility_sql = (
                    f"SELECT NOT (weekly_email_enabled IS FALSE "
                    f"AND weekly_email_updated_at IS NOT NULL) AS enabled FROM {owner_table} "
                    "WHERE id=%s AND status='approved'"
                )
                eligibility_params = (uid,)
            cur.execute(eligibility_sql, eligibility_params)
            eligibility = cur.fetchone()
            if not eligibility or not eligibility.get("enabled"):
                _finish_delivery(
                    cur, delivery["id"], delivery["claim_token"],
                    False, "recipient is no longer eligible",
                )
                conn.commit()
                return False, "recipient is no longer eligible"
        cur.execute(
            """UPDATE weekly_email_deliveries
                  SET subject=%s, updated_at=NOW()
                WHERE id=%s AND claim_token=%s AND status='sending'""",
            (subject, delivery["id"], delivery["claim_token"]),
        )
        if cur.rowcount != 1:
            conn.rollback()
            return False, "delivery claim was fenced by another worker"
        conn.commit()
        ok = False
        msg = ""
        remaining = max(1, MAX_DELIVERY_ATTEMPTS - int(delivery["attempts"]) + 1)
        for retry_no in range(remaining):
            outcome = send_email(
                user["email"], subject, html_body,
                # tracking_token is stable across failed/stale claims and is
                # also the provider idempotency key.
                idempotency_key=f"weekly-email-{delivery['tracking_token']}",
                detailed=True,
            )
            if len(outcome) == 3:
                ok, msg, provider_outcome = outcome
            else:
                ok, msg = outcome
                provider_outcome = "accepted" if ok else "definitive_failure"
            accepted = bool(ok or provider_outcome == "accepted")
            finished = _finish_delivery(
                cur, delivery["id"], delivery["claim_token"],
                accepted, msg, subject,
            )
            conn.commit()
            if not finished:
                return False, "delivery claim was fenced by another worker"
            if accepted:
                return True, msg
            if retry_no + 1 < remaining:
                time.sleep(min(2 ** retry_no, 2))
                delivery = _claim_delivery(
                    cur, uid, week_start, cohort, recipient_type,
                )
                conn.commit()
                if not delivery:
                    return False, "delivery claim unavailable for retry"
        return False, msg
    except Exception as exc:
        # The recipient owns this exact lease; an old worker cannot mark a
        # newer claim failed because _finish_delivery fences on claim_token.
        try:
            _finish_delivery(
                cur, delivery["id"], delivery["claim_token"],
                False, str(exc),
            )
            conn.commit()
        except Exception:
            conn.rollback()
        return False, str(exc)


def _get_weekly_recipients(cur, selected_cohort, target_uid=None):
    """일반회원과 승인된 파트너를 같은 발송 입력 형태로 정규화한다."""
    cur.execute(
        """
        SELECT 'user' AS recipient_type, id, email,
               COALESCE(name, email) AS name,
               COALESCE(unsubscribe_token::text, '') AS unsubscribe_token,
               COALESCE(weekly_email_enabled, FALSE) AS weekly_email_enabled
          FROM users
         WHERE NOT (
                   weekly_email_enabled IS FALSE
                   AND updated_weekly_email_at IS NOT NULL
               )
           AND email IS NOT NULL AND email <> ''
           AND COALESCE(status, 'active') <> 'withdrawn'
           AND (%s IS NULL OR id=%s)
        UNION ALL
        SELECT 'agent', id, email, COALESCE(owner_name, email),
               COALESCE(weekly_unsubscribe_token::text, ''),
               weekly_email_enabled
          FROM agents
         WHERE NOT (
                   weekly_email_enabled IS FALSE
                   AND weekly_email_updated_at IS NOT NULL
               )
           AND status='approved'
           AND email IS NOT NULL AND email <> ''
           AND %s IS NULL
        UNION ALL
        SELECT 'operator', id, email, COALESCE(owner_name, email),
               COALESCE(weekly_unsubscribe_token::text, ''),
               weekly_email_enabled
          FROM operators
         WHERE NOT (
                   weekly_email_enabled IS FALSE
                   AND weekly_email_updated_at IS NOT NULL
               )
           AND status='approved'
           AND email IS NOT NULL AND email <> ''
           AND %s IS NULL
        UNION ALL
        SELECT 'loan_consultant', id, email, COALESCE(owner_name, email),
               COALESCE(weekly_unsubscribe_token::text, ''),
               weekly_email_enabled
          FROM loan_consultants
         WHERE NOT (
                   weekly_email_enabled IS FALSE
                   AND weekly_email_updated_at IS NOT NULL
               )
           AND status='approved'
           AND email IS NOT NULL AND email <> ''
           AND %s IS NULL
        ORDER BY recipient_type, id
        """,
        (target_uid, target_uid, target_uid, target_uid, target_uid),
    )
    rows = []
    for raw in cur.fetchall():
        row = dict(raw)
        # Keep provider input conservative; malformed addresses are excluded
        # without logging the PII value.
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", str(row.get("email") or "")):
            continue
        row["cohort"] = cohort_for_recipient(row["recipient_type"], row["id"])
        if row["cohort"] == selected_cohort:
            rows.append(row)
    return rows


# ── 메인 ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="홈앤스테이 주간 소식 이메일 발송")
    parser.add_argument("--dry-run",  action="store_true", help="발송 없이 로그만 출력")
    parser.add_argument("--user-id",  type=int, default=None, help="특정 회원 ID (테스트용)")
    parser.add_argument("--test-admin-report", action="store_true",
                        help="회원 발송 없이 관리자 결과 보고 테스트메일만 발송")
    parser.add_argument("--admin-copy", action="store_true",
                        help="회원 발송 없이 관리자 주간 이메일 사본만 발송")
    parser.add_argument("--force-resend", action="store_true",
                        help="관리자 사본의 동일 주차 중복 방지를 해제해 명시적으로 재발송")
    parser.add_argument("--cohort", choices=("tue", "thu"),
                        help="발송 cohort (tue=짝수 회원, thu=홀수 회원)")
    parser.add_argument("--scheduled", action="store_true",
                        help="Asia/Seoul 기준 화·목에 해당 cohort만 발송")
    args = parser.parse_args()

    dry_run    = args.dry_run
    target_uid = args.user_id
    today      = kst_today()
    if args.test_admin_report:
        ok, msg = _send_admin_delivery_report(1, 1, 0, test=True)
        log.info("관리자 테스트 보고: %s", msg)
        return 0 if ok else 1
    is_manual_preview = target_uid is not None
    if not is_manual_preview:
        if today < week_start_for(EXPERIMENT_START):
            log.info("A/B 실험 시작 전이라 주간 이메일을 발송하지 않습니다.")
            return 0
        if today >= experiment_report_date():
            if args.scheduled and today.weekday() == 3:
                return _run_report_only(today)
            log.info("A/B 실험 기간이 끝나 주간 회원 발송을 건너뜁니다.")
            return 0
        if experiment_week(today) is None:
            log.info("A/B 실험 주차가 아니므로 주간 이메일을 발송하지 않습니다.")
            return 0
    selected_cohort = args.cohort
    if args.scheduled or (target_uid is None and not args.cohort):
        selected_cohort = selected_cohort or scheduled_cohort(today)
        if not selected_cohort:
            log.info("오늘은 주간 이메일 발송일이 아닙니다 (Asia/Seoul).")
            return 0
    elif target_uid is not None and selected_cohort is None:
        selected_cohort = cohort_for_user(target_uid)
    week_ago   = (today - timedelta(days=7)).isoformat()
    week_start = week_start_for(today)

    conn = get_conn()
    try:
        cur = conn.cursor()

        # 공통 데이터 (전체 회원이 동일하게 받음)
        price_highs, most_traded = _get_ranking(cur)
        # _get_datalab_summary()는 별도 DB 연결을 사용한다. 운영 스키마 DDL이
        # 대기 중일 때 첫 연결의 ACCESS SHARE 잠금을 계속 쥐고 있으면,
        # 두 번째 연결이 DDL 뒤에서 기다리는 교착성 잠금 대기가 생긴다.
        # 순위 조회는 읽기 전용이므로 여기서 트랜잭션을 끝내 잠금을 해제한다.
        conn.commit()
        datalab_summary          = _get_datalab_summary()
        quality_errors = (datalab_summary or {}).get("quality_errors") or []
        if quality_errors:
            for quality_error in quality_errors:
                log.error("[품질검증 실패] %s", quality_error)
            log.error("잘못된 공통 지표가 포함되어 이번 주 이메일 발송을 중단합니다.")
            return 1
        feature_tip              = _get_active_feature_tip(cur)
        _resolve_building_ids(
            cur,
            [
                *price_highs,
                *most_traded,
                *[
                    item for item in (
                        (datalab_summary or {}).get("price_change"),
                        (datalab_summary or {}).get("volume_top"),
                    )
                    if item
                ],
            ],
        )

        if args.admin_copy:
            ok, msg = _send_admin_digest_copy(
                price_highs, most_traded, datalab_summary, feature_tip,
                force_resend=args.force_resend,
            )
            log.info("관리자 주간 이메일 사본: %s", msg)
            return 0 if ok else 1

        # 일반회원과 승인된 파트너를 동일한 발송 입력으로 정규화한다.
        users = _get_weekly_recipients(cur, selected_cohort, target_uid)
        log.info("발송 대상 %d명(일반회원+파트너)", len(users))

        sent = errors = 0
        for user in users:
            uid   = user["id"]
            recipient_type = user.get("recipient_type", "user")
            email = user["email"]
            name  = user["name"]
            delivery = None
            subject = None
            try:
                if not dry_run:
                    delivery = _claim_delivery(
                        cur, uid, week_start, selected_cohort, recipient_type,
                    )
                    conn.commit()
                    if not delivery:
                        log.info("  - %s (이미 발송됨/다른 작업자가 처리 중)", email)
                        continue
                personalized = (
                    _personalize_recipient(cur, user, week_ago)
                    if recipient_type == "user"
                    else _personalize_partner_recipient(cur, user, week_ago)
                )
                subject = _build_subject(
                    personalized["new_deal_count"],
                    datalab_summary, feature_tip,
                )
                unsubscribe_token = user.get("unsubscribe_token") or ""
                if unsubscribe_token and recipient_type != "user":
                    unsubscribe_url = (
                        f"{SITE_URL}/unsubscribe?type={quote(recipient_type)}"
                        f"&token={quote(unsubscribe_token)}"
                    )
                else:
                    unsubscribe_url = (
                        f"{SITE_URL}/unsubscribe?token={unsubscribe_token}"
                        if unsubscribe_token else f"{SITE_URL}/mypage"
                    )
                if dry_run:
                    log.info(
                        "  [DRY-RUN] %s | 관심단지 %d개(신규실거래 %d건) | "
                        "의뢰 listing=%d buy=%d | 데이터랩 신고율=%s | 기능팁=%s",
                        f"{recipient_type}:{uid}", len(personalized["favs"]),
                        personalized["new_deal_count"],
                        len(personalized["listing_reqs"]),
                        len(personalized["buy_reqs"]),
                        datalab_summary.get("report_rate"),
                        feature_tip.get("episode") if feature_tip else "-",
                    )
                    sent += 1
                    continue

                ok, msg = _send_claimed_recipient(
                    conn, cur, user, delivery, subject,
                    personalized["favs"], personalized["deals_by_fav"],
                    personalized["listing_reqs"], personalized["buy_reqs"],
                    price_highs, most_traded, datalab_summary, feature_tip,
                    unsubscribe_url, personalized["alert_off_count"],
                    personalized["signal_counts"], week_start, selected_cohort,
                    recipient_type=recipient_type,
                )
            except Exception as exc:
                conn.rollback()
                ok, msg = False, str(exc)
                if delivery:
                    try:
                        _finish_delivery(
                            cur, delivery["id"], delivery["claim_token"],
                            False, msg, subject,
                        )
                        conn.commit()
                    except Exception:
                        conn.rollback()
            if dry_run:
                if not ok:
                    errors += 1
                    log.warning("  [DRY-RUN] ✗ %s — %s", email, msg)
                continue
            if ok:
                sent += 1
                log.info("  ✓ %s", email)
            else:
                errors += 1
                log.warning("  ✗ %s — %s", email, msg)

    finally:
        conn.close()

    log.info("완료: 발송=%d, 오류=%d", sent, errors)
    if not dry_run and target_uid is None:
        copy_ok, copy_msg = _send_admin_digest_copy(
            price_highs, most_traded, datalab_summary, feature_tip,
            cohort=selected_cohort,
        )
        if copy_ok:
            log.info("관리자 주간 이메일 사본 발송 완료")
        else:
            log.warning("관리자 주간 이메일 사본 발송 실패 — %s", copy_msg)
        report_ok, report_msg = _send_admin_delivery_report(
            len(users), sent, errors, cohort=selected_cohort,
        )
        if report_ok:
            log.info("관리자 주간 결과 보고 발송 완료")
        else:
            log.warning("관리자 주간 결과 보고 실패 — %s", report_msg)
        # Report delivery has its own ledger and can be retried on subsequent
        # Thursday runs without resending any member emails.
        try:
            report_conn = get_conn()
            try:
                _send_experiment_report(report_conn, today)
            finally:
                report_conn.close()
        except Exception:
            log.warning("8주 실험 보고서 처리 실패", exc_info=True)
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
