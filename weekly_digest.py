#!/usr/bin/env python3
"""
홈앤스테이 주간 소식 이메일 발송
===================================
대상  : weekly_email_enabled = TRUE 인 일반 회원 전체 (관심단지 유무 무관)
Zone 1-1 : 관심단지 신규 실거래 (없으면 안내 문구)
Zone 1-2 : 매물의뢰 / 매수의뢰 진행 현황 (없으면 CTA)
Zone 2   : 이번 주 시세 랭킹 — 신고가 TOP5, 거래량 TOP5
Zone 5   : 광고 배너 (활성 배너 없으면 완전 제외)

실행:
  python weekly_digest.py                  # 전체 발송
  python weekly_digest.py --dry-run        # 발송 없이 로그만 출력
  python weekly_digest.py --user-id 4     # 특정 회원만 (테스트)
"""

import os
import sys
import argparse
import logging
from datetime import date, timedelta

import psycopg2
import psycopg2.extras

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

def _get_active_banner(cur):
    today = date.today().isoformat()
    cur.execute("""
        SELECT image_url, link_url FROM email_ad_banners
        WHERE is_active = TRUE
          AND start_date <= %s::date
          AND end_date   >= %s::date
        ORDER BY RANDOM()
        LIMIT 1
    """, (today, today))
    return cur.fetchone()


def _get_ranking(cur):
    """신고가 갱신 TOP5, 거래량 TOP5 (최근 7일)"""
    week_ago = (date.today() - timedelta(days=7)).isoformat()

    # 신고가 갱신: 이번 주 거래 중 해당 건물의 역대 최고가를 경신한 것
    cur.execute("""
        WITH this_week AS (
            SELECT building_name,
                   MAX(price) AS new_peak
            FROM transactions
            WHERE deal_date >= %s
            GROUP BY building_name
        ),
        prev_peak AS (
            SELECT building_name,
                   MAX(price) AS old_peak
            FROM transactions
            WHERE deal_date < %s
            GROUP BY building_name
        )
        SELECT t.building_name,
               t.new_peak AS price,
               mb.id      AS building_id,
               ROUND((t.new_peak - COALESCE(p.old_peak, 0))::numeric
                     * 100.0 / NULLIF(COALESCE(p.old_peak, t.new_peak), 0), 1) AS pct_gain
        FROM this_week t
        LEFT JOIN prev_peak p USING (building_name)
        LEFT JOIN master_buildings mb ON mb.building_name = t.building_name
        WHERE t.new_peak > COALESCE(p.old_peak, 0)
        ORDER BY pct_gain DESC NULLS LAST
        LIMIT 5
    """, (week_ago, week_ago))
    price_highs = cur.fetchall()

    # 거래량 TOP5 (최근 7일)
    cur.execute("""
        SELECT t.building_name,
               COUNT(*) AS deal_count,
               mb.id    AS building_id
        FROM transactions t
        LEFT JOIN master_buildings mb ON mb.building_name = t.building_name
        WHERE t.deal_date >= %s
        GROUP BY t.building_name, mb.id
        ORDER BY deal_count DESC
        LIMIT 5
    """, (week_ago,))
    most_traded = cur.fetchall()

    return price_highs, most_traded


# ── HTML 조립 ─────────────────────────────────────────────────────────────────

def _bld_url(building_id, building_name=""):
    if building_id:
        return f"{SITE_URL}/building/{building_id}"
    if building_name:
        import urllib.parse
        return f"{SITE_URL}/?q={urllib.parse.quote(building_name)}"
    return SITE_URL


def _zone1_1(favs, deals_by_fav):
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
          지도에서 관심단지 저장하기 →
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
    </table>"""


def _zone1_2(listing_reqs, buy_reqs):
    """매물의뢰 / 매수의뢰 현황"""
    all_reqs = [("매물내놓기", r) for r in listing_reqs] + \
               [("매수의뢰",   r) for r in buy_reqs]

    if not all_reqs:
        return f"""
        <p style="color:#555;font-size:14px;margin:0 0 12px;">
          현재 진행 중인 의뢰가 없습니다.<br>
          매물을 내놓으시면 전문 중개사가 연결해드립니다.
        </p>
        <a href="{SITE_URL}/"
           style="display:inline-block;background:#B4863F;color:#fff;
                  text-decoration:none;padding:10px 22px;border-radius:6px;
                  font-size:14px;font-weight:700;">
          매물내놓기 →
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


