#!/usr/bin/env python3
"""
관심단지 주간 요약 이메일 발송 배치

실행 방법:
  python weekly_digest.py [--dry-run] [--user-id <id>]

  --dry-run   실제 발송 없이 대상자·내용만 출력
  --user-id   특정 사용자 1명에게만 발송 (테스트용)

스케줄링 예시 (cron):
  0 9 * * 1  cd /path/to/app && python weekly_digest.py >> logs/weekly_digest.log 2>&1

로직:
  1. email_alert_enabled=true 인 회원 중 user_favorites 가 1개 이상인 회원 조회
  2. 각 회원의 관심단지에 대해 지난 7일 신규 실거래가 있는 건만 필터
  3. 신규 실거래가 있는 회원에게만 이메일 발송 (없으면 발송 안 함)
  4. 이메일 본문에 수신거부 링크 포함 (마이페이지 알림 설정 링크)
"""

import os
import sys
import argparse
import logging
from datetime import datetime, timedelta, timezone

import psycopg2
import psycopg2.extras

# email_util은 같은 디렉터리에 있다고 가정
from email_util import send_email

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL", "")
SITE_URL = os.environ.get("SITE_URL", "https://livingstay.kr")


def get_conn():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)


def _fmt_price(won_man: int) -> str:
    """만원 단위 → '1억 2,300만원' 형식."""
    if won_man is None:
        return "-"
    uk = won_man // 10000
    man = won_man % 10000
    if uk and man:
        return f"{uk:,}억 {man:,}만원"
    if uk:
        return f"{uk:,}억원"
    return f"{man:,}만원"


def _build_email_html(user_name: str, deals: list, unsubscribe_url: str) -> str:
    """관심단지 주간 요약 이메일 HTML 생성."""
    greeting = f"안녕하세요, {user_name}님!"

    rows_html = ""
    for d in deals:
        building = d["building_name"] or "(건물명 미확인)"
        addr = d["address"] or ""
        price = _fmt_price(d["price"])
        date = d["deal_date"] or ""
        detail_url = f"{SITE_URL}/building/{d['building_id']}" if d.get("building_id") else f"{SITE_URL}/?q={building}"
        rows_html += f"""
        <tr>
          <td style="padding:10px 14px; border-bottom:1px solid #eee;">
            <a href="{detail_url}" style="font-weight:700; color:#16202E; text-decoration:none; font-size:14px;">{building}</a><br>
            <span style="font-size:12px; color:#6B7684;">{addr}</span>
          </td>
          <td style="padding:10px 14px; border-bottom:1px solid #eee; text-align:right; white-space:nowrap;">
            <span style="font-weight:700; color:#B4863F; font-size:14px;">{price}</span><br>
            <span style="font-size:11px; color:#9AA5B1;">{date}</span>
          </td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>관심단지 주간 실거래 요약</title></head>
<body style="margin:0;padding:0;background:#F4F5F7;font-family:'Noto Sans KR',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#F4F5F7;padding:32px 0;">
<tr><td align="center">
  <table width="560" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,.08);">
    <!-- 헤더 -->
    <tr><td style="background:#16202E;padding:24px 32px;">
      <a href="{SITE_URL}" style="color:#fff;font-size:20px;font-weight:700;text-decoration:none;">🏨 홈앤스테이</a>
      <p style="color:#B0B8C1;font-size:13px;margin:6px 0 0;">관심단지 주간 실거래 요약</p>
    </td></tr>
    <!-- 인사 -->
    <tr><td style="padding:28px 32px 8px;">
      <p style="font-size:16px;font-weight:600;color:#16202E;margin:0 0 8px;">{greeting}</p>
      <p style="font-size:14px;color:#4A5568;line-height:1.7;margin:0;">
        관심 등록하신 건물에서 <strong>지난 7일간 새로운 실거래</strong>가 등록됐습니다.
      </p>
    </td></tr>
    <!-- 거래 목록 -->
    <tr><td style="padding:12px 32px 24px;">
      <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #eee;border-radius:8px;overflow:hidden;">
        <thead>
          <tr style="background:#F8F9FA;">
            <th style="padding:10px 14px;text-align:left;font-size:12px;color:#6B7684;font-weight:600;">건물명 / 주소</th>
            <th style="padding:10px 14px;text-align:right;font-size:12px;color:#6B7684;font-weight:600;">실거래가</th>
          </tr>
        </thead>
        <tbody>{rows_html}</tbody>
      </table>
    </td></tr>
    <!-- CTA -->
    <tr><td style="padding:0 32px 28px;text-align:center;">
      <a href="{SITE_URL}" style="display:inline-block;background:#16202E;color:#fff;padding:13px 32px;border-radius:8px;font-size:14px;font-weight:700;text-decoration:none;">
        지도에서 전체 실거래 확인하기 →
      </a>
    </td></tr>
    <!-- 푸터 -->
    <tr><td style="background:#F8F9FA;padding:18px 32px;text-align:center;">
      <p style="font-size:12px;color:#9AA5B1;margin:0;line-height:1.7;">
        이 메일은 홈앤스테이 관심단지 실거래 알림 서비스입니다.<br>
        수신을 원하지 않으시면
        <a href="{unsubscribe_url}" style="color:#9AA5B1;text-decoration:underline;">여기서 알림을 끄실 수 있습니다</a>.
      </p>
    </td></tr>
  </table>
</td></tr></table>
</body></html>"""
    return html


