#!/usr/bin/env python3
"""관심단지 신규 실거래 일일 이메일 digest.

KST 기준 전날 새로 수집된 거래(created_at)를 관심단지 알림 구독과 매칭한다.
같은 회원·거래·발송일은 deal_alert_logs에서 한 번만 발송한다.

실행:
  python deal_alert_digest.py
  python deal_alert_digest.py --dry-run
  python deal_alert_digest.py --date 2026-08-24
"""

import argparse
import html
import logging
import os
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from urllib.parse import quote

import psycopg2
import psycopg2.extras

from email_util import send_email
from weekly_digest import SITE_URL, _fmt_price


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9), name="KST")
CLAIM_RETRY_AFTER = "1 hour"


def get_conn():
    return psycopg2.connect(
        os.environ["DATABASE_URL"],
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


def kst_yesterday(now=None):
    """현재 시각에서 KST 전날 날짜를 계산한다. 테스트에서는 now를 주입한다."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(KST).date() - timedelta(days=1)


def kst_day_utc_bounds(alert_date):
    """KST 날짜의 [00:00, 다음날 00:00) 범위를 DB timestamp(UTC)로 돌려준다."""
    start = datetime.combine(alert_date, time.min, tzinfo=KST)
    end = start + timedelta(days=1)
    return (
        start.astimezone(timezone.utc).replace(tzinfo=None),
        end.astimezone(timezone.utc).replace(tzinfo=None),
    )


def _display_area(area):
    try:
        return f"{float(area):g}㎡" if area not in (None, "", 0) else ""
    except (TypeError, ValueError):
        return str(area or "")


def build_html(user_name, deals, unsubscribe_url):
    """Zone 1-1만 남긴 짧은 일일 digest HTML."""
    cards = []
    for tx in deals:
        building = html.escape(str(tx.get("building_name") or tx.get("address") or "관심단지"))
        address = html.escape(str(tx.get("address") or ""))
        deal_type = html.escape(str(tx.get("deal_type") or "실거래"))
        meta = [deal_type, _display_area(tx.get("area"))]
        if tx.get("floor") not in (None, ""):
            meta.append(f"{tx['floor']}층")
        detail = " · ".join(item for item in meta if item)
        query = quote(str(tx.get("building_name") or tx.get("address") or ""))
        cards.append(f"""
          <tr>
            <td style="padding:14px 0;border-bottom:1px solid #EEEEEE;">
              <a href="{SITE_URL}/?q={query}"
                 style="font-size:15px;font-weight:700;color:#16202E;text-decoration:none;">
                {building}
              </a>
              <p style="font-size:12px;color:#888;margin:4px 0 8px;">{address}</p>
              <p style="font-size:13px;color:#555;margin:0;">
                <strong style="color:#B4863F;">{_fmt_price(tx.get("price"))}</strong>
                &nbsp;·&nbsp; {html.escape(str(tx.get("deal_date") or "-"))}
                {f"&nbsp;·&nbsp; {html.escape(detail)}" if detail else ""}
              </p>
            </td>
          </tr>""")

    safe_name = html.escape(str(user_name or "회원"))
    safe_unsubscribe = html.escape(unsubscribe_url, quote=True)
    return f"""<!DOCTYPE html>
<html lang="ko">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>홈앤스테이 관심단지 실거래 알림</title></head>
<body style="margin:0;padding:0;background:#f4f5f7;font-family:'Apple SD Gothic Neo','Noto Sans KR',sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f5f7;padding:24px 0;"><tr><td align="center">
<table width="100%" style="max-width:580px;background:#fff;border-radius:12px;overflow:hidden;">
  <tr><td style="background:#16202E;padding:20px 28px;text-align:center;">
    <a href="{SITE_URL}"><img src="{SITE_URL}/static/images/logo-email.png" alt="HOME &amp; STAY"
      width="180" style="display:inline-block;height:auto;max-height:44px;border:0;"></a>
    <p style="color:#B4863F;font-size:11px;font-weight:700;margin:6px 0 0;">관심단지 실거래 알림</p>
  </td></tr>
  <tr><td style="padding:24px 28px 0;">
    <p style="font-size:15px;font-weight:700;color:#16202E;margin:0 0 5px;">{safe_name}님, 관심단지에 새 실거래가 등록됐어요.</p>
    <p style="font-size:13px;color:#777;margin:0;">새로 수집된 거래를 한 번에 확인해보세요.</p>
  </td></tr>
  <tr><td style="padding:20px 28px 0;">
    <h2 style="font-size:15px;font-weight:700;color:#16202E;margin:0;padding-bottom:8px;border-bottom:2px solid #B4863F;">📌 관심단지 실거래 알림</h2>
    <table width="100%" cellpadding="0" cellspacing="0" role="presentation">{''.join(cards)}</table>
    <p style="margin:18px 0 0;text-align:center;"><a href="{SITE_URL}/"
      style="display:inline-block;background:#16202E;color:#fff;text-decoration:none;padding:10px 18px;border-radius:6px;font-size:13px;font-weight:700;">관심단지와 실거래 더 보기 →</a></p>
  </td></tr>
  <tr><td style="padding:24px 28px;text-align:center;">
    <p style="padding-top:16px;border-top:1px solid #eee;font-size:11px;color:#aaa;margin:0;">
      이 메일은 홈앤스테이 주간 소식 수신 설정에 따라 발송됩니다.
      <a href="{safe_unsubscribe}" style="color:#aaa;text-decoration:underline;">수신거부</a>
    </p>
  </td></tr>
</table></td></tr></table></body></html>"""


def _load_recipients(cur, start_utc, end_utc):
    """전날 새 거래를 구독자별로 묶기 전의 행을 조회한다."""
    cur.execute(
        """
        SELECT u.id AS user_id, u.email, COALESCE(u.name, u.email) AS user_name,
               COALESCE(u.unsubscribe_token::text, '') AS unsubscribe_token,
               t.id AS transaction_id, t.building_name, t.address, t.price, t.deal_date,
               t.deal_type, t.area, t.floor
          FROM transactions t
          JOIN user_alert_subscriptions s
            ON s.address = t.address
           AND ((s.building_name IS NULL AND t.building_name IS NULL)
                OR s.building_name = t.building_name)
          JOIN users u ON u.id = s.user_id
         WHERE t.created_at >= %s AND t.created_at < %s
           AND t.transaction_scope = 'unit'
           AND COALESCE(u.weekly_email_enabled, TRUE) = TRUE
           AND u.email IS NOT NULL AND u.email <> ''
           AND COALESCE(u.status, 'active') <> 'withdrawn'
         ORDER BY u.id, t.id
        """,
        (start_utc, end_utc),
    )
    grouped = defaultdict(lambda: {"user": None, "deals": []})
    for row in cur.fetchall():
        bucket = grouped[row["user_id"]]
        bucket["user"] = {
            "id": row["user_id"],
            "email": row["email"],
            "name": row["user_name"],
            "unsubscribe_token": row["unsubscribe_token"],
        }
        bucket["deals"].append(dict(row))
    return grouped


def _claim_deals(cur, user_id, transaction_ids, alert_date):
    """중복 발송을 막는 선점. 실패·오래된 pending만 다음 실행에서 재시도한다."""
    claimed = []
    for transaction_id in transaction_ids:
        cur.execute(
            f"""
            INSERT INTO deal_alert_logs
                (user_id, transaction_id, alert_date, status, claimed_at, error_message)
            VALUES (%s, %s, %s, 'pending', NOW(), NULL)
            ON CONFLICT (user_id, transaction_id, alert_date) DO UPDATE
                SET status = 'pending', claimed_at = NOW(), error_message = NULL
              WHERE deal_alert_logs.status = 'failed'
                 OR (deal_alert_logs.status = 'pending'
                     AND deal_alert_logs.claimed_at < NOW() - INTERVAL '{CLAIM_RETRY_AFTER}')
            RETURNING transaction_id
            """,
            (user_id, transaction_id, alert_date),
        )
        row = cur.fetchone()
        if row:
            claimed.append(row["transaction_id"])
    return claimed


def _finish_claim(cur, user_id, transaction_ids, alert_date, ok, error_message=None):
    """발송 결과를 남겨 성공한 거래는 영구 중복 방지, 실패한 거래는 다음 실행에 재시도한다."""
    if not transaction_ids:
        return
    if ok:
        cur.execute(
            """
            UPDATE deal_alert_logs
               SET status = 'sent', sent_at = NOW(), error_message = NULL
             WHERE user_id = %s AND transaction_id = ANY(%s) AND alert_date = %s
            """,
            (user_id, transaction_ids, alert_date),
        )
    else:
        cur.execute(
            """
            UPDATE deal_alert_logs
               SET status = 'failed', error_message = %s
             WHERE user_id = %s AND transaction_id = ANY(%s) AND alert_date = %s
            """,
            (str(error_message or "email delivery failed")[:500], user_id, transaction_ids, alert_date),
        )


def run(alert_date=None, dry_run=False):
    """지정 KST 날짜의 일일 digest를 처리하고 결과 요약을 돌려준다."""
    alert_date = alert_date or kst_yesterday()
    start_utc, end_utc = kst_day_utc_bounds(alert_date)
    result = {"users": 0, "sent": 0, "skipped": 0, "errors": 0}
    conn = get_conn()
    try:
        cur = conn.cursor()
        recipients = _load_recipients(cur, start_utc, end_utc)
        result["users"] = len(recipients)
        log.info("KST %s 신규 실거래 대상 회원 %d명", alert_date, len(recipients))

        for bucket in recipients.values():
            user = bucket["user"]
            deals = bucket["deals"]
            if dry_run:
                result["sent"] += 1
                log.info("  [DRY-RUN] %s | 새 실거래 %d건", user["email"], len(deals))
                continue

            claimed_ids = _claim_deals(cur, user["id"], [d["transaction_id"] for d in deals], alert_date)
            conn.commit()
            if not claimed_ids:
                result["skipped"] += 1
                continue
            claimed_deals = [d for d in deals if d["transaction_id"] in set(claimed_ids)]
            token = user.get("unsubscribe_token") or ""
            unsubscribe_url = (
                f"{SITE_URL}/unsubscribe?token={quote(token)}"
                if token else f"{SITE_URL}/mypage"
            )
            subject = f"[홈앤스테이] 관심단지 새 실거래 {len(claimed_deals)}건"
            try:
                ok, message = send_email(
                    user["email"],
                    subject,
                    build_html(user["name"], claimed_deals, unsubscribe_url),
                )
            except Exception as exc:
                ok, message = False, str(exc)

            _finish_claim(cur, user["id"], claimed_ids, alert_date, ok, message)
            conn.commit()
            if ok:
                result["sent"] += 1
                log.info("  ✓ %s | %d건", user["email"], len(claimed_deals))
            else:
                result["errors"] += 1
                log.warning("  ✗ %s — %s", user["email"], message)
    finally:
        conn.close()

    log.info("완료: 대상=%d, 발송=%d, 중복스킵=%d, 오류=%d",
             result["users"], result["sent"], result["skipped"], result["errors"])
    return result


def main():
    parser = argparse.ArgumentParser(description="홈앤스테이 관심단지 실거래 일일 이메일 digest")
    parser.add_argument("--dry-run", action="store_true", help="발송·발송이력 기록 없이 대상만 확인")
    parser.add_argument("--date", type=date.fromisoformat, default=None, help="KST 기준 날짜 (YYYY-MM-DD)")
    args = parser.parse_args()
    run(alert_date=args.date, dry_run=args.dry_run)


if __name__ == "__main__":
    main()