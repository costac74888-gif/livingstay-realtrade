"""
sync_lodgings.py — 행안부 '문화_숙박업 조회서비스' 수집 배치.

특징 (sync_brokers.py 패턴 재사용)
- 일일 트래픽 10,000건 → 소프트 캡 8,000에서 스스로 멈추고 체크포인트 저장.
- numOfRows=1000, 실제 API 업태명 기준 생활숙박·일반숙박만 저장(클라이언트 필터 — API에 업태 필터 없음).
- permit_number(관리번호 MNG_NO) 기준 UPSERT.
- --status-key 시 run_id 펜싱 + 30초 하트비트 (관리자 버튼용).

사용 예
  python sync_lodgings.py
  python sync_lodgings.py --status-key lodging_sync_status
  python sync_lodgings.py --reset
"""

import argparse
import hashlib
import hmac
import html
import json
import os
import sys
import threading
import time
from contextlib import contextmanager
from datetime import date, datetime, timedelta

import requests
from psycopg2.extras import execute_values

import import_camping_lodging as camping_importer
from addr_norm import (
    get_building_jibun_key,
    normalize_name,
    normalize_road_prefix,
    normalize_jibun_prefix,
)
from db import get_conn
from quota_policy import korea_today
from stats_cache import mark_master_stats_invalidated
from email_util import send_email
from lodging_categories import (
    TARGET_LODGING_HYGIENE_TYPES,
    is_target_lodging_hygiene,
    normalize_hygiene_type,
)
from lodging_matching import refresh_auto_building_names

API_URL = "https://apis.data.go.kr/1741000/lodgings/info"
SERVICE_KEY_ENV = "DATA_GO_KR_BROKER_API_KEY"  # 계정 공용 일반인증키 재사용
CAMPING_API_URL = "https://apis.data.go.kr/B551011/GoCamping/basedList"
CAMPING_SERVICE_KEY_ENV = "LODGING_SERVICE_KEY"

MAX_DAILY_CALLS = 8000  # 일일 쿼터 10,000 — 여유분을 남기고 멈춘다.
DAILY_CALLS_META_KEY = "lodging_daily_calls"
PROGRESS_META_KEY = "lodging_sync_progress"
LAST_SYNC_META_KEY = "lodging_last_sync"
CAMPING_MAX_DAILY_CALLS = 800
CAMPING_NUM_ROWS_DEFAULT = 100
CAMPING_DAILY_CALLS_META_KEY = "camping_daily_calls"
CAMPING_PROGRESS_META_KEY = "camping_sync_progress"
CAMPING_LAST_SYNC_META_KEY = "camping_last_sync"
_INTERNAL_STATS_REFRESH_URL = os.environ.get(
    "MASTER_STATS_REFRESH_URL",
    "http://127.0.0.1:5000/api/admin/stats/refresh",
)

# 실제 API 응답값: 숙박업(생활), 일반호텔, 여관업, 여인숙업.
# '숙박업 기타'는 범위가 모호해 별도 검토 전에는 수집하지 않는다.
TARGET_HYGIENES = TARGET_LODGING_HYGIENE_TYPES
PROGRESS_TARGET_HYGIENES = tuple(sorted(TARGET_HYGIENES))

NUM_ROWS_DEFAULT = 1000
SLEEP_DEFAULT = 0.3
HEARTBEAT_SEC = 30
LODGING_SYNC_LOCK_ID = 918273
ROOM_EXPIRY_ALERT_LOCK_ID = 918274
PERMIT_CHANGE_ALERT_LOCK_ID = 918275
ROOM_EXPIRY_THRESHOLDS = (90, 60, 30, 7)
PERMIT_ALERT_BOOTSTRAP_META_KEY = "lodging_permit_alert_snapshot_ready"


class _CampingDailyCapReached(RuntimeError):
    pass


@contextmanager
def _lodging_sync_lock():
    """모든 숙박업 동기화 실행을 직렬화하는 세션 advisory lock."""
    conn = get_conn()
    cur = conn.cursor()
    acquired = False
    try:
        cur.execute(
            "SELECT pg_try_advisory_lock(%s) AS acquired",
            (LODGING_SYNC_LOCK_ID,),
        )
        acquired = bool(cur.fetchone()["acquired"])
        if not acquired:
            print("[lodgings] 이미 다른 프로세스가 실행 중입니다 — 이 실행을 종료합니다.")
            yield False
            return
        yield True
    finally:
        if acquired:
            try:
                cur.execute(
                    "SELECT pg_advisory_unlock(%s) AS released",
                    (LODGING_SYNC_LOCK_ID,),
                )
                cur.fetchone()["released"]
            except Exception as exc:
                print(f"[lodgings] advisory lock 해제 실패: {_redact(repr(exc))[:160]}")
        cur.close()
        conn.close()


def _daily_calls_today(cur, meta_key):
    cur.execute("SELECT value FROM app_meta WHERE key=%s", (meta_key,))
    row = cur.fetchone()
    if not row or not row["value"]:
        return 0
    try:
        data = json.loads(row["value"])
        if data.get("date") == korea_today():
            return int(data.get("count", 0))
    except (TypeError, ValueError):
        pass
    return 0


def _bump_daily_calls(cur, conn, meta_key):
    today = korea_today()
    fresh = json.dumps({"date": today, "count": 1})
    cur.execute("""
        INSERT INTO app_meta (key, value, updated_at) VALUES (%s, %s, NOW())
        ON CONFLICT (key) DO UPDATE SET
            value = CASE
                WHEN (app_meta.value::jsonb ->> 'date') = %s
                THEN jsonb_build_object(
                        'date', %s,
                        'count', COALESCE((app_meta.value::jsonb ->> 'count')::int, 0) + 1
                     )::text
                ELSE EXCLUDED.value
            END,
            updated_at = NOW()
        RETURNING (value::jsonb ->> 'count')::int AS count
    """, (meta_key, fresh, today, today))
    count = cur.fetchone()["count"]
    conn.commit()
    return count


def _load_progress(cur):
    cur.execute("SELECT value FROM app_meta WHERE key=%s", (PROGRESS_META_KEY,))
    row = cur.fetchone()
    if not row or not row["value"]:
        return {"next_page": 1, "total_count": None}
    try:
        data = json.loads(row["value"])
        # 수집 대상이 바뀌면 과거 체크포인트를 이어 쓰면 안 된다.
        # 예: 생활숙박만 수집하던 시점의 page 200 체크포인트를 일반숙박
        # 추가 후 재사용하면 1~199페이지의 일반숙박을 영구히 건너뛴다.
        saved_targets = tuple(sorted(data.get("target_hygienes") or ()))
        if saved_targets != PROGRESS_TARGET_HYGIENES:
            return {"next_page": 1, "total_count": None}
        return {"next_page": int(data.get("next_page", 1)),
                "total_count": data.get("total_count")}
    except (TypeError, ValueError):
        return {"next_page": 1, "total_count": None}