def _zone5(banner):
    if not banner:
        return ""
    return f"""
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr>
        <td style="padding:16px 0 0;border-top:1px solid #eee;">
          <p style="font-size:10px;color:#aaa;margin:0 0 6px;">[광고]</p>
          <a href="{banner['link_url']}" target="_blank" rel="noopener noreferrer">
            <img src="{banner['image_url']}" alt="광고 배너"
                 style="display:block;width:100%;max-width:524px;height:auto;border-radius:8px;" />
          </a>
        </td>
      </tr>
    </table>"""


def build_html(user_name, favs, deals_by_fav,
               listing_reqs, buy_reqs,
               price_highs, most_traded,
               banner, unsubscribe_url):
    z1  = _zone1_1(favs, deals_by_fav)
    z12 = _zone1_2(listing_reqs, buy_reqs)
    z2  = _zone2(price_highs, most_traded)
    z5  = _zone5(banner)

    zone5_block = ""
    if z5:
        zone5_block = f"""
  <tr>
    <td style="padding:20px 28px 0;">{z5}</td>
  </tr>"""

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

  <!-- ── Zone 5: 광고 배너 (없으면 블록 자체 제거) ── -->
  {zone5_block}

  <!-- ── 푸터 ── -->
  <tr>
    <td style="padding:20px 28px 24px;">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td style="padding-top:16px;border-top:1px solid #eee;text-align:center;">
            <p style="font-size:11px;color:#aaa;margin:0 0 4px;">
              홈앤스테이 | 빌드리머스 주식회사
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
        banner                  = _get_active_banner(cur)
        price_highs, most_traded = _get_ranking(cur)

        # 발송 대상 회원 조회
        uid_filter = "AND u.id = %s" if target_uid else ""
        uid_params = (target_uid,) if target_uid else ()
        cur.execute(f"""
            SELECT id, email, COALESCE(name, email) AS name
            FROM users u
            WHERE COALESCE(weekly_email_enabled, FALSE) = TRUE
              AND email IS NOT NULL AND email <> ''
              AND COALESCE(status, 'active') <> 'withdrawn'
              {uid_filter}
            ORDER BY id
        """, uid_params)
        users = cur.fetchall()
        log.info("발송 대상 회원 %d명 (배너=%s)", len(users), "있음" if banner else "없음")

        sent = errors = 0
        for user in users:
            uid   = user["id"]
            email = user["email"]
            name  = user["name"]

            # 관심단지
            cur.execute("""
                SELECT building_name, address, master_building_id
                FROM user_favorites
                WHERE user_id = %s
                ORDER BY created_at DESC
            """, (uid,))
            favs = [(r["building_name"], r["address"], r["master_building_id"])
                    for r in cur.fetchall()]

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
                           ON mb.building_name = t.building_name
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

            # 이메일 제목 구성
            n_deals = sum(1 for f in favs if deals_by_fav.get((f[0], f[1])))
            has_ad  = banner is not None
            subject_suffix = f" | 관심단지 {n_deals}곳 새 실거래" if n_deals else ""
            subject = f"{'(광고) ' if has_ad else ''}[홈앤스테이] 이번 주 소식{subject_suffix}"

            unsubscribe_url = f"{SITE_URL}/mypage#alerts"
            html_body = build_html(
                name, favs, deals_by_fav,
                listing_reqs, buy_reqs,
                price_highs, most_traded,
                banner, unsubscribe_url,
            )

            if dry_run:
                log.info("  [DRY-RUN] %s | 관심단지 %d개(신규실거래 %d건) | "
                         "의뢰 listing=%d buy=%d | 배너=%s",
                         email, len(favs), n_deals,
                         len(listing_reqs), len(buy_reqs),
                         "있음" if banner else "없음")
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
