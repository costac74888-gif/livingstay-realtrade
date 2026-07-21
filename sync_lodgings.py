"""
sync_lodgings.py — 행안부 '문화_숙박업 조회서비스' 수집 배치.

특징 (sync_brokers.py 패턴 재사용)
- 일일 트래픽 10,000건 → 소프트 캡 8,000에서 스스로 멈추고 체크포인트 저장.
- numOfRows=1000, 위생업태 '숙박업(생활)'만 저장(클라이언트 필터 — API에 업태 필터 없음).
- permit_number(관리번호 MNG_NO) 기준 UPSERT.
- --status-key 시 run_id 펜싱 + 30초 하트비트 (관리자 버튼용).

사용 예
  python sync_lodgings.py
  python sync_lodgings.py --status-key lodging_sync_status
  python sync_lodgings.py --reset
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

from addr_norm import normalize_name, normalize_road_prefix
from db import get_conn

API_URL = "https://apis.data.go.kr/1741000/lodgings/info"
SERVICE_KEY_ENV = "DATA_GO_KR_BROKER_API_KEY"  # 계정 공용 일반인증키 재사용

MAX_DAILY_CALLS = 8000  # 일일 쿼터 10,000 — 여유분을 남기고 멈춘다.
DAILY_CALLS_META_KEY = "lodging_daily_calls"
PROGRESS_META_KEY = "lodging_sync_progress"
LAST_SYNC_META_KEY = "lodging_last_sync"

TARGET_HYGIENE = "숙박업(생활)"

NUM_ROWS_DEFAULT = 1000
SLEEP_DEFAULT = 0.3
HEARTBEAT_SEC = 30


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


def _to_int(v):
    try:
        return int(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return 0


def _upsert(cur, it):
    """숙박업(생활)만 1행 UPSERT. 저장 시 True."""
    hygiene = (it.get("SNTTN_BZSTAT_NM") or it.get("BZSTAT_SE_NM") or "").strip()
    if hygiene != TARGET_HYGIENE:
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
             road_norm, biz_name_norm, source_updated_at, updated_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
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
            biz_name_norm = EXCLUDED.biz_name_norm,
            source_updated_at = EXCLUDED.source_updated_at,
            updated_at = NOW()
    """, (biz_name, permit_number, road_address, jibun_address,
          (it.get("LCPMT_YMD") or "").strip() or None,
          (it.get("SALS_STTS_NM") or "").strip() or None,
          (it.get("DTL_SALS_STTS_NM") or "").strip() or None,
          room_count, hygiene,
          (it.get("TELNO") or "").strip() or None,
          normalize_road_prefix(road_address),
          normalize_name(biz_name),
          (it.get("DAT_UPDT_PNT") or "").strip() or None))
    return True


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

        while True:
            # run_id 펜싱: 상태행 소유권을 잃었으면(다른 실행이 시작됨) 즉시 중단 —
            # 구 프로세스가 체크포인트/카운터/레지스트리를 계속 갱신하는 split-brain 방지.
            if status_key and run_id and not _still_owner(cur, status_key, run_id):
                print("[lodgings] 다른 실행이 상태를 가져갔습니다 — 이 실행을 중단합니다.")
                raise RuntimeError("동기화 소유권 상실(다른 실행이 시작됨)")
            if calls_today >= max_calls:
                print(f"[lodgings] 일일 소프트 캡({max_calls}건) 도달 — 내일 이어서 진행 "
                      f"(다음 페이지 {page} 저장됨)")
                return False, processed, calls_today

            calls_today = _bump_daily_calls(cur, conn)
            print(f"[lodgings] 페이지 {page} 호출 (오늘 {calls_today}/{max_calls})")
            items, total = _fetch_page(key, page, num_rows)
            if total:
                total_count = total

            if not items:
                _clear_progress(cur, conn)
                cur.execute("SELECT COUNT(*) AS c FROM lodging_registry")
                total_rows = cur.fetchone()["c"]
                _mark_last_sync(cur, conn, total_rows)
                print(f"[lodgings] 전체 수집 완료 — 생활숙박업 누적 {total_rows}건")
                return True, processed, calls_today

            if not first_item_logged:
                print(f"[lodgings] 응답 필드: {sorted(items[0].keys())}")
                first_item_logged = True

            saved = 0
            for it in items:
                if _upsert(cur, it):
                    saved += 1
            conn.commit()
            processed += saved
            page += 1
            _save_progress(cur, conn, page, total_count)
            print(f"[lodgings] 생활숙박업 {saved}건 저장/{len(items)}건 검사 "
                  f"(누적 이번 실행 {processed}건, 전체 {total_count or '?'}건 중 페이지 {page - 1} 완료)")

            # 완료 판정은 '실제' 페이지 크기 기준 — 요청 numOfRows보다 적게 내려오는 경우가 있음(실측 100행).
            if page_size is None or len(items) > page_size:
                page_size = len(items)
            if total_count and page_size and (page - 1) * page_size >= total_count:
                _clear_progress(cur, conn)
                cur.execute("SELECT COUNT(*) AS c FROM lodging_registry")
                total_rows = cur.fetchone()["c"]
                _mark_last_sync(cur, conn, total_rows)
                print(f"[lodgings] 전체 수집 완료 — 생활숙박업 누적 {total_rows}건")
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
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--status-key", default=None)
    args = parser.parse_args()

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


if __name__ == "__main__":
    main()
