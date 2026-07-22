"""
sync_brokers.py — 공공데이터포털 '전국공인중개사사무소표준데이터' 수집 배치.

특징 (sync_batch.py의 백필 패턴 재사용)
- 일일 트래픽 한도가 1,000건으로 매우 작음 → 소프트 캡(기본 900)에서 스스로 멈추고,
  체크포인트(마지막 완료 페이지)를 app_meta에 저장해 다음날 이어서 수집한다.
- 한 번 호출에 numOfRows=1000 으로 최대한 크게 받아 총 호출 수를 최소화한다.
- reg_number(개설등록번호) 기준 UPSERT — 여러 번 돌려도 중복 저장되지 않는다.
- --status-key 를 주면(관리자 버튼 실행) app_meta에 상태(running/done/failed)와
  30초 하트비트를 기록한다. run_id 펜싱으로 새 실행 상태를 덮어쓰지 않는다.

사용 예
  python sync_brokers.py                      # CLI 수동 실행
  python sync_brokers.py --status-key broker_sync_status   # 관리자 버튼용
  python sync_brokers.py --reset              # 체크포인트 초기화 후 처음부터
"""

import argparse
import hashlib
import json
import os
import sys
import threading
import time
from datetime import datetime

import requests

from db import get_conn

API_URL = "https://api.data.go.kr/openapi/tn_pubr_public_med_office_api"
SERVICE_KEY_ENV = "DATA_GO_KR_BROKER_API_KEY"

# 일일 쿼터 1,000건 — 관리자 화면의 다른 기능/재시도 여유분 100건을 남기고 멈춘다.
MAX_DAILY_CALLS = 900
DAILY_CALLS_META_KEY = "broker_daily_calls"
PROGRESS_META_KEY = "broker_sync_progress"   # {"next_page": N, "total_count": M}
LAST_SYNC_META_KEY = "broker_last_sync"      # {"finished_at": ..., "total": ...}

NUM_ROWS_DEFAULT = 1000
SLEEP_DEFAULT = 0.3
HEARTBEAT_SEC = 30

# 표준데이터 응답 필드 후보 — 데이터셋 버전에 따라 키가 다를 수 있어 후보 목록에서
# 처음 발견되는 키를 사용한다(첫 행에서 실제 키 목록을 로그로 남김).
FIELD_CANDIDATES = {
    "office_name": ["medOfficeNm", "mdtOfcNm", "bsshNm", "officeNm", "cmpnm", "opnSvcNm"],
    "reg_number": ["estblRegNo", "estblRegno", "registerNo", "regNo"],
    "road_address": ["lctnRoadNmAddr", "rdnmadr", "rdnmAdr", "roadAddress"],
    "jibun_address": ["lctnLotnoAddr", "lnmadr", "lnmAdr", "jibunAddress"],
    "phone": ["telno", "phoneNumber", "telNo", "tel"],
    "reg_date": ["estblRegYmd", "estblRegDe", "registDe", "estblDe", "openDe"],
    "owner_name": ["rprsvNm", "rprsntvNm", "representNm", "ownerNm"],
    "lat": ["latitude", "lat"],
    "lng": ["longitude", "lot", "lng"],
    "homepage_url": ["hmpgAddr", "homepageUrl", "hmpgAdres", "homepage"],
    "source_updated_at": ["crtrYmd", "referenceDate", "dataStdDe", "stdrDe"],
}


def _pick(item, field):
    for k in FIELD_CANDIDATES[field]:
        if k in item and item[k] not in (None, ""):
            return str(item[k]).strip()
    return None


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
        return {"next_page": int(data.get("next_page", 1)),
                "total_count": data.get("total_count")}
    except (TypeError, ValueError):
        return {"next_page": 1, "total_count": None}


