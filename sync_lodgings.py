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
from datetime import date, datetime

import requests
from psycopg2.extras import execute_values

from addr_norm import (
    get_building_jibun_key,
    normalize_name,
    normalize_road_prefix,
    normalize_jibun_prefix,
)
from db import get_conn
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

MAX_DAILY_CALLS = 8000  # 일일 쿼터 10,000 — 여유분을 남기고 멈춘다.
DAILY_CALLS_META_KEY = "lodging_daily_calls"
PROGRESS_META_KEY = "lodging_sync_progress"
LAST_SYNC_META_KEY = "lodging_last_sync"
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
ROOM_EXPIRY_THRESHOLDS = (90, 60, 30, 7)


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


def _daily_calls_today(cur):
    cur.execute("SELECT value FROM app_meta WHERE key=%s", (DAILY_CALLS_META_KEY,))
    row = cur.fetchone()
    if not row or not row["value"]:
        return 0
    try:
        data = json.loads(row["value"])
        if data.get("date") == datetime.now().strftime("%Y-%m-%d"):
            return int(data.get("count", 0))
    except (TypeError, ValueError):
        pass
    return 0


def _bump_daily_calls(cur, conn):
    today = datetime.now().strftime("%Y-%m-%d")
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
    """, (DAILY_CALLS_META_KEY, fresh, today, today))
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
    key = os.environ.get(SERVICE_KEY_ENV, "")
    return text.replace(key, "***") if key else text


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


def _to_int(v):
    try:
        return int(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return 0


def _upsert(cur, it):
    """수집 대상 생활·일반숙박 업태 1행 UPSERT. 저장 시 True."""
    hygiene = normalize_hygiene_type(
        it.get("SNTTN_BZSTAT_NM") or it.get("BZSTAT_SE_NM")
    )
    if not is_target_lodging_hygiene(hygiene):
        return False
    biz_name = (it.get("BPLC_NM") or "").strip()
    if not biz_name:
        return False
    permit_number = (it.get("MNG_NO") or "").strip()
    road_address = (it.get("ROAD_NM_ADDR") or "").strip() or None
    jibun_address = (it.get("LOTNO_ADDR") or "").strip() or None
    if not permit_number:
        base = biz_name + "|" + (road_address or jibun_address or "")
        permit_number = "NOMNG:" + hashlib.sha256(base.encode("utf-8")).hexdigest()[:20]
    room_count = _to_int(it.get("KSRM_CNT")) + _to_int(it.get("WSRM_CNT"))
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
          (it.get("SALS_STTS_NM") or "").strip() or None,
          (it.get("DTL_SALS_STTS_NM") or "").strip() or None,
          room_count, hygiene,
          (it.get("TELNO") or "").strip() or None,
          normalize_road_prefix(road_address),
          normalize_jibun_prefix(jibun_address),
          normalize_name(biz_name),
          (it.get("DAT_UPDT_PNT") or "").strip() or None))
    return bool(cur.rowcount)


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
        calls_today = _daily_calls_today(cur)
        first_item_logged = False
        daily_match_keys = set()

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

            calls_today = _bump_daily_calls(cur, conn)
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
                changed = _upsert(cur, it)
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
            num_rows=args.num_rows, sleep_sec=args.sleep,
            max_calls=args.max_calls, reset=args.reset,
            status_key=args.status_key, run_id=run_id)
    except Exception as e:
        error = _redact(str(e))[:500]
        print(f"[lodgings] 실패: {error}")

    if not error and completed:
        _refresh_master_stats_after_completion()

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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--num-rows", type=int, default=NUM_ROWS_DEFAULT)
    parser.add_argument("--sleep", type=float, default=SLEEP_DEFAULT)
    parser.add_argument("--max-calls", type=int, default=MAX_DAILY_CALLS)
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--reindex-norms", action="store_true")
    parser.add_argument("--status-key", default=None)
    args = parser.parse_args()

    with _lodging_sync_lock() as acquired:
        if acquired:
            _run(args)


if __name__ == "__main__":
    main()