def _save_progress(cur, conn, next_page, total_count):
    payload = json.dumps({
        "next_page": next_page,
        "total_count": total_count,
        "target_hygienes": PROGRESS_TARGET_HYGIENES,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    cur.execute("""
        INSERT INTO app_meta (key, value, updated_at) VALUES (%s, %s, NOW())
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
    """, (PROGRESS_META_KEY, payload))
    conn.commit()


def _clear_progress(cur, conn):
    cur.execute("DELETE FROM app_meta WHERE key=%s", (PROGRESS_META_KEY,))
    conn.commit()


def _mark_last_sync(cur, conn, total):
    payload = json.dumps({
        "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total": total,
    })
    cur.execute("""
        INSERT INTO app_meta (key, value, updated_at) VALUES (%s, %s, NOW())
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
    """, (LAST_SYNC_META_KEY, payload))
    conn.commit()
    _signal_stats_change()


def send_room_expiry_alerts(today=None):
    """계약만기 90/60/30/7일 전 알림을 이메일과 알림함에 기록한다.

    인앱 알림을 먼저 영속화한 뒤 이메일을 보낸다. 이메일 호출 직전에
    ``attempting`` 상태와 Resend 멱등 키를 먼저 커밋한다. 호출 뒤 DB 장애가
    나도 다음 실행이 같은 멱등 키로 안전하게 재시도할 수 있다.
    """
    basis_date = today or date.today()
    conn = get_conn()
    cur = conn.cursor()
    acquired = False
    stats = {
        "target_count": 0,
        "sent_count": 0,
        "email_sent_count": 0,
        "in_app_count": 0,
        "failed_count": 0,
    }
    try:
        cur.execute(
            "SELECT pg_try_advisory_lock(%s) AS acquired",
            (ROOM_EXPIRY_ALERT_LOCK_ID,),
        )
        acquired = bool(cur.fetchone()["acquired"])
        if not acquired:
            print("[room-expiry] 이미 다른 실행이 진행 중입니다 — 이번 실행을 건너뜁니다.")
            return stats

        cur.execute("""
            WITH room_data AS (
                SELECT bri.id AS room_id,
                       bri.room_label,
                       bri.contract_end_date,
                       (bri.contract_end_date - %s::date) AS days_remaining,
                       lr.user_id,
                       u.email,
                       mb.building_name
                  FROM business_room_inventory bri
                  JOIN listing_requests lr ON lr.id = bri.listing_request_id
                  JOIN users u ON u.id = lr.user_id
                  JOIN master_buildings mb ON mb.id = lr.master_building_id
                 WHERE bri.status = '입실'
                   AND bri.contract_end_date IS NOT NULL
                   AND COALESCE(u.status, 'active') = 'active'
            )
            -- 새 알림은 오늘 정확히 90/60/30/7일 남은 방에만 만든다.
            SELECT rd.room_id, rd.room_label, rd.contract_end_date, rd.days_remaining,
                   rd.user_id, rd.email, rd.building_name,
                   rd.days_remaining::text AS alert_threshold,
                   NULL::INTEGER AS alert_id, NULL::TEXT AS email_state
              FROM room_data rd
             WHERE rd.days_remaining IN (90, 60, 30, 7)
               AND NOT EXISTS (
                   SELECT 1 FROM room_expiry_alerts_sent sent
                    WHERE sent.room_id = rd.room_id
                      AND sent.threshold = rd.days_remaining::text
               )

            UNION ALL

            -- 인앱 기록 뒤 이메일만 실패한 이력은 임계 날짜가 지나도 재시도한다.
            -- Resend 멱등 키 보관(24시간) 안에서만 자동 재시도해 중복을 막는다.
            SELECT rd.room_id, rd.room_label, rd.contract_end_date, rd.days_remaining,
                   rd.user_id, rd.email, rd.building_name,
                   sent.threshold AS alert_threshold,
                   sent.id AS alert_id, sent.email_state
              FROM room_data rd
              JOIN room_expiry_alerts_sent sent ON sent.room_id = rd.room_id
             WHERE NULLIF(BTRIM(rd.email), '') IS NOT NULL
               AND (
                   sent.email_state IN ('pending', 'failed')
                   OR (
                       sent.email_state IN ('failed', 'attempting')
                       AND sent.email_attempted_at >= NOW() - INTERVAL '23 hours'
                   )
               )
             ORDER BY contract_end_date, room_id
        """, (basis_date,))
        targets = cur.fetchall()
        stats["target_count"] = len(targets)
        cur.execute("""
            SELECT COUNT(*) AS count
              FROM room_expiry_alerts_sent sent
              JOIN business_room_inventory bri ON bri.id = sent.room_id
              JOIN listing_requests lr ON lr.id = bri.listing_request_id
              JOIN users u ON u.id = lr.user_id
             WHERE bri.status = '입실'
               AND bri.contract_end_date IS NOT NULL
               AND NULLIF(BTRIM(u.email), '') IS NOT NULL
               AND sent.email_state = 'attempting'
               AND (
                   sent.email_attempted_at IS NULL
                   OR sent.email_attempted_at < NOW() - INTERVAL '23 hours'
               )
        """)
        stale_email_attempts = int(cur.fetchone()["count"])
        if stale_email_attempts:
            print(
                f"[room-expiry] 이메일 멱등 재시도 안전 창이 지난 "
                f"{stale_email_attempts}건은 자동 재발송하지 않습니다. "
                "발송 이력 확인 후 수동 처리해주세요.",
                file=sys.stderr,
            )
        # 조회 트랜잭션을 닫고 각 항목을 즉시 커밋할 수 있게 한다.
        conn.commit()

        for target in targets:
            alert_threshold = int(target["alert_threshold"])
            building_name = target["building_name"] or "건물"
            raw_room_label = str(target["room_label"] or "")
            room_label = (
                raw_room_label
                if raw_room_label.endswith("호")
                else raw_room_label + "호"
            )
            expiry_date = target["contract_end_date"].strftime("%Y-%m-%d")
            title = (
                f"[홈앤스테이] {building_name} {room_label} "
                f"계약만료 {alert_threshold}일 전입니다."
            )
            body = f"만기일: {expiry_date}. 마이페이지에서 확인해주세요."
            email = (target["email"] or "").strip()
            alert_id = target["alert_id"]
            email_state = target["email_state"]

            # 새 대상은 알림함과 이력 행을 하나의 트랜잭션으로 먼저 남긴다.
            # 따라서 이메일 실패는 사이트 알림 수신을 막지 않는다.
            if not alert_id:
                try:
                    cur.execute("""
                        INSERT INTO room_expiry_alerts_sent
                            (room_id, threshold, email_state)
                        VALUES (%s, %s, %s)
                        RETURNING id
                    """, (
                        target["room_id"],
                        str(alert_threshold),
                        "pending" if email else "not_required",
                    ))
                    alert_id = cur.fetchone()["id"]
                    cur.execute("""
                        INSERT INTO notifications
                            (user_id, title, body, building_name)
                        VALUES (%s, %s, %s, %s)
                        RETURNING id
                    """, (target["user_id"], title, body, building_name))
                    notification_id = cur.fetchone()["id"]
                    cur.execute("""
                        UPDATE room_expiry_alerts_sent
                           SET notification_id=%s, in_app_sent_at=NOW()
                         WHERE id=%s
                    """, (notification_id, alert_id))
                    conn.commit()
                    stats["sent_count"] += 1
                    stats["in_app_count"] += 1
                    email_state = "pending" if email else "not_required"
                except Exception as exc:
                    conn.rollback()
                    stats["failed_count"] += 1
                    print(
                        f"[room-expiry] 인앱 알림 기록 실패(room_id={target['room_id']}): {exc}",
                        file=sys.stderr,
                    )
                    continue

            if not email or email_state not in ("pending", "failed", "attempting"):
                continue

            # 발송 시도와 멱등 키를 먼저 확정한다. 성공 응답 뒤 상태 갱신이
            # 실패해도 다음 실행이 같은 키로 재시도하므로 중복 이메일은 없다.
            try:
                cur.execute("""
                    UPDATE room_expiry_alerts_sent
                       SET email_state='attempting',
                           email_attempted_at=NOW(),
                           email_error=NULL,
                           email_idempotency_key=COALESCE(
                               email_idempotency_key,
                               'room-expiry/' || id::text
                           )
                     WHERE id=%s
                       AND email_state IN ('pending', 'failed', 'attempting')
                    RETURNING id, email_idempotency_key
                """, (alert_id,))
                claimed = cur.fetchone()
                conn.commit()
            except Exception as exc:
                conn.rollback()
                stats["failed_count"] += 1
                print(
                    f"[room-expiry] 이메일 발송 준비 실패(room_id={target['room_id']}): {exc}",
                    file=sys.stderr,
                )
                continue
            if not claimed:
                continue

            email_html = (
                f"<p>{html.escape(title)}</p>"
                f"<p>{html.escape(body)}</p>"
                '<p><a href="https://homenstay.com/mypage">'
                "마이페이지에서 확인하기</a></p>"
            )
            email_result = send_email(
                email,
                title,
                email_html,
                idempotency_key=claimed["email_idempotency_key"],
                detailed=True,
            )
            email_ok, email_message = email_result[:2]
            email_outcome = (
                email_result[2]
                if len(email_result) > 2
                else ("accepted" if email_ok else "definitive_failure")
            )
            next_email_state = (
                "sent" if email_ok
                else ("attempting" if email_outcome == "transport_error" else "failed")
            )
            try:
                cur.execute("""
                    UPDATE room_expiry_alerts_sent
                       SET email_state=%s,
                           email_sent_at=CASE WHEN %s THEN NOW() ELSE NULL END,
                           email_error=CASE WHEN %s THEN NULL ELSE %s END
                     WHERE id=%s AND email_state='attempting'
                """, (
                    next_email_state,
                    email_ok,
                    email_ok,
                    None if email_ok else str(email_message)[:500],
                    alert_id,
                ))
                conn.commit()
            except Exception as exc:
                conn.rollback()
                stats["failed_count"] += 1
                print(
                    f"[room-expiry] 이메일 후처리 기록 실패(room_id={target['room_id']}); "
                    f"다음 실행에서 멱등 키로 재시도합니다: {exc}",
                    file=sys.stderr,
                )
                continue
            if email_ok:
                stats["email_sent_count"] += 1
            else:
                stats["failed_count"] += 1
                print(f"[room-expiry] 이메일 발송 실패({email}): {email_message}")
        return stats
    finally:
        if acquired:
            try:
                cur.execute(
                    "SELECT pg_advisory_unlock(%s) AS released",
                    (ROOM_EXPIRY_ALERT_LOCK_ID,),
                )
                cur.fetchone()["released"]
            except Exception:
                pass
        cur.close()
        conn.close()


def _permit_change_summary_text(summary):
    labels = (
        ("new", "신규신고"),
        ("closed", "폐업"),
        ("status", "상태변경"),
        ("room", "호실변경"),
    )
    parts = [
        f"{label} {int(summary.get(key) or 0)}건"
        for key, label in labels
        if int(summary.get(key) or 0) > 0
    ]
    return ", ".join(parts) or "영업신고 정보가 변경됐어요"


def send_permit_change_alerts():
    """완료된 숙박업 동기화의 건물별 일일 신고변동을 한 번씩 전달한다."""
    conn = get_conn()
    cur = conn.cursor()
    acquired = False
    stats = {"target_count": 0, "in_app_count": 0, "email_sent_count": 0, "failed_count": 0}
    try:
        cur.execute(
            "SELECT pg_try_advisory_lock(%s) AS acquired",
            (PERMIT_CHANGE_ALERT_LOCK_ID,),
        )
        acquired = bool(cur.fetchone()["acquired"])
        if not acquired:
            print("[permit-alert] 이미 다른 신고변동 알림이 진행 중입니다 — 이번 실행을 건너뜁니다.")
            return stats
        cur.execute("""
            SELECT pcl.id, pcl.master_building_id, pcl.change_summary,
                   mb.building_name, mb.road_address, mb.jibun_address
              FROM permit_change_alert_logs pcl
              JOIN master_buildings mb ON mb.id = pcl.master_building_id
             WHERE pcl.delivery_queued_at IS NULL
               AND pcl.change_date >= %s
             ORDER BY pcl.change_date, pcl.id
        """, (_korean_today() - timedelta(days=7),))
        logs = cur.fetchall()
        stats["target_count"] = len(logs)
        for log_row in logs:
            summary = dict(log_row.get("change_summary") or {})
            summary_text = _permit_change_summary_text(summary)
            building_name = log_row.get("building_name") or "관심 단지"
            address = log_row.get("road_address") or log_row.get("jibun_address")
            title = f"{building_name} 영업신고 현황이 변경됐어요"
            had_storage_error = False
            cur.execute("""
                SELECT uf.user_id, u.email,
                       COALESCE(u.email_alert_enabled, TRUE) AS email_alert_enabled
                  FROM user_favorites uf
                  JOIN users u ON u.id = uf.user_id
                 WHERE uf.master_building_id=%s
                   AND uf.permit_change_alert_enabled=TRUE
                   AND COALESCE(u.status, 'active') = 'active'
            """, (log_row["master_building_id"],))
            recipients = cur.fetchall()
            for recipient in recipients:
                delivery_id = None
                try:
                    initial_email_state = (
                        "pending"
                        if recipient.get("email") and recipient.get("email_alert_enabled")
                        else "not_required"
                    )
                    cur.execute("""
                        INSERT INTO permit_change_alert_deliveries
                            (permit_change_alert_log_id, user_id, email_state)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (permit_change_alert_log_id, user_id) DO NOTHING
                        RETURNING id
                    """, (log_row["id"], recipient["user_id"], initial_email_state))
                    delivery = cur.fetchone()
                    if not delivery:
                        conn.commit()
                        continue
                    delivery_id = delivery["id"]
                    cur.execute("""
                        INSERT INTO notifications
                            (user_id, title, body, building_name, address, master_building_id)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        RETURNING id
                    """, (
                        recipient["user_id"], title, summary_text, building_name,
                        address, log_row["master_building_id"],
                    ))
                    notification_id = cur.fetchone()["id"]
                    cur.execute("""
                        UPDATE permit_change_alert_deliveries
                           SET notification_id=%s
                         WHERE id=%s
                    """, (notification_id, delivery_id))
                    conn.commit()
                    stats["in_app_count"] += 1
                except Exception as exc:
                    conn.rollback()
                    had_storage_error = True
                    stats["failed_count"] += 1
                    print(f"[permit-alert] 인앱 알림 기록 실패(log={log_row['id']}): {_redact(str(exc))[:300]}")
                    continue

                if not recipient.get("email") or not recipient.get("email_alert_enabled"):
                    continue
                try:
                    cur.execute("""
                        UPDATE permit_change_alert_deliveries
                           SET email_state='attempting', email_attempted_at=NOW()
                         WHERE id=%s AND email_state='pending'
                     RETURNING id
                    """, (delivery_id,))
                    if not cur.fetchone():
                        conn.rollback()
                        continue
                    conn.commit()
                    email_html = (
                        f"<p>{html.escape(title)}</p>"
                        f"<p>{html.escape(summary_text)}</p>"
                        '<p><a href="https://livingstay-realtrade.replit.app/mypage">'
                        "마이페이지에서 알림 설정 확인하기</a></p>"
                    )
                    ok, message = send_email(
                        recipient["email"], f"[홈앤스테이] {title}", email_html,
                        idempotency_key=f"permit-change/{log_row['id']}/{recipient['user_id']}",
                    )
                    cur.execute("""
                        UPDATE permit_change_alert_deliveries
                           SET email_state=%s,
                               email_sent_at=CASE WHEN %s THEN NOW() ELSE NULL END,
                               email_error=CASE WHEN %s THEN NULL ELSE %s END
                         WHERE id=%s AND email_state='attempting'
                    """, (
                        "sent" if ok else "failed", bool(ok), bool(ok),
                        None if ok else str(message or "")[:500], delivery_id,
                    ))
                    conn.commit()
                    if ok:
                        stats["email_sent_count"] += 1
                    else:
                        stats["failed_count"] += 1
                        print(f"[permit-alert] 이메일 발송 실패({recipient['email']}): {message}")
                except Exception as exc:
                    conn.rollback()
                    stats["failed_count"] += 1
                    print(f"[permit-alert] 이메일 처리 실패(log={log_row['id']}): {_redact(str(exc))[:300]}")
            if not had_storage_error:
                cur.execute("""
                    UPDATE permit_change_alert_logs
                       SET delivery_queued_at=NOW(), updated_at=NOW()
                     WHERE id=%s AND delivery_queued_at IS NULL
                """, (log_row["id"],))
                conn.commit()
        return stats
    finally:
        if acquired:
            try:
                cur.execute(
                    "SELECT pg_advisory_unlock(%s) AS released",
                    (PERMIT_CHANGE_ALERT_LOCK_ID,),
                )
                cur.fetchone()["released"]
                conn.commit()
            except Exception:
                conn.rollback()
        cur.close()
        conn.close()


# ---- 관리자 버튼용 상태 기록 (run_id 펜싱 + 하트비트) ----
def _read_status(status_key):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT value FROM app_meta WHERE key=%s", (status_key,))
        row = cur.fetchone()
    finally:
        cur.close()
        conn.close()
    if not row or not row["value"]:
        return None
    try:
        return json.loads(row["value"])
    except (TypeError, ValueError):
        return None


def _write_status(status_key, payload, run_id):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE app_meta SET value=%s, updated_at=NOW()
            WHERE key=%s AND (value::jsonb ->> 'run_id') = %s
        """, (json.dumps(payload, ensure_ascii=False), status_key, run_id))
        conn.commit()
    finally:
        cur.close()
        conn.close()


def _touch(status_key, run_id):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE app_meta SET updated_at=NOW()
            WHERE key=%s AND (value::jsonb ->> 'run_id') = %s
        """, (status_key, run_id))
        conn.commit()
    finally:
        cur.close()
        conn.close()


def _redact(text):
    redacted = text
    for env_name in (SERVICE_KEY_ENV, CAMPING_SERVICE_KEY_ENV):
        key = os.environ.get(env_name, "")
        if key:
            redacted = redacted.replace(key, "***")
    return redacted


def _signal_stats_change():
    """커밋된 원본 변경을 알리되 표식 실패는 배치를 실패시키지 않는다."""
    try:
        mark_master_stats_invalidated("lodgings")
        print("[lodgings] 통계 원본 캐시 무효화 표식을 갱신했습니다.")
    except Exception as exc:
        print(
            f"[lodgings] 통계 원본 캐시 표식 갱신 실패: "
            f"{_redact(str(exc))[:300]}"
        )


def _refresh_master_stats_after_completion():
    """수집 완료 직후 실행 중인 앱 워커의 통계 원본을 즉시 갱신한다."""
    try:
        secret = os.environ.get("SESSION_SECRET", "")
        if not secret:
            raise RuntimeError("SESSION_SECRET이 없어 내부 통계 갱신 요청을 서명할 수 없습니다.")
        timestamp = str(int(time.time()))
        signature = hmac.new(
            secret.encode("utf-8"),
            f"POST:/api/admin/stats/refresh:{timestamp}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        response = requests.post(
            _INTERNAL_STATS_REFRESH_URL,
            headers={
                "X-Stats-Refresh-Timestamp": timestamp,
                "X-Stats-Refresh-Signature": signature,
            },
            timeout=180,
        )
        payload = response.json()
        if not response.ok or not payload.get("ok"):
            raise RuntimeError(payload.get("message") or f"HTTP {response.status_code}")
        failed = [key for key, ok in (payload.get("sections") or {}).items() if not ok]
        print(
            f"[lodgings] 완료 후 통계 캐시 {'부분 실패: ' + ', '.join(failed) if failed else '갱신 완료'}"
        )
    except Exception as exc:
        print(f"[lodgings] 완료 후 통계 캐시 갱신 실패: {_redact(str(exc))[:300]}")


def _fetch_page(key, page, num_rows):
    resp = requests.get(API_URL, params={
        "serviceKey": key,
        "pageNo": str(page),
        "numOfRows": str(num_rows),
        "type": "json",
    }, timeout=60)
    resp.raise_for_status()
    try:
        data = resp.json()
    except ValueError:
        raise RuntimeError(f"JSON 파싱 실패: {_redact(resp.text[:200])}")
    header = (data.get("response") or {}).get("header") or {}
    code = str(header.get("resultCode", "")).strip()
    if code == "03":  # NODATA
        return [], 0
    if code not in ("00", "0", ""):
        raise RuntimeError(f"API 오류 resultCode={code} msg={header.get('resultMsg')}")
    body = (data.get("response") or {}).get("body") or {}
    items = body.get("items") or []
    if isinstance(items, dict):
        items = items.get("item") or []
    if isinstance(items, dict):
        items = [items]
    total = int(body.get("totalCount") or 0)
    return items, total


def _is_429(exc):
    """HTTP 429(속도 제한) 오류인지 판별."""
    resp = getattr(exc, "response", None)
    return getattr(resp, "status_code", None) == 429


def _fetch_page_retry(key, page, num_rows):
    """_fetch_page 1회 재시도 래퍼 (sync_brhub.py와 동일 패턴).
    - 일반 오류(타임아웃 등): 15초 대기 후 1회 재시도
    - 429(속도 제한): 45초 대기 후 1회 재시도
    - 재시도도 실패하면 예외를 그대로 전파(체크포인트는 호출부에서 보존됨)
    반환: (items, total, saw_429)"""
    try:
        items, total = _fetch_page(key, page, num_rows)
        return items, total, False
    except Exception as e:
        saw_429 = _is_429(e)
        wait = 45 if saw_429 else 15
        print(f"[lodgings] 페이지 {page} 오류: {_redact(repr(e))[:160]} — {wait}초 후 1회 재시도")
        time.sleep(wait)
        items, total = _fetch_page(key, page, num_rows)
        return items, total, saw_429


def _load_camping_progress(cur):
    cur.execute(
        "SELECT value FROM app_meta WHERE key=%s",
        (CAMPING_PROGRESS_META_KEY,),
    )
    row = cur.fetchone()
    if not row or not row["value"]:
        return {"next_page": 1, "total_count": None}
    try:
        data = json.loads(row["value"])
        return {
            "next_page": max(1, int(data.get("next_page", 1))),
            "total_count": data.get("total_count"),
        }
    except (TypeError, ValueError):
        return {"next_page": 1, "total_count": None}


def _save_camping_progress(cur, conn, next_page, total_count):
    payload = json.dumps({
        "next_page": next_page,
        "total_count": total_count,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    cur.execute("""
        INSERT INTO app_meta (key, value, updated_at) VALUES (%s, %s, NOW())
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
    """, (CAMPING_PROGRESS_META_KEY, payload))
    conn.commit()


def _clear_camping_progress(cur, conn):
    cur.execute(
        "DELETE FROM app_meta WHERE key=%s",
        (CAMPING_PROGRESS_META_KEY,),
    )
    conn.commit()


def _mark_camping_last_sync(cur, conn, total):
    payload = json.dumps({
        "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total": total,
    })
    cur.execute("""
        INSERT INTO app_meta (key, value, updated_at) VALUES (%s, %s, NOW())
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
    """, (CAMPING_LAST_SYNC_META_KEY, payload))
    conn.commit()


def _fetch_camping_page(key, page, num_rows):
    response = requests.get(
        CAMPING_API_URL,
        params={
            "serviceKey": key,
            "pageNo": str(page),
            "numOfRows": str(num_rows),
            "MobileOS": "ETC",
            "MobileApp": "LivingStay",
            "_type": "json",
        },
        timeout=60,
    )
    response.raise_for_status()
    try:
        data = response.json()
    except ValueError:
        raise RuntimeError(
            f"고캠핑 JSON 파싱 실패: {_redact(response.text[:200])}"
        )
    envelope = data.get("response") or {}
    header = envelope.get("header") or {}
    code = str(header.get("resultCode", "")).strip()
    if code not in ("0000", "00", "0", ""):
        raise RuntimeError(
            f"고캠핑 API 오류 resultCode={code} "
            f"msg={header.get('resultMsg')}"
        )
    body = envelope.get("body") or {}
    items = body.get("items") or []
    if isinstance(items, dict):
        items = items.get("item") or []
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list):
        raise RuntimeError("고캠핑 API items 형식이 목록이 아닙니다.")
    try:
        total = int(body.get("totalCount") or 0)
    except (TypeError, ValueError):
        total = 0
    return items, total


def _fetch_camping_page_retry(
    key, page, num_rows, *, on_attempt=None, retry_waits=(15, 45)
):
    """고캠핑 페이지를 최대 3회 시도하고, 각 실제 호출을 카운터에 반영한다."""
    for attempt in range(len(retry_waits) + 1):
        if on_attempt:
            on_attempt()
        try:
            return _fetch_camping_page(key, page, num_rows)
        except Exception as exc:
            if attempt >= len(retry_waits):
                raise
            wait = 45 if _is_429(exc) else retry_waits[attempt]
            print(
                f"[camping] 페이지 {page} 오류: "
                f"{_redact(repr(exc))[:160]} — {wait}초 후 재시도 "
                f"({attempt + 2}/{len(retry_waits) + 1})"
            )
            time.sleep(wait)


def _to_int(v):
    try:
        return int(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return 0


def _korean_today():
    """알림 중복 키는 서비스 기준일(KST)로 고정한다."""
    return (datetime.utcnow() + timedelta(hours=9)).date()


def _permit_number_for_item(it, biz_name, road_address, jibun_address):
    permit_number = (it.get("MNG_NO") or "").strip()
    if permit_number:
        return permit_number
    base = biz_name + "|" + (road_address or jibun_address or "")
    return "NOMNG:" + hashlib.sha256(base.encode("utf-8")).hexdigest()[:20]


def _permit_alert_snapshot_ready(cur):
    cur.execute(
        "SELECT value FROM app_meta WHERE key=%s",
        (PERMIT_ALERT_BOOTSTRAP_META_KEY,),
    )
    row = cur.fetchone()
    return bool(row and row.get("value") == "1")


def _mark_permit_alert_snapshot_ready(cur, conn):
    """최초 전체 수집이 끝난 뒤부터만 신규 신고 이벤트를 허용한다."""
    cur.execute("""
        INSERT INTO app_meta (key, value, updated_at) VALUES (%s, '1', NOW())
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
    """, (PERMIT_ALERT_BOOTSTRAP_META_KEY,))
    conn.commit()


def _unique_building_lookup(cur):
    """주소 정규화 키가 하나의 건물만 가리킬 때만 알림 연결에 사용한다."""
    cur.execute("""
        SELECT id, road_address, jibun_address, umd_nm, jibun
          FROM master_buildings
         WHERE COALESCE(lodging_type, '') <> 'mixed_use_excluded'
    """)
    road_candidates = {}
    jibun_candidates = {}
    for row in cur.fetchall():
        road_key = normalize_road_prefix(row.get("road_address"))
        jibun_key = get_building_jibun_key(row)
        if road_key:
            road_candidates.setdefault(road_key, set()).add(row["id"])
        if jibun_key:
            jibun_candidates.setdefault(jibun_key, set()).add(row["id"])
    return (
        {key: next(iter(ids)) for key, ids in road_candidates.items() if len(ids) == 1},
        {key: next(iter(ids)) for key, ids in jibun_candidates.items() if len(ids) == 1},
    )


def _building_id_for_lodging_item(it, road_lookup, jibun_lookup):
    keys = _lodging_item_match_keys(it)
    if not keys:
        return None
    road_key, jibun_key = keys
    return (road_lookup.get(road_key) if road_key else None) or (
        jibun_lookup.get(jibun_key) if jibun_key else None
    )


def _is_closed_status(status_name, status_detail):
    text = f"{status_name or ''} {status_detail or ''}"
    return "폐업" in text


def _add_permit_change_summary(cur, building_id, changes):
    """같은 건물·같은 KST 날짜의 여러 변화를 하나의 요약 행에 누적한다."""
    if not building_id or not changes:
        return
    change_date = _korean_today()
    cur.execute("""
        SELECT id, change_summary
          FROM permit_change_alert_logs
         WHERE master_building_id=%s AND change_date=%s
         FOR UPDATE
    """, (building_id, change_date))
    row = cur.fetchone()
    if row:
        summary = dict(row.get("change_summary") or {})
        for key, count in changes.items():
            summary[key] = int(summary.get(key) or 0) + int(count or 0)
        cur.execute("""
            UPDATE permit_change_alert_logs
               SET change_summary=%s::jsonb, updated_at=NOW()
             WHERE id=%s
        """, (json.dumps(summary), row["id"]))
        return
    cur.execute("""
        INSERT INTO permit_change_alert_logs
            (master_building_id, change_date, change_summary)
        VALUES (%s, %s, %s::jsonb)
    """, (building_id, change_date, json.dumps(changes)))


def _record_permit_alert_snapshot(cur, *, permit_number, building_id,
                                  status_name, status_detail, room_count,
                                  alerts_enabled):
    """현재 상태를 기록하고, 기준 스냅샷 이후의 네 가지 변화만 집계한다."""
    cur.execute("""
        SELECT master_building_id, biz_status_name, biz_status_detail, room_count
          FROM lodging_registry_alert_snapshots
         WHERE permit_number=%s
         FOR UPDATE
    """, (permit_number,))
    previous = cur.fetchone()
    if previous is None:
        cur.execute("""
            INSERT INTO lodging_registry_alert_snapshots
                (permit_number, master_building_id, biz_status_name, biz_status_detail, room_count)
            VALUES (%s, %s, %s, %s, %s)
        """, (permit_number, building_id, status_name, status_detail, room_count))
        if alerts_enabled and building_id:
            _add_permit_change_summary(cur, building_id, {"new": 1})
        return

    previous_building_id = previous.get("master_building_id")
    effective_building_id = building_id or previous_building_id
    changes = {}
    old_closed = _is_closed_status(
        previous.get("biz_status_name"), previous.get("biz_status_detail")
    )
    new_closed = _is_closed_status(status_name, status_detail)
    if not old_closed and new_closed:
        changes["closed"] = 1
    elif (
        previous.get("biz_status_name") != status_name
        or previous.get("biz_status_detail") != status_detail
    ):
        changes["status"] = 1
    if previous.get("room_count") != room_count:
        changes["room"] = 1
    cur.execute("""
        UPDATE lodging_registry_alert_snapshots
           SET master_building_id=%s,
               biz_status_name=%s,
               biz_status_detail=%s,
               room_count=%s,
               updated_at=NOW()
         WHERE permit_number=%s
    """, (effective_building_id, status_name, status_detail, room_count, permit_number))
    if alerts_enabled and effective_building_id:
        _add_permit_change_summary(cur, effective_building_id, changes)


def _upsert(cur, it, *, building_id=None, permit_alerts_enabled=False):
    """수집 대상 생활·일반숙박 업태 1행 UPSERT. 저장 시 True."""
    hygiene = normalize_hygiene_type(
        it.get("SNTTN_BZSTAT_NM") or it.get("BZSTAT_SE_NM")
    )
    if not is_target_lodging_hygiene(hygiene):
        return False
    biz_name = (it.get("BPLC_NM") or "").strip()
    if not biz_name:
        return False
    road_address = (it.get("ROAD_NM_ADDR") or "").strip() or None
    jibun_address = (it.get("LOTNO_ADDR") or "").strip() or None
    permit_number = _permit_number_for_item(it, biz_name, road_address, jibun_address)
    room_count = _to_int(it.get("KSRM_CNT")) + _to_int(it.get("WSRM_CNT"))
    status_name = (it.get("SALS_STTS_NM") or "").strip() or None
    status_detail = (it.get("DTL_SALS_STTS_NM") or "").strip() or None
    cur.execute("""
        INSERT INTO lodging_registry
            (biz_name, permit_number, road_address, jibun_address, permit_date,
             biz_status_name, biz_status_detail, room_count, hygiene_type, phone,
             road_norm, jibun_norm, biz_name_norm, source_updated_at, updated_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
        ON CONFLICT (permit_number) DO UPDATE SET
            biz_name = EXCLUDED.biz_name,
            road_address = EXCLUDED.road_address,
            jibun_address = EXCLUDED.jibun_address,
            permit_date = EXCLUDED.permit_date,
            biz_status_name = EXCLUDED.biz_status_name,
            biz_status_detail = EXCLUDED.biz_status_detail,
            room_count = EXCLUDED.room_count,
            hygiene_type = EXCLUDED.hygiene_type,
            phone = EXCLUDED.phone,
            road_norm = EXCLUDED.road_norm,
            jibun_norm = EXCLUDED.jibun_norm,
            biz_name_norm = EXCLUDED.biz_name_norm,
            source_updated_at = EXCLUDED.source_updated_at,
            updated_at = NOW()
         WHERE (
             lodging_registry.biz_name,
             lodging_registry.road_address,
             lodging_registry.jibun_address,
             lodging_registry.permit_date,
             lodging_registry.biz_status_name,
             lodging_registry.biz_status_detail,
             lodging_registry.room_count,
             lodging_registry.hygiene_type,
             lodging_registry.phone,
             lodging_registry.road_norm,
             lodging_registry.jibun_norm,
             lodging_registry.biz_name_norm,
             lodging_registry.source_updated_at
         ) IS DISTINCT FROM (
             EXCLUDED.biz_name,
             EXCLUDED.road_address,
             EXCLUDED.jibun_address,
             EXCLUDED.permit_date,
             EXCLUDED.biz_status_name,
             EXCLUDED.biz_status_detail,
             EXCLUDED.room_count,
             EXCLUDED.hygiene_type,
             EXCLUDED.phone,
             EXCLUDED.road_norm,
             EXCLUDED.jibun_norm,
             EXCLUDED.biz_name_norm,
             EXCLUDED.source_updated_at
         )
    """, (biz_name, permit_number, road_address, jibun_address,
          (it.get("LCPMT_YMD") or "").strip() or None,
           status_name, status_detail,
          room_count, hygiene,
          (it.get("TELNO") or "").strip() or None,
          normalize_road_prefix(road_address),
          normalize_jibun_prefix(jibun_address),
          normalize_name(biz_name),
           (it.get("DAT_UPDT_PNT") or "").strip() or None))
    changed = bool(cur.rowcount)
    _record_permit_alert_snapshot(
        cur,
        permit_number=permit_number,
        building_id=building_id,
        status_name=status_name,
        status_detail=status_detail,
        room_count=room_count,
        alerts_enabled=permit_alerts_enabled,
    )
    return changed


def _lodging_item_match_keys(it):
    """자동명명 후보를 찾기 위한 수집 항목의 주소 정규화 키."""
    hygiene = normalize_hygiene_type(
        it.get("SNTTN_BZSTAT_NM") or it.get("BZSTAT_SE_NM")
    )
    if not is_target_lodging_hygiene(hygiene):
        return None
    if not (it.get("BPLC_NM") or "").strip():
        return None
    return (
        normalize_road_prefix((it.get("ROAD_NM_ADDR") or "").strip() or None),
        normalize_jibun_prefix((it.get("LOTNO_ADDR") or "").strip() or None),
    )


def _building_ids_for_lodging_keys(cur, match_keys):
    """그날 UPSERT한 신고 주소와 매칭되는 미확정 일반숙박 건물 ID를 찾는다."""
    road_norms = {road for road, _ in match_keys if road}
    jibun_norms = {jibun for _, jibun in match_keys if jibun}
    if not road_norms and not jibun_norms:
        return set()

    # master_buildings에는 lodging_registry처럼 정규화 키가 저장되지 않으므로
    # 후보 건물만 읽어 동일한 주소 정규화 함수를 적용한다. 이 조회는 캡 시점에
    # 한 번만 수행하고, 실제 자동명명 재계산은 매칭된 ID로 제한한다.
    cur.execute("""
        SELECT id, road_address, jibun_address
          FROM master_buildings
         WHERE name_pending IS TRUE
           AND lodging_type = '일반'
    """)
    ids = set()
    for row in cur.fetchall():
        road_norm = normalize_road_prefix(row.get("road_address"))
        jibun_norm = get_building_jibun_key(row)
        if (road_norm and road_norm in road_norms) or (
            jibun_norm and jibun_norm in jibun_norms
        ):
            ids.add(row["id"])
    return ids


def _refresh_daily_auto_building_names(conn, match_keys):
    """오늘 처리한 주소에 해당하는 자동명칭만 갱신한다."""
    if not match_keys:
        return 0
    cur = conn.cursor()
    try:
        building_ids = _building_ids_for_lodging_keys(cur, match_keys)
    finally:
        cur.close()
    if not building_ids:
        return 0
    return refresh_auto_building_names(conn, sorted(building_ids))


def reindex_lodging_norms():
    """기존 lodging_registry 주소의 정규화 키를 현재 규칙으로 재계산한다."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id, road_address, jibun_address FROM lodging_registry")
        rows = cur.fetchall()
        updates = []
        for row in rows:
            updates.append((
                row["id"],
                normalize_road_prefix(row["road_address"]),
                normalize_jibun_prefix(row["jibun_address"]),
            ))

        updated = 0
        for start in range(0, len(updates), 1000):
            batch = updates[start:start + 1000]
            execute_values(
                cur,
                """
                UPDATE lodging_registry AS lr
                   SET road_norm = values.road_norm,
                       jibun_norm = values.jibun_norm,
                       updated_at = NOW()
                  FROM (VALUES %s) AS values(id, road_norm, jibun_norm)
                 WHERE lr.id = values.id
                   AND (lr.road_norm IS DISTINCT FROM values.road_norm
                        OR lr.jibun_norm IS DISTINCT FROM values.jibun_norm)
                """,
                batch,
                template="(%s, %s, %s)",
                page_size=len(batch),
            )
            updated += cur.rowcount
        conn.commit()
        if updated:
            _signal_stats_change()
        renamed = refresh_auto_building_names(conn)
        if renamed:
            _signal_stats_change()
        print(f"[lodgings] 정규화 키 재계산 완료 — 전체 {len(rows)}건, 변경 {updated}건")
        print(f"[lodgings] 신고 기준 자동명칭 재계산 완료 — 변경 {renamed}건")
        return updated
    finally:
        cur.close()
        conn.close()


def _still_owner(cur, status_key, run_id):
    """상태행 소유권 확인 — 다른 실행이 상태를 가져갔으면 False (관리자 버튼 실행일 때만 사용)."""
    cur.execute("SELECT value FROM app_meta WHERE key=%s", (status_key,))
    row = cur.fetchone()
    if not row or not row["value"]:
        return False
    try:
        d = json.loads(row["value"])
    except (TypeError, ValueError):
        return False
    return d.get("run_id") == run_id and d.get("state") == "running"


def _reconcile_camping_source_key(cur, data):
    """유일하게 같은 XLSX 캠핑 행이 있으면 고캠핑 contentId 키로 승계한다."""
    road_norm = data.get("road_norm")
    jibun_norm = data.get("jibun_norm")
    if not data.get("biz_name_norm") or not (road_norm or jibun_norm):
        return False

    cur.execute(
        "SELECT id FROM lodging_registry WHERE permit_number=%s",
        (data["permit_number"],),
    )
    canonical = cur.fetchone()
    cur.execute("""
        SELECT id, applied_building_id
          FROM lodging_registry
         WHERE permit_number LIKE 'CAMPING:%:%'
           AND hygiene_type = %s
           AND biz_name_norm = %s
           AND (
                (%s IS NOT NULL AND road_norm = %s)
                OR (%s IS NOT NULL AND jibun_norm = %s)
           )
         ORDER BY id
         LIMIT 2
         FOR UPDATE
    """, (
        camping_importer.HYGIENE_TYPE_FIXED,
        data["biz_name_norm"],
        road_norm,
        road_norm,
        jibun_norm,
        jibun_norm,
    ))
    legacy_rows = cur.fetchall()
    if len(legacy_rows) != 1:
        return False
    legacy = legacy_rows[0]

    if canonical:
        cur.execute("""
            UPDATE lodging_registry
               SET applied_building_id = COALESCE(
                       applied_building_id, %s
                   )
             WHERE id = %s
        """, (legacy.get("applied_building_id"), canonical["id"]))
        cur.execute(
            "DELETE FROM lodging_registry WHERE id=%s",
            (legacy["id"],),
        )
    else:
        cur.execute(
            "UPDATE lodging_registry SET permit_number=%s WHERE id=%s",
            (data["permit_number"], legacy["id"]),
        )
    return True


def sync_camping(
    num_rows=CAMPING_NUM_ROWS_DEFAULT,
    sleep_sec=SLEEP_DEFAULT,
    max_calls=CAMPING_MAX_DAILY_CALLS,
    reset=False,
    dry_run=False,
    status_key=None,
    run_id=None,
):
    """한국관광공사 고캠핑 목록을 CAMPING 원본키로 이어받아 동기화한다."""
    key = os.environ.get(CAMPING_SERVICE_KEY_ENV, "")
    if not key:
        raise RuntimeError(
            f"환경변수 {CAMPING_SERVICE_KEY_ENV} 가 설정되어 있지 않습니다."
        )
    if num_rows < 1 or max_calls < 1:
        raise ValueError("num_rows와 max_calls는 1 이상이어야 합니다.")

    conn = get_conn()
    cur = conn.cursor()
    counters = {
        "inserted": 0,
        "updated": 0,
        "matched": 0,
        "created": 0,
        "inactive": 0,
        "unmatched": 0,
        "skipped": 0,
    }
    try:
        camping_importer.common._assert_schema(cur)
        if reset and not dry_run:
            _clear_camping_progress(cur, conn)
        progress = _load_camping_progress(cur)
        page = 1 if (reset and dry_run) else progress["next_page"]
        total_count = progress["total_count"]
        calls_today = _daily_calls_today(cur, CAMPING_DAILY_CALLS_META_KEY)
        processed = 0
        sample_count = 0

        road_index = jibun_index = None
        bjdong = None
        if not dry_run:
            road_index, jibun_index = (
                camping_importer.common._load_master_indexes(cur)
            )

        def _count_attempt():
            nonlocal calls_today
            if calls_today >= max_calls:
                raise _CampingDailyCapReached
            calls_today = _bump_daily_calls(
                cur, conn, CAMPING_DAILY_CALLS_META_KEY
            )

        while True:
            if status_key and run_id and not _still_owner(cur, status_key, run_id):
                raise RuntimeError("캠핑 동기화 소유권 상실(다른 실행이 시작됨)")
            if calls_today >= max_calls:
                print(
                    f"[camping] 일일 소프트 캡({max_calls}건) 도달 — "
                    f"다음 페이지 {page}부터 이어서 실행합니다."
                )
                return False, counters, calls_today

            print(
                f"[camping] 페이지 {page} 호출 "
                f"(오늘 {calls_today + 1}/{max_calls})"
            )
            try:
                items, total = _fetch_camping_page_retry(
                    key,
                    page,
                    num_rows,
                    on_attempt=_count_attempt,
                )
            except _CampingDailyCapReached:
                print(
                    f"[camping] 재시도 전 일일 소프트 캡({max_calls}건) "
                    f"도달 — 페이지 {page}부터 이어서 실행합니다."
                )
                return False, counters, calls_today
            if total:
                total_count = total
            if not items:
                if not dry_run:
                    _clear_camping_progress(cur, conn)
                    cur.execute("""
                        SELECT COUNT(*) AS c
                          FROM lodging_registry
                         WHERE permit_number LIKE 'CAMPING:%'
                    """)
                    _mark_camping_last_sync(
                        cur, conn, cur.fetchone()["c"]
                    )
                print(
                    f"[camping] 전체 수집 완료 — 이번 실행 처리 "
                    f"{processed:,}건"
                )
                return True, counters, calls_today

            for item in items:
                data = camping_importer.parse_api_item(item)
                if not data:
                    counters["skipped"] += 1
                    continue
                processed += 1
                if dry_run:
                    if sample_count < camping_importer.DRY_RUN_SAMPLE_LIMIT:
                        print(
                            f"  [DRY] {data['permit_number']} | "
                            f"{data['biz_name']} | "
                            f"{data['biz_status_name'] or '-'} | "
                            f"사이트 "
                            f"{data['camping_site_count'] if data['camping_site_count'] is not None else '-'}"
                        )
                        sample_count += 1
                    continue

                _reconcile_camping_source_key(cur, data)
                registry = camping_importer.common._upsert_registry(
                    cur,
                    data,
                    reset_applied_building_id=False,
                )
                counters[
                    "inserted" if registry["is_new"] else "updated"
                ] += 1

                building_id = None
                new_building_id = None
                if data["biz_status_name"] != ACTIVE_STATUS:
                    counters["inactive"] += 1
                elif not data.get("road_norm") and not data.get("jibun_norm"):
                    counters["unmatched"] += 1
                else:
                    building_id, match_reason = (
                        camping_importer.common._match_master(
                            data, road_index, jibun_index
                        )
                    )
                    if building_id:
                        counters["matched"] += 1
                    elif match_reason:
                        counters["unmatched"] += 1
                        print(
                            f"  [검토] {data['biz_name']} — {match_reason}: "
                            f"{data['road_address'] or '-'}"
                        )
                    else:
                        if bjdong is None:
                            bjdong = camping_importer.common.BjdongMap(
                                camping_importer.common.BJDONG_CODE_CSV
                            )
                        location = (
                            camping_importer.common._location_from_addresses(
                                bjdong,
                                data.get("road_address"),
                                data.get("jibun_address"),
                            )
                        )
                        if location:
                            building_id = camping_importer._create_master(
                                cur, data, location
                            )
                            new_building_id = building_id
                            counters["created"] += 1
                        else:
                            counters["unmatched"] += 1

                if building_id:
                    cur.execute(
                        "UPDATE lodging_registry "
                        "SET applied_building_id=%s WHERE id=%s",
                        (building_id, registry["id"]),
                    )
                if new_building_id:
                    camping_importer.common._register_new_master_in_indexes(
                        new_building_id, data, road_index, jibun_index
                    )

            if not dry_run:
                conn.commit()
                _signal_stats_change()
            next_page = page + 1
            if not dry_run:
                _save_camping_progress(
                    cur, conn, next_page, total_count
                )
            print(
                f"[camping] 페이지 {page} 완료 — 응답 {len(items):,}건 / "
                f"이번 실행 처리 {processed:,}건 / 전체 {total_count or '?'}건"
            )

            completed = (
                bool(total_count)
                and ((page - 1) * num_rows + len(items) >= total_count)
            )
            page = next_page
            if completed:
                if not dry_run:
                    _clear_camping_progress(cur, conn)
                    cur.execute("""
                        SELECT COUNT(*) AS c
                          FROM lodging_registry
                         WHERE permit_number LIKE 'CAMPING:%'
                    """)
                    _mark_camping_last_sync(
                        cur, conn, cur.fetchone()["c"]
                    )
                print(
                    f"[camping] 전체 수집 완료 — 이번 실행 처리 "
                    f"{processed:,}건"
                )
                return True, counters, calls_today
            time.sleep(sleep_sec)
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def sync_lodgings(num_rows=NUM_ROWS_DEFAULT, sleep_sec=SLEEP_DEFAULT,
                  max_calls=MAX_DAILY_CALLS, reset=False,
                  status_key=None, run_id=None):
    key = os.environ.get(SERVICE_KEY_ENV, "")
    if not key:
        raise RuntimeError(f"환경변수 {SERVICE_KEY_ENV} 가 설정되어 있지 않습니다.")

    conn = get_conn()
    cur = conn.cursor()
    try:
        if reset:
            _clear_progress(cur, conn)
        prog = _load_progress(cur)
        page = prog["next_page"]
        total_count = prog["total_count"]
        processed = 0
        page_size = None  # 실제 페이지 크기 — API가 numOfRows보다 적게 줄 수 있어 응답으로 판정
        calls_today = _daily_calls_today(cur, DAILY_CALLS_META_KEY)
        first_item_logged = False
        daily_match_keys = set()
        # 기준 스냅샷이 아직 없을 때는 전체 수집 완료 전까지 알림을 만들지 않는다.
        permit_alerts_enabled = _permit_alert_snapshot_ready(cur)
        road_buildings, jibun_buildings = _unique_building_lookup(cur)

        while True:
            # run_id 펜싱: 상태행 소유권을 잃었으면(다른 실행이 시작됨) 즉시 중단 —
            # 구 프로세스가 체크포인트/카운터/레지스트리를 계속 갱신하는 split-brain 방지.
            if status_key and run_id and not _still_owner(cur, status_key, run_id):
                print("[lodgings] 다른 실행이 상태를 가져갔습니다 — 이 실행을 중단합니다.")
                raise RuntimeError("동기화 소유권 상실(다른 실행이 시작됨)")
            if calls_today >= max_calls:
                print(f"[lodgings] 일일 소프트 캡({max_calls}건) 도달 — 내일 이어서 진행 "
                      f"(다음 페이지 {page} 저장됨)")
                renamed = _refresh_daily_auto_building_names(conn, daily_match_keys)
                if renamed:
                    _signal_stats_change()
                print(f"[lodgings] 오늘 처리분 신고 기준 자동명칭 반영 — 변경 {renamed}건")
                return False, processed, calls_today

            calls_today = _bump_daily_calls(
                cur, conn, DAILY_CALLS_META_KEY
            )
            print(f"[lodgings] 페이지 {page} 호출 (오늘 {calls_today}/{max_calls})")
            items, total, saw_429 = _fetch_page_retry(key, page, num_rows)
            if saw_429:
                # 속도 제한을 맞았으므로 이후 요청 간격을 2배로(최대 10초) 늘려 재발 방지
                sleep_sec = min(max(sleep_sec, 0.1) * 2, 10.0)
                print(f"[lodgings] 429 감지 — 이후 요청 간격을 {sleep_sec:.1f}초로 늘립니다")
            if total:
                total_count = total

            if not items:
                _clear_progress(cur, conn)
                cur.execute("SELECT COUNT(*) AS c FROM lodging_registry")
                total_rows = cur.fetchone()["c"]
                _mark_last_sync(cur, conn, total_rows)
                if not permit_alerts_enabled:
                    _mark_permit_alert_snapshot_ready(cur, conn)
                renamed = refresh_auto_building_names(conn)
                if renamed:
                    _signal_stats_change()
                print(f"[lodgings] 전체 수집 완료 — 대상 숙박업 누적 {total_rows}건")
                return True, processed, calls_today

            if not first_item_logged:
                print(f"[lodgings] 응답 필드: {sorted(items[0].keys())}")
                first_item_logged = True

            saved = 0
            for it in items:
                building_id = _building_id_for_lodging_item(
                    it, road_buildings, jibun_buildings
                )
                changed = _upsert(
                    cur, it, building_id=building_id,
                    permit_alerts_enabled=permit_alerts_enabled,
                )
                if changed:
                    saved += 1
                match_keys = _lodging_item_match_keys(it)
                if match_keys:
                    daily_match_keys.add(match_keys)
            conn.commit()
            if saved:
                _signal_stats_change()
            processed += saved
            page += 1
            _save_progress(cur, conn, page, total_count)
            print(f"[lodgings] 대상 숙박업 {saved}건 저장/{len(items)}건 검사 "
                  f"(누적 이번 실행 {processed}건, 전체 {total_count or '?'}건 중 페이지 {page - 1} 완료)")

            # 완료 판정은 '실제' 페이지 크기 기준 — 요청 numOfRows보다 적게 내려오는 경우가 있음(실측 100행).
            if page_size is None or len(items) > page_size:
                page_size = len(items)
            if total_count and page_size and (page - 1) * page_size >= total_count:
                _clear_progress(cur, conn)
                cur.execute("SELECT COUNT(*) AS c FROM lodging_registry")
                total_rows = cur.fetchone()["c"]
                _mark_last_sync(cur, conn, total_rows)
                if not permit_alerts_enabled:
                    _mark_permit_alert_snapshot_ready(cur, conn)
                renamed = refresh_auto_building_names(conn)
                if renamed:
                    _signal_stats_change()
                print(f"[lodgings] 전체 수집 완료 — 대상 숙박업 누적 {total_rows}건")
                return True, processed, calls_today

            time.sleep(sleep_sec)
    finally:
        cur.close()
        conn.close()


def _run(args):
    if args.reindex_norms:
        reindex_lodging_norms()
        _refresh_master_stats_after_completion()
        return

    if bool(getattr(args, "camping", False)):
        _run_camping(args)
        return

    run_id = None
    stop_beat = threading.Event()
    if args.status_key:
        status = _read_status(args.status_key)
        if not status or status.get("state") != "running":
            print("[lodgings] running 상태가 아니므로 종료합니다.")
            return
        run_id = status.get("run_id") or ""

        def _beat():
            while not stop_beat.wait(HEARTBEAT_SEC):
                try:
                    _touch(args.status_key, run_id)
                except Exception:
                    pass
        threading.Thread(target=_beat, daemon=True).start()

    error = None
    completed, processed, calls_today = False, 0, None
    try:
        completed, processed, calls_today = sync_lodgings(
            num_rows=args.num_rows or NUM_ROWS_DEFAULT, sleep_sec=args.sleep,
            max_calls=args.max_calls or MAX_DAILY_CALLS, reset=args.reset,
            status_key=args.status_key, run_id=run_id)
    except Exception as e:
        error = _redact(str(e))[:500]
        print(f"[lodgings] 실패: {error}")

    lodging_error = error
    camping_completed = None
    camping_counters = None
    camping_calls_today = None
    camping_error = None
    include_camping = bool(getattr(args, "include_camping", False))
    if include_camping:
        try:
            (
                camping_completed,
                camping_counters,
                camping_calls_today,
            ) = sync_camping(
                num_rows=CAMPING_NUM_ROWS_DEFAULT,
                sleep_sec=args.sleep,
                max_calls=CAMPING_MAX_DAILY_CALLS,
                reset=False,
                dry_run=False,
                status_key=args.status_key,
                run_id=run_id,
            )
        except Exception as exc:
            camping_error = _redact(str(exc))[:500]
            print(f"[camping] 실패: {camping_error}")
        error = lodging_error or camping_error

    if (
        (not lodging_error and completed)
        or (
            include_camping
            and not camping_error
            and camping_completed
        )
    ):
        _refresh_master_stats_after_completion()

    if not lodging_error and completed:
        try:
            permit_stats = send_permit_change_alerts()
            print(
                "[permit-alert] 대상 {target_count}건, 인앱 {in_app_count}건, "
                "이메일 {email_sent_count}건, 실패 {failed_count}건".format(**permit_stats)
            )
        except Exception as e:
            print(f"[permit-alert] 배치 실패: {_redact(str(e))[:500]}")

    # 숙박업 수집과 독립적으로 매일 계약만기 알림을 점검한다.
    # 수집 실패나 이메일 설정 문제로 숙박업 배치 자체가 실패하지 않게 한다.
    try:
        expiry_stats = send_room_expiry_alerts()
        print(
            "[room-expiry] 대상 {target_count}건, "
            "발송 {sent_count}건 (이메일 {email_sent_count}건, "
            "인앱 {in_app_count}건, 실패 {failed_count}건)".format(**expiry_stats)
        )
    except Exception as e:
        print(f"[room-expiry] 배치 실패: {_redact(str(e))[:500]}")

    if args.status_key and run_id is not None:
        stop_beat.set()
        status = _read_status(args.status_key) or {}
        status.update({
            "state": "failed" if error else "done",
            "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "processed": processed,
            "completed": (None if error else completed),
            "calls_today": calls_today,
            "camping_completed": camping_completed,
            "camping_counters": camping_counters,
            "camping_calls_today": camping_calls_today,
            "camping_error": camping_error,
            "error": error,
        })
        for attempt in range(3):
            try:
                _write_status(args.status_key, status, run_id)
                break
            except Exception as e:
                print(f"[lodgings] 상태 저장 실패({attempt + 1}/3): {e}")
                time.sleep(5)
    if error and not args.status_key:
        sys.exit(1)


def _run_camping(args):
    run_id = None
    stop_beat = threading.Event()
    if args.status_key:
        status = _read_status(args.status_key)
        if not status or status.get("state") != "running":
            print("[camping] running 상태가 아니므로 종료합니다.")
            return
        run_id = status.get("run_id") or ""

        def _beat():
            while not stop_beat.wait(HEARTBEAT_SEC):
                try:
                    _touch(args.status_key, run_id)
                except Exception:
                    pass
        threading.Thread(target=_beat, daemon=True).start()

    error = None
    completed = False
    counters = {}
    calls_today = None
    try:
        completed, counters, calls_today = sync_camping(
            num_rows=args.num_rows or CAMPING_NUM_ROWS_DEFAULT,
            sleep_sec=args.sleep,
            max_calls=args.max_calls or CAMPING_MAX_DAILY_CALLS,
            reset=args.reset,
            dry_run=args.dry_run,
            status_key=args.status_key,
            run_id=run_id,
        )
    except Exception as exc:
        error = _redact(str(exc))[:500]
        print(f"[camping] 실패: {error}")

    if not error and completed and not args.dry_run:
        _refresh_master_stats_after_completion()

    if args.status_key and run_id is not None:
        stop_beat.set()
        status = _read_status(args.status_key) or {}
        status.update({
            "state": "failed" if error else "done",
            "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "completed": None if error else completed,
            "counters": counters,
            "calls_today": calls_today,
            "dry_run": bool(args.dry_run),
            "error": error,
        })
        for attempt in range(3):
            try:
                _write_status(args.status_key, status, run_id)
                break
            except Exception as exc:
                print(
                    f"[camping] 상태 저장 실패({attempt + 1}/3): {exc}"
                )
                time.sleep(5)
    if error and not args.status_key:
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--num-rows", type=int, default=None)
    parser.add_argument("--sleep", type=float, default=SLEEP_DEFAULT)
    parser.add_argument("--max-calls", type=int, default=None)
    parser.add_argument("--reset", action="store_true")
    parser.add_argument(
        "--camping",
        action="store_true",
        help="한국관광공사 고캠핑 API를 별도 체크포인트로 수집",
    )
    parser.add_argument(
        "--include-camping",
        action="store_true",
        help="일반 숙박업 수집 뒤 고캠핑 API도 이어서 수집",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "고캠핑 API를 조회·검증하되 레지스트리·체크포인트는 변경하지 않음 "
            "(실제 호출량은 일일 카운터에 반영)"
        ),
    )
    parser.add_argument("--reindex-norms", action="store_true")
    parser.add_argument("--status-key", default=None)
    args = parser.parse_args()

    with _lodging_sync_lock() as acquired:
        if acquired:
            _run(args)
        else:
            # 호출자가 실제 수집이 시작되지 않았음을 구분할 수 있어야 한다.
            # 특히 scheduled_sync가 잠금 충돌을 성공 완료로 기록하면 안 된다.
            print("[lodgings] 다른 숙박 동기화가 실행 중이어서 시작하지 못했습니다.")
            raise SystemExit(75)


if __name__ == "__main__":
    main()