def _save_progress(cur, conn, next_page, total_count):
    payload = json.dumps({
        "next_page": next_page,
        "total_count": total_count,
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


def _fetch_page(key, page, num_rows):
    """API 1페이지 호출 → (items, total_count). 오류 시 RuntimeError."""
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
    if code not in ("00", "0"):
        raise RuntimeError(f"API 오류 resultCode={code} msg={header.get('resultMsg')}")
    body = (data.get("response") or {}).get("body") or {}
    items = body.get("items") or []
    if isinstance(items, dict):  # XML→JSON 변환형 케이스 방어
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
        print(f"[brokers] 페이지 {page} 오류: {_redact(repr(e))[:160]} — {wait}초 후 1회 재시도")
        time.sleep(wait)
        items, total = _fetch_page(key, page, num_rows)
        return items, total, saw_429


def _upsert(cur, item):
    """1행 UPSERT. reg_number 없으면 지번/도로명주소+상호로 대체키 생성(데이터 유실 방지)."""
    row = {f: _pick(item, f) for f in FIELD_CANDIDATES}
    if not row["office_name"]:
        return False
    if not row["reg_number"]:
        base = (row["office_name"] or "") + "|" + (row["road_address"] or row["jibun_address"] or "")
        # 주의: hash()는 프로세스마다 시드가 달라 재실행 시 값이 바뀜 → sha256으로 결정적 키 생성
        row["reg_number"] = "NOREG:" + hashlib.sha256(base.encode("utf-8")).hexdigest()[:20]
    lat = lng = None
    try:
        lat = float(row["lat"]) if row["lat"] else None
        lng = float(row["lng"]) if row["lng"] else None
    except ValueError:
        pass
    cur.execute("""
        INSERT INTO broker_registry
            (office_name, reg_number, road_address, jibun_address, phone, reg_date,
             owner_name, lat, lng, homepage_url, source_updated_at, updated_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
        ON CONFLICT (reg_number) DO UPDATE SET
            office_name = EXCLUDED.office_name,
            road_address = EXCLUDED.road_address,
            jibun_address = EXCLUDED.jibun_address,
            phone = EXCLUDED.phone,
            reg_date = EXCLUDED.reg_date,
            owner_name = EXCLUDED.owner_name,
            lat = COALESCE(EXCLUDED.lat, broker_registry.lat),
            lng = COALESCE(EXCLUDED.lng, broker_registry.lng),
            homepage_url = EXCLUDED.homepage_url,
            source_updated_at = EXCLUDED.source_updated_at,
            updated_at = NOW()
    """, (row["office_name"], row["reg_number"], row["road_address"], row["jibun_address"],
          row["phone"], row["reg_date"], row["owner_name"], lat, lng,
          row["homepage_url"], row["source_updated_at"]))
    return True


def sync_brokers(num_rows=NUM_ROWS_DEFAULT, sleep_sec=SLEEP_DEFAULT,
                 max_calls=MAX_DAILY_CALLS, reset=False):
    """수집 본체. 반환: (완결 여부, 이번 실행 처리 행수, 오늘 사용 호출수)."""
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
        calls_today = _daily_calls_today(cur)
        first_item_logged = False

        while True:
            if calls_today >= max_calls:
                print(f"[brokers] 일일 소프트 캡({max_calls}건) 도달 — 내일 이어서 진행 "
                      f"(다음 페이지 {page} 저장됨)")
                return False, processed, calls_today

            calls_today = _bump_daily_calls(cur, conn)
            print(f"[brokers] 페이지 {page} 호출 (오늘 {calls_today}/{max_calls})")
            items, total, saw_429 = _fetch_page_retry(key, page, num_rows)
            if saw_429:
                # 속도 제한을 맞았으므로 이후 요청 간격을 2배로(최대 10초) 늘려 재발 방지
                sleep_sec = min(max(sleep_sec, 0.1) * 2, 10.0)
                print(f"[brokers] 429 감지 — 이후 요청 간격을 {sleep_sec:.1f}초로 늘립니다")
            if total:
                total_count = total

            if not items:
                # 전체 수집 완료(마지막 페이지 초과 or NODATA)
                _clear_progress(cur, conn)
                cur.execute("SELECT COUNT(*) AS c FROM broker_registry")
                total_rows = cur.fetchone()["c"]
                _mark_last_sync(cur, conn, total_rows)
                print(f"[brokers] 전체 수집 완료 — 누적 {total_rows}건")
                return True, processed, calls_today

            if not first_item_logged:
                print(f"[brokers] 응답 필드: {sorted(items[0].keys())}")
                first_item_logged = True

            saved = 0
            for it in items:
                if _upsert(cur, it):
                    saved += 1
            conn.commit()
            processed += saved
            page += 1
            _save_progress(cur, conn, page, total_count)
            print(f"[brokers] {saved}건 저장 (누적 이번 실행 {processed}건, "
                  f"전체 {total_count or '?'}건 중 페이지 {page - 1} 완료)")

            if total_count and (page - 1) * num_rows >= total_count:
                _clear_progress(cur, conn)
                cur.execute("SELECT COUNT(*) AS c FROM broker_registry")
                total_rows = cur.fetchone()["c"]
                _mark_last_sync(cur, conn, total_rows)
                print(f"[brokers] 전체 수집 완료 — 누적 {total_rows}건")
                return True, processed, calls_today

            time.sleep(sleep_sec)
    finally:
        cur.close()
        conn.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--num-rows", type=int, default=NUM_ROWS_DEFAULT)
    parser.add_argument("--sleep", type=float, default=SLEEP_DEFAULT)
    parser.add_argument("--max-calls", type=int, default=MAX_DAILY_CALLS)
    parser.add_argument("--reset", action="store_true", help="체크포인트 초기화 후 처음부터")
    parser.add_argument("--status-key", default=None,
                        help="관리자 버튼 실행 시 상태를 기록할 app_meta 키")
    args = parser.parse_args()

    run_id = None
    stop_beat = threading.Event()
    if args.status_key:
        status = _read_status(args.status_key)
        if not status or status.get("state") != "running":
            print("[brokers] running 상태가 아니므로 종료합니다.")
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
        completed, processed, calls_today = sync_brokers(
            num_rows=args.num_rows, sleep_sec=args.sleep,
            max_calls=args.max_calls, reset=args.reset)
    except Exception as e:
        error = _redact(str(e))[:500]
        print(f"[brokers] 실패: {error}")

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
                print(f"[brokers] 상태 저장 실패({attempt + 1}/3): {e}")
                time.sleep(5)
    if error and not args.status_key:
        sys.exit(1)


if __name__ == "__main__":
    main()
