#!/usr/bin/env python3
"""
홈앤스테이 주간 소식 이메일 발송
===================================
대상  : weekly_email_enabled = TRUE 인 일반 회원 전체 (관심단지 유무 무관)
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
import logging
from datetime import date, timedelta

import psycopg2
import psycopg2.extras

from addr_norm import normalize_jibun_prefix, normalize_road_prefix
from email_util import send_email

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

    # 신고가 갱신: 이번 주 거래 중 해당 건물의 역대 최고가를 경신한 것
    # ※ 동명 건물이 여러 master_buildings 행으로 매칭될 수 있어 LATERAL 서브쿼리로
    #    building_id를 1건만 선택. GROUP BY에 mb.id를 넣으면 중복 행이 생겨 오류 발생.
    cur.execute("""
        WITH this_week AS (
            SELECT building_name, jibun,
                   MAX(price) AS new_peak
            FROM transactions
            WHERE deal_date >= %s
            GROUP BY building_name, jibun
        ),
        prev_peak AS (
            SELECT building_name, jibun,
                   MAX(price) AS old_peak
            FROM transactions
            WHERE deal_date < %s
            GROUP BY building_name, jibun
        )
        SELECT t.building_name,
               t.new_peak AS price,
               (SELECT mb2.id FROM master_buildings mb2
                WHERE REPLACE(mb2.building_name,' ','') = REPLACE(t.building_name,' ','')
                  AND mb2.jibun = t.jibun
                ORDER BY mb2.id LIMIT 1)  AS building_id,
               ROUND((t.new_peak - COALESCE(p.old_peak, 0))::numeric
                     * 100.0 / NULLIF(COALESCE(p.old_peak, t.new_peak), 0), 1) AS pct_gain
        FROM this_week t
        LEFT JOIN prev_peak p
               ON p.building_name = t.building_name AND p.jibun = t.jibun
        WHERE t.new_peak > COALESCE(p.old_peak, 0)
        ORDER BY pct_gain DESC NULLS LAST
        LIMIT 5
    """, (week_ago, week_ago))
    price_highs = cur.fetchall()

    # 거래량 TOP5 (최근 7일)
    # ※ 동일하게 correlated 서브쿼리로 building_id 1건만 선택 → 중복/오매칭 방지
    cur.execute("""
        SELECT t.building_name,
               COUNT(*) AS deal_count,
               (SELECT mb2.id FROM master_buildings mb2
                WHERE REPLACE(mb2.building_name,' ','') = REPLACE(t.building_name,' ','')
                  AND mb2.jibun = t.jibun
                ORDER BY mb2.id LIMIT 1)  AS building_id
        FROM transactions t
        WHERE t.deal_date >= %s
        GROUP BY t.building_name, t.jibun
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