def run(dry_run: bool = False, target_user_id: int = None):
    if not DATABASE_URL:
        log.error("DATABASE_URL 환경변수가 없습니다. 종료합니다.")
        sys.exit(1)

    seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=7)).date().isoformat()

    conn = get_conn()
    sent = 0
    skipped = 0
    errors = 0

    try:
        with conn.cursor() as cur:
            # ── 대상 회원 조회 ──────────────────────────────────────────────
            user_filter = "AND u.id = %s" if target_user_id else ""
            user_params = (target_user_id,) if target_user_id else ()
            cur.execute(f"""
                SELECT DISTINCT u.id, u.email, COALESCE(u.name, u.email) AS name
                FROM users u
                JOIN user_favorites uf ON uf.user_id = u.id
                WHERE COALESCE(u.email_alert_enabled, TRUE) = TRUE
                  AND u.email IS NOT NULL
                  AND u.email <> ''
                  {user_filter}
                ORDER BY u.id
            """, user_params)
            users = cur.fetchall()
            log.info("대상 회원 %d명", len(users))

            for user in users:
                uid = user["id"]
                email = user["email"]
                name = user["name"]

                # ── 관심단지에 최근 7일 신규 실거래 조회 ─────────────────
                cur.execute("""
                    SELECT
                        uf.building_name, uf.address,
                        t.price, t.deal_date, t.floor, t.area,
                        mb.id AS building_id
                    FROM user_favorites uf
                    JOIN transactions t
                      ON t.building_name = uf.building_name
                     AND t.address = uf.address
                    LEFT JOIN master_buildings mb
                      ON mb.building_name = uf.building_name
                    WHERE uf.user_id = %s
                      AND t.deal_date >= %s
                    ORDER BY uf.building_name, t.deal_date DESC
                """, (uid, seven_days_ago))
                deals = cur.fetchall()

                if not deals:
                    skipped += 1
                    log.debug("  user %d — 신규 실거래 없음, 건너뜀", uid)
                    continue

                # ── 건물별로 최신 1건만 (중복 방지) ─────────────────────
                seen = {}
                unique_deals = []
                for d in deals:
                    key = (d["building_name"], d["address"])
                    if key not in seen:
                        seen[key] = True
                        unique_deals.append(d)

                unsubscribe_url = f"{SITE_URL}/mypage#alerts"
                subject = f"[홈앤스테이] 관심단지 {len(unique_deals)}곳에 새 실거래가 등록됐습니다"
                html_body = _build_email_html(name, unique_deals, unsubscribe_url)

                if dry_run:
                    log.info("  [DRY-RUN] → %s (%d건): %s",
                             email, len(unique_deals),
                             ", ".join(d["building_name"] for d in unique_deals))
                    sent += 1
                    continue

                ok, msg = send_email(email, subject, html_body)
                if ok:
                    sent += 1
                    log.info("  ✓ %s — %d건 발송", email, len(unique_deals))
                else:
                    errors += 1
                    log.warning("  ✗ %s — 발송 실패: %s", email, msg)

    finally:
        conn.close()

    log.info("완료: 발송=%d, 건너뜀=%d, 오류=%d", sent, skipped, errors)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="홈앤스테이 관심단지 주간 요약 이메일")
    parser.add_argument("--dry-run", action="store_true", help="실제 발송 없이 대상만 출력")
    parser.add_argument("--user-id", type=int, default=None, help="특정 사용자 ID에게만 발송 (테스트)")
    args = parser.parse_args()
    run(dry_run=args.dry_run, target_user_id=args.user_id)