def _get_datalab_summary_db_fallback():
    """캐시를 사용할 수 없을 때 주간 이메일이 직접 읽는 최소 통계."""
    empty = {"report_rate": None, "price_change": None, "volume_top": None}
    conn = cur = None
    try:
        conn = get_conn()
        cur = conn.cursor()

        # fallback ① 전국 생숙 영업신고율. master_buildings에는 정규화 키가
        # 저장되지 않으므로 기존 주소 매칭과 같은 도로명·지번 prefix 키를 만들어
        # Python 해시 맵으로 결합한다. 대량 OR JOIN은 주간 발송 시간 제한을 넘긴다.
        cur.execute("""
            SELECT id, units, road_address, jibun_address
            FROM master_buildings
            WHERE lodging_type = '생활'
        """)
        buildings = cur.fetchall()
        cur.execute("""
            SELECT permit_number, room_count, biz_status_name, road_norm, jibun_norm
            FROM lodging_registry
            WHERE road_norm IS NOT NULL OR jibun_norm IS NOT NULL
        """)
        lodgings = cur.fetchall()
        by_road, by_jibun = {}, {}
        for lodging in lodgings:
            if lodging.get("road_norm"):
                by_road.setdefault(lodging["road_norm"], {})[lodging["permit_number"]] = lodging
            if lodging.get("jibun_norm"):
                by_jibun.setdefault(lodging["jibun_norm"], {})[lodging["permit_number"]] = lodging

        total_units = active_rooms = 0
        for building in buildings:
            total_units += int(building.get("units") or 0)
            road_key = normalize_road_prefix(building.get("road_address"))
            jibun_key = normalize_jibun_prefix(
                building.get("jibun_address") or building.get("road_address")
            )
            matches = {}
            matches.update(by_road.get(road_key, {}))
            matches.update(by_jibun.get(jibun_key, {}))
            for lodging in matches.values():
                if "폐업" not in (lodging.get("biz_status_name") or ""):
                    active_rooms += int(lodging.get("room_count") or 0)
        report_rate = round(100.0 * active_rooms / total_units, 1) if total_units else None

        # fallback ② 최근 30일 거래량 TOP1
        cur.execute("""
            SELECT building_name, COUNT(*) AS deal_count
            FROM transactions
            WHERE deal_date >= TO_CHAR(NOW() - INTERVAL '30 days', 'YYYY-MM-DD')
              AND price > 0
            GROUP BY building_name
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
                WHERE deal_date IS NOT NULL
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
                building_name, address, sgg_nm, umd_nm, transaction_count,
                first_price, latest_price, first_deal_date, latest_deal_date,
                area_sqm, change_percent,
                (SELECT id FROM master_buildings
                 WHERE building_name = changed.building_name
                   AND sgg_cd = changed.sgg_cd
                   AND umd_nm = changed.umd_nm
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
                "deal_count": int(volume_row.get("deal_count") or 0),
            }
        if price_row:
            result["price_change"] = {
                "building_name": price_row.get("building_name"),
                "building_id": price_row.get("building_id"),
                "change_percent": round(float(price_row.get("change_percent")), 1),
            }
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
    empty = {"report_rate": None, "price_change": None, "volume_top": None}
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
            result["report_rate"] = float(rate) if rate is not None else None

        if section_ok("transaction_stats"):
            transactions = data.get("transaction_stats") or {}
            price_items = (
                ((transactions.get("price_change") or {}).get("up") or {}).get("items")
                or []
            )
            volume_items = transactions.get("volume_top") or []
            result["price_change"] = dict(price_items[0]) if price_items else None
            result["volume_top"] = dict(volume_items[0]) if volume_items else None
        return _get_datalab_summary_db_fallback() if cache_fill_failed else result
    except Exception:
        log.warning("데이터랩 요약 캐시를 읽지 못했습니다. DB 폴백을 시도합니다.", exc_info=True)
        return _get_datalab_summary_db_fallback()


# ── HTML 조립 ─────────────────────────────────────────────────────────────────

def _bld_url(building_id, building_name=""):
    """building_id 가 있으면 상세 페이지 직링크, 없으면 홈으로.
    /?q= 검색 URL은 지도 패널을 자동으로 열지 않아 '건물 정보 못 불러옴'처럼 보이므로 사용하지 않는다."""
    if building_id:
        return f"{SITE_URL}/building/{building_id}"
    return SITE_URL


def _zone1_1(favs, deals_by_fav, alert_off_count=0):
    """관심단지 실거래"""
    if not favs:
        return f"""
        <p style="color:#555;font-size:14px;margin:0 0 12px;">
          아직 등록하신 관심단지가 없어요.
        </p>
        <a href="{SITE_URL}/"
           style="display:inline-block;background:#B4863F;color:#fff;
                  text-decoration:none;padding:10px 22px;border-radius:6px;
                  font-size:14px;font-weight:700;">
          관심단지 등록하고 실거래 알림 받기 →
        </a>"""

    rows = ""
    for bname, addr, mid in favs:
        deal = deals_by_fav.get((bname, addr))
        url  = _bld_url(mid or (deal and deal.get("building_id")), bname)
        if deal:
            rows += f"""
            <tr>
              <td style="padding:8px 4px;border-bottom:1px solid #eee;vertical-align:top;">
                <a href="{url}" style="color:#16202E;font-weight:700;text-decoration:none;">{bname}</a>
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
                <a href="{url}" style="color:#16202E;font-weight:700;text-decoration:none;">{bname}</a>
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
                     border-bottom:2px solid #eee;">건물명</th>
          <th style="text-align:right;padding:6px 4px;color:#888;font-weight:600;
                     border-bottom:2px solid #eee;white-space:nowrap;">거래금액</th>
          <th style="text-align:right;padding:6px 4px;color:#888;font-weight:600;
                     border-bottom:2px solid #eee;">계약일</th>
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
          매물 내놓기 — 제휴 중개법인 통해 수수료 0원 →
        </a>"""

    rows = ""
    for kind, r in all_reqs:
        url  = _bld_url(r.get("master_building_id"), r.get("building_name") or "")
        name = r.get("building_name") or "-"
        badge_style = _status_badge_style(r["status"])
        rows += f"""
        <tr>
          <td style="padding:8px 4px;border-bottom:1px solid #eee;font-size:12px;
                     color:#888;white-space:nowrap;">{kind}</td>
          <td style="padding:8px 4px;border-bottom:1px solid #eee;font-weight:700;">
            <a href="{url}" style="color:#16202E;text-decoration:none;">{name}</a>
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
    def price_rows():
        if not price_highs:
            return "<tr><td colspan='3' style='padding:8px 4px;color:#888;font-size:13px;'>이번 주 신고가 갱신 건물이 없습니다.</td></tr>"
        html = ""
        for i, r in enumerate(price_highs, 1):
            url  = _bld_url(r.get("building_id"), r["building_name"])
            gain = f"+{r['pct_gain']}%" if r.get("pct_gain") else ""
            html += f"""
            <tr>
              <td style="padding:6px 4px;border-bottom:1px solid #f0f0f0;
                         color:#aaa;width:20px;font-size:13px;">{i}</td>
              <td style="padding:6px 4px;border-bottom:1px solid #f0f0f0;font-size:13px;">
                <a href="{url}" style="color:#16202E;font-weight:700;text-decoration:none;">
                  {r['building_name']}
                </a>
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
            url = _bld_url(r.get("building_id"), r["building_name"])
            html += f"""
            <tr>
              <td style="padding:6px 4px;border-bottom:1px solid #f0f0f0;
                         color:#aaa;width:20px;font-size:13px;">{i}</td>
              <td style="padding:6px 4px;border-bottom:1px solid #f0f0f0;font-size:13px;">
                <a href="{url}" style="color:#16202E;font-weight:700;text-decoration:none;">
                  {r['building_name']}
                </a>
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
    """데이터랩 원본 캐시의 전국 요약. 데이터가 없으면 Zone 자체를 생략한다."""
    summary = summary or {}
    rate = summary.get("report_rate")
    price = summary.get("price_change") or {}
    volume = summary.get("volume_top") or {}

    if rate is None and not price and not volume:
        return ""

    rate_text = f"{rate:.1f}%" if isinstance(rate, (int, float)) else "-"
    if price:
        pct = price.get("change_percent")
        pct_text = f"{float(pct):+.1f}%" if pct is not None else "변동률 집계 중"
        price_text = (
            f'<a href="{_bld_url(price.get("building_id"), price.get("building_name") or "")}" '
            'style="color:#16202E;font-weight:700;text-decoration:none;">'
            f'{html.escape(str(price.get("building_name") or "-"))}</a> · {pct_text}'
        )
    else:
        price_text = "-"

    if volume:
        volume_text = (
            f'<a href="{_bld_url(volume.get("building_id"), volume.get("building_name") or "")}" '
            'style="color:#16202E;font-weight:700;text-decoration:none;">'
            f'{html.escape(str(volume.get("building_name") or "-"))}</a> · '
            f'{int(volume.get("deal_count") or 0):,}건'
        )
    else:
        volume_text = "-"

    return f"""
    <table style="width:100%;border-collapse:collapse;font-size:13px;">
      <tbody>
        <tr><td style="padding:8px 4px;border-bottom:1px solid #f0f0f0;color:#888;">전국 생숙 영업신고율</td>
            <td style="padding:8px 4px;border-bottom:1px solid #f0f0f0;text-align:right;color:#B4863F;font-weight:700;">{rate_text}</td></tr>
        <tr><td style="padding:8px 4px;border-bottom:1px solid #f0f0f0;color:#888;">가격변동 TOP1</td>
            <td style="padding:8px 4px;border-bottom:1px solid #f0f0f0;text-align:right;">{price_text}</td></tr>
        <tr><td style="padding:8px 4px;color:#888;">거래량 TOP1</td>
            <td style="padding:8px 4px;text-align:right;">{volume_text}</td></tr>
      </tbody>
    </table>"""


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


def build_html(user_name, favs, deals_by_fav,
               listing_reqs, buy_reqs,
               price_highs, most_traded,
               datalab_summary, feature_tip,
               unsubscribe_url, alert_off_count=0):
    z1  = _zone1_1(favs, deals_by_fav, alert_off_count)
    z12 = _zone1_2(listing_reqs, buy_reqs)
    z2  = _zone2(price_highs, most_traded)
    z3  = _zone3(datalab_summary)
    z4  = _zone4(feature_tip)

    zone3_block = f"""
  <tr>
    <td style="padding:20px 28px 0;">
      <h2 style="font-size:15px;font-weight:700;color:#16202E;margin:0 0 12px;
                 padding-bottom:8px;border-bottom:2px solid #B4863F;">
        📈 데이터랩 한눈에 보기
      </h2>
      {z3}
    </td>
  </tr>""" if z3 else ""

    zone4_block = f"""
  <tr>
    <td style="padding:20px 28px 0;">
      <h2 style="font-size:15px;font-weight:700;color:#16202E;margin:0 0 12px;
                 padding-bottom:8px;border-bottom:2px solid #B4863F;">
        ✨ 이번 주 기능 소개
      </h2>
      {z4}
    </td>
  </tr>""" if z4 else ""

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>홈앤스테이 주간 소식</title>
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
      <p style="color:#9aa5b1;font-size:12px;margin:6px 0 0;">주간 소식</p>
    </td>
  </tr>

  <!-- ── 인사말 ── -->
  <tr>
    <td style="padding:24px 28px 0;">
      <p style="font-size:15px;font-weight:700;color:#16202E;margin:0 0 4px;">
        {user_name}님, 이번 주 홈앤스테이 소식을 전달해드려요.
      </p>
      <p style="font-size:13px;color:#888;margin:0;">
        생활숙박시설·관광숙박 실거래가 최신 정보입니다.
      </p>
    </td>
  </tr>

  <!-- ── Zone 1-1: 관심단지 실거래 ── -->
  <tr>
    <td style="padding:20px 28px 0;">
      <h2 style="font-size:15px;font-weight:700;color:#16202E;margin:0 0 12px;
                 padding-bottom:8px;border-bottom:2px solid #B4863F;">
        📌 관심단지 실거래 알림
      </h2>
      {z1}
    </td>
  </tr>

  <!-- ── Zone 1-2: 매물의뢰 현황 ── -->
  <tr>
    <td style="padding:20px 28px 0;">
      <h2 style="font-size:15px;font-weight:700;color:#16202E;margin:0 0 12px;
                 padding-bottom:8px;border-bottom:2px solid #B4863F;">
        📋 매물의뢰 진행 현황
      </h2>
      {z12}
    </td>
  </tr>

  <!-- ── Zone 2: 시세 랭킹 ── -->
  <tr>
    <td style="padding:20px 28px 0;">
      <h2 style="font-size:15px;font-weight:700;color:#16202E;margin:0 0 12px;
                 padding-bottom:8px;border-bottom:2px solid #B4863F;">
        📊 이번 주 시세 랭킹
      </h2>
      {z2}
    </td>
  </tr>

  {zone3_block}
  {zone4_block}

  <!-- ── 푸터 ── -->
  <tr>
    <td style="padding:20px 28px 24px;">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td style="padding-top:16px;border-top:1px solid #eee;text-align:center;">
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


# ── 메인 ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="홈앤스테이 주간 소식 이메일 발송")
    parser.add_argument("--dry-run",  action="store_true", help="발송 없이 로그만 출력")
    parser.add_argument("--user-id",  type=int, default=None, help="특정 회원 ID (테스트용)")
    args = parser.parse_args()

    dry_run    = args.dry_run
    target_uid = args.user_id
    week_ago   = (date.today() - timedelta(days=7)).isoformat()

    conn = get_conn()
    try:
        cur = conn.cursor()

        # 공통 데이터 (전체 회원이 동일하게 받음)
        price_highs, most_traded = _get_ranking(cur)
        datalab_summary          = _get_datalab_summary()
        feature_tip              = _get_active_feature_tip(cur)

        # 발송 대상 회원 조회
        uid_filter = "AND u.id = %s" if target_uid else ""
        uid_params = (target_uid,) if target_uid else ()
        cur.execute(f"""
            SELECT id, email, COALESCE(name, email) AS name,
                   COALESCE(user_type, 'general') AS user_type,
                   COALESCE(unsubscribe_token::text, '') AS unsubscribe_token
            FROM users u
            WHERE COALESCE(weekly_email_enabled, FALSE) = TRUE
              AND email IS NOT NULL AND email <> ''
              AND COALESCE(status, 'active') <> 'withdrawn'
              {uid_filter}
            ORDER BY id
        """, uid_params)
        users = cur.fetchall()
        log.info("발송 대상 회원 %d명", len(users))

        sent = errors = 0
        for user in users:
            uid   = user["id"]
            email = user["email"]
            name  = user["name"]

            # 관심단지 — /api/favorites/mine 과 동일한 3단계 LATERAL JOIN으로 building_id 결정
            # (저장 시점 master_building_id가 NULL인 기존 데이터도 거래·주소 역매칭으로 복구)
            cur.execute("""
                SELECT uf.building_name, uf.address,
                       COALESCE(uf.master_building_id, bid.id, bid2.id) AS master_building_id
                FROM user_favorites uf
                LEFT JOIN LATERAL (
                    SELECT mb.id
                    FROM transactions t2
                    JOIN master_buildings mb
                      ON mb.sgg_cd = t2.sgg_cd AND mb.umd_nm = t2.umd_nm
                     AND mb.jibun = t2.jibun
                    WHERE ((uf.building_name IS NULL AND t2.building_name IS NULL)
                           OR t2.building_name = uf.building_name)
                      AND t2.address = uf.address
                    ORDER BY (mb.building_name = uf.building_name) DESC NULLS LAST, mb.id
                    LIMIT 1
                ) bid ON TRUE
                LEFT JOIN LATERAL (
                    SELECT mb.id
                    FROM master_buildings mb
                    WHERE mb.road_address = uf.address
                       OR REPLACE(mb.umd_nm || mb.jibun, ' ', '') = REPLACE(uf.address, ' ', '')
                    ORDER BY (mb.building_name = uf.building_name) DESC NULLS LAST, mb.id
                    LIMIT 1
                ) bid2 ON TRUE
                WHERE uf.user_id = %s
                ORDER BY uf.created_at DESC, uf.id DESC
            """, (uid,))
            favs = [(r["building_name"], r["address"], r["master_building_id"])
                    for r in cur.fetchall()]

            # 알림 꺼진 관심단지 수 (user_alert_subscriptions 미등록)
            alert_off_count = 0
            if favs:
                cur.execute("""
                    SELECT COUNT(*) AS cnt FROM (
                        SELECT building_name, address FROM user_favorites WHERE user_id = %s
                        EXCEPT
                        SELECT building_name, address FROM user_alert_subscriptions WHERE user_id = %s
                    ) sub
                """, (uid, uid))
                alert_off_count = (cur.fetchone() or {}).get("cnt", 0) or 0

            # 관심단지별 최근 실거래 (건물명+주소 매칭, 최신 1건)
            deals_by_fav: dict = {}
            if favs:
                fav_names   = [f[0] for f in favs]
                fav_addrs   = [f[1] for f in favs]
                cur.execute("""
                    SELECT DISTINCT ON (t.building_name, t.address)
                        t.building_name, t.address, t.price, t.deal_date,
                        mb.id AS building_id
                    FROM transactions t
                    LEFT JOIN master_buildings mb
                           ON REPLACE(mb.building_name,' ','') = REPLACE(t.building_name,' ','')
                    WHERE t.building_name = ANY(%s)
                      AND t.address       = ANY(%s)
                      AND t.deal_date    >= %s
                    ORDER BY t.building_name, t.address, t.deal_date DESC
                """, (fav_names, fav_addrs, week_ago))
                for r in cur.fetchall():
                    # 건물명+주소가 모두 일치하는 것만 저장
                    key = (r["building_name"], r["address"])
                    if key in set((f[0], f[1]) for f in favs):
                        deals_by_fav[key] = dict(r)

            # 진행 중 매물의뢰
            cur.execute("""
                SELECT lr.id, lr.status, lr.master_building_id,
                       mb.building_name
                FROM listing_requests lr
                LEFT JOIN master_buildings mb ON mb.id = lr.master_building_id
                WHERE lr.user_id = %s
                  AND lr.status NOT IN ('cancelled', 'completed')
                ORDER BY lr.created_at DESC
                LIMIT 5
            """, (uid,))
            listing_reqs = cur.fetchall()

            # 진행 중 매수의뢰
            cur.execute("""
                SELECT br.id, br.status, br.master_building_id,
                       mb.building_name
                FROM buy_requests br
                LEFT JOIN master_buildings mb ON mb.id = br.master_building_id
                WHERE br.user_id = %s
                  AND br.status NOT IN ('cancelled', 'completed')
                ORDER BY br.created_at DESC
                LIMIT 5
            """, (uid,))
            buy_reqs = cur.fetchall()

            # 이메일 제목 구성: 관심단지 새 실거래 → 가격변동 TOP1 → 기능 소개 → 기본.
            n_deals = sum(1 for f in favs if deals_by_fav.get((f[0], f[1])))
            subject = _build_subject(n_deals, datalab_summary, feature_tip)

            # 수신거부는 /unsubscribe?token=… 대신 마이페이지로 이동
            # (토큰 링크가 "잘못됐거나 이미 처리된 링크" 오류를 내는 경우 방지)
            unsubscribe_url = f"{SITE_URL}/mypage"
            html_body = build_html(
                name, favs, deals_by_fav,
                listing_reqs, buy_reqs,
                price_highs, most_traded,
                datalab_summary, feature_tip,
                unsubscribe_url, alert_off_count,
            )

            if dry_run:
                log.info("  [DRY-RUN] %s | 관심단지 %d개(신규실거래 %d건) | "
                           "의뢰 listing=%d buy=%d | 데이터랩 신고율=%s | 기능팁=%s",
                         email, len(favs), n_deals,
                          len(listing_reqs), len(buy_reqs), datalab_summary.get("report_rate"),
                           feature_tip.get("episode") if feature_tip else "-")
                sent += 1
                continue

            ok, msg = send_email(email, subject, html_body)
            if ok:
                sent += 1
                log.info("  ✓ %s", email)
            else:
                errors += 1
                log.warning("  ✗ %s — %s", email, msg)

    finally:
        conn.close()

    log.info("완료: 발송=%d, 오류=%d", sent, errors)


if __name__ == "__main__":
    main()
