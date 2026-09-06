#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
zip_code_backfill.py — master_buildings.zip_code 1회성 백필

zip_code가 NULL이고 road_address가 있는 건물을 대상으로
JUSO API(address_utils.road_to_jibun)를 재호출해 zipNo만 채워넣는다.

JUSO API 일일 한도: 행안부 기본 제공 500,000건/일 (공공데이터 일반).
이 배치 전용 캡(--daily-cap)은 기본 5,000건으로 설정해 다른 JUSO 호출과
예산을 공유하지 않는다(PROJECT_PRINCIPLES.md 영역1 원칙).

사용법:
  python zip_code_backfill.py               # 기본 실행 (캡 5,000, 슬립 0.3초)
  python zip_code_backfill.py --daily-cap 1000 --sleep 0.5
  python zip_code_backfill.py --limit 50    # 소량 테스트
"""

import argparse
import json
import os
import re
import sys
import time
import uuid
from datetime import date as _date

import psycopg2
import psycopg2.extras
from stats_cache import mark_master_stats_invalidated

# This file was used by the original one-off command.  A production worker's
# filesystem is ephemeral, so app_meta is the authoritative checkpoint.  Keep
# the file only to import a pre-existing local checkpoint once.
PROGRESS_FILE = "zip_code_backfill_progress.json"
PROGRESS_META_KEY = "zip_code_backfill_status"
LEASE_STALE_MINUTES = 10
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("PROD_DATABASE_URL", "")
_CURRENT_RUN_ID = None


class LeaseAlreadyHeld(Exception):
    pass


class LeaseLost(Exception):
    pass


def get_conn():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)


def _configure_timeouts(conn):
    """Keep DB work well inside the ten-minute lease window."""
    cur = conn.cursor()
    try:
        cur.execute("SET statement_timeout TO 60000")
        cur.execute("SET lock_timeout TO 30000")
        conn.commit()
    finally:
        cur.close()


def _legacy_progress():
    """Return a legacy checkpoint if present; never write it again."""
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE) as f:
                p = json.load(f)
            return p
        except Exception:
            pass
    return {}


def _normalise_progress(value, today):
    """Make old file/meta values safe to use as a DB-backed status document."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            value = {}
    value = value if isinstance(value, dict) else {}
    try:
        last_id = max(0, int(value.get("last_id") or 0))
    except (TypeError, ValueError):
        last_id = 0
    try:
        completed = max(0, int(value.get("completed", value.get("done", 0)) or 0))
    except (TypeError, ValueError):
        completed = 0
    same_day = value.get("date", value.get("last_run_date")) == today
    try:
        calls_today = max(0, int(value.get("calls_today") or 0)) if same_day else 0
    except (TypeError, ValueError):
        calls_today = 0
    return {
        "date": today,
        "calls_today": calls_today,
        "last_id": last_id,
        "done": bool(value.get("done")) if isinstance(value.get("done"), bool) else False,
        "completed": completed,
        "state": str(value.get("state") or "idle"),
        "heartbeat": value.get("heartbeat"),
        "last_error": value.get("last_error"),
        "run_id": value.get("run_id"),
        # A crash may leave this set.  last_id deliberately remains at the
        # previous completed attempt, so a takeover can retry this address,
        # but the already-reserved call remains charged to calls_today.
        "in_flight_id": value.get("in_flight_id"),
    }


def acquire_lease(conn, run_id=None):
    """Atomically acquire the 10-minute worker lease and return its checkpoint."""
    today = _date.today().isoformat()
    run_id = run_id or uuid.uuid4().hex
    legacy = _normalise_progress(_legacy_progress(), today)
    initial = dict(legacy)
    initial.update(
        date=today, state="running", done=False,
        heartbeat=datetime_now(), run_id=run_id,
    )
    cur = conn.cursor()
    try:
        cur.execute(f"""
            INSERT INTO app_meta (key, value, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (key) DO UPDATE
            SET value = (
                (
                    CASE
                      WHEN (app_meta.value::jsonb ->> 'date') = %s
                      THEN app_meta.value::jsonb
                      ELSE app_meta.value::jsonb ||
                           jsonb_build_object('date', %s, 'calls_today', 0)
                    END
                ) || jsonb_build_object(
                    'state', 'running', 'done', false, 'heartbeat', %s,
                    'run_id', %s
                )
            )::text,
            updated_at = NOW()
            WHERE (app_meta.value::jsonb ->> 'state') IS DISTINCT FROM 'running'
               OR app_meta.updated_at < NOW() - INTERVAL '{LEASE_STALE_MINUTES} minutes'
            RETURNING value
        """, (
            PROGRESS_META_KEY, json.dumps(initial), today, today,
            initial["heartbeat"], run_id,
        ))
        row = cur.fetchone()
        if not row:
            conn.rollback()
            raise LeaseAlreadyHeld("fresh zip-code backfill worker is already running")
        conn.commit()
        prog = _normalise_progress(row["value"], today)
        prog.update(state="running", done=False, run_id=run_id)
        return prog
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def datetime_now():
    """UTC ISO time keeps status useful even when app and batch hosts differ."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _save_progress_cursor(cur, prog):
    run_id = prog.get("run_id")
    if not run_id:
        raise LeaseLost("zip-code backfill status has no run_id")
    cur.execute("""
        UPDATE app_meta
        SET value=%s, updated_at=NOW()
        WHERE key=%s
          AND value::jsonb ->> 'run_id' = %s
    """, (json.dumps(prog), PROGRESS_META_KEY, run_id))
    if cur.rowcount != 1:
        raise LeaseLost("zip-code backfill lease was replaced by another worker")


def save_progress(conn, prog):
    """Persist every attempted ID so an API failure cannot pin the worker."""
    prog["heartbeat"] = datetime_now()
    cur = conn.cursor()
    try:
        _save_progress_cursor(cur, prog)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def _reserve_attempt(conn, prog, bid, daily_cap):
    """Durably charge one provider call before dispatching it."""
    if prog["calls_today"] >= daily_cap:
        return False
    prog["calls_today"] += 1
    prog["in_flight_id"] = bid
    # Fenced commit: provider dispatch is forbidden unless this worker still
    # owns the lease and the quota reservation reached durable app_meta.
    save_progress(conn, prog)
    return True


def _attempt_address(conn, cur, prog, row, road_to_jibun):
    """Complete an already-reserved provider attempt."""
    bid = row["id"]
    road = row["road_address"]
    clean_road = re.sub(r"\([^)]*\)\s*$", "", road.split(",")[0]).strip()
    try:
        juso = road_to_jibun(clean_road)
        zip_val = (juso.get("zipNo") or "").strip() if juso else ""
        if not zip_val:
            prog["last_id"] = bid
            prog["in_flight_id"] = None
            return "empty", None, False
        cur.execute(
            "UPDATE master_buildings SET zip_code=%s WHERE id=%s AND zip_code IS NULL",
            (zip_val, bid),
        )
        changed = cur.rowcount > 0
        conn.commit()
        prog["last_id"] = bid
        prog["in_flight_id"] = None
        prog["completed"] += 1
        return "ok", zip_val, changed
    except Exception as error:
        # UPDATE failures leave psycopg2's transaction aborted. Roll back
        # before the caller stores the consumed call and advanced checkpoint.
        conn.rollback()
        prog["last_id"] = bid
        prog["in_flight_id"] = None
        prog["last_error"] = f"id={bid} {type(error).__name__}: {str(error)[:500]}"
        return "error", error, False


def main_impl():
    global _CURRENT_RUN_ID
    _CURRENT_RUN_ID = None
    parser = argparse.ArgumentParser(description="zip_code 백필 배치")
    parser.add_argument("--daily-cap", type=int, default=5000, help="JUSO API 일일 최대 호출수 (기본 5,000)")
    parser.add_argument("--sleep", type=float, default=0.3, help="건물 간 대기(초, 기본 0.3)")
    parser.add_argument("--limit", type=int, default=0, help="처리 건수 제한 (0=무제한, 테스트용)")
    parser.add_argument("--prod", action="store_true", help="Prod DB(PROD_DATABASE_URL) 대상")
    parser.add_argument("--reset-progress", action="store_true", help="DB 진행 상태를 초기화 후 처음부터")
    args = parser.parse_args()

    if args.prod and not os.environ.get("PROD_DATABASE_URL"):
        print("[오류] --prod 옵션이지만 PROD_DATABASE_URL 환경변수가 없습니다.")
        sys.exit(1)

    # --prod면 PROD_DATABASE_URL, 아니면 DATABASE_URL
    global DATABASE_URL
    if args.prod:
        DATABASE_URL = os.environ["PROD_DATABASE_URL"]

    # 로컬 임포트 (address_utils가 같은 디렉터리에 있어야 함)
    from address_utils import road_to_jibun

    conn = get_conn()
    _configure_timeouts(conn)
    cur = conn.cursor()
    if args.reset_progress:
        cur.execute(f"""
            DELETE FROM app_meta
            WHERE key=%s
              AND (
                  (value::jsonb ->> 'state') IS DISTINCT FROM 'running'
                  OR updated_at < NOW() - INTERVAL '{LEASE_STALE_MINUTES} minutes'
              )
        """, (PROGRESS_META_KEY,))
        conn.commit()
        if cur.rowcount:
            print("[초기화] DB 진행 상태 삭제 — 처음부터 재시작합니다.")
    cur.close()
    prog = acquire_lease(conn)
    _CURRENT_RUN_ID = prog["run_id"]
    print(f"[시작] 오늘 호출 수: {prog['calls_today']}, 마지막 처리 id: {prog['last_id']}")
    cur = conn.cursor()

    # 대상: zip_code IS NULL AND road_address IS NOT NULL, id > last_id 순으로
    cur.execute("""
        SELECT COUNT(*) AS c FROM master_buildings
        WHERE zip_code IS NULL AND road_address IS NOT NULL
          AND id > %s
    """, (prog["last_id"],))
    total = cur.fetchone()["c"]
    print(f"[대상] zip_code 미채움 건물: {total}건 (id > {prog['last_id']})")

    # 이미 채워진 건수 (전체 현황)
    cur.execute("SELECT COUNT(*) AS c FROM master_buildings WHERE zip_code IS NOT NULL")
    already = cur.fetchone()["c"]
    print(f"[현황] 이미 zip_code 채워진 건물: {already}건")

    cur.execute("""
        SELECT id, building_name, road_address FROM master_buildings
        WHERE zip_code IS NULL AND road_address IS NOT NULL
          AND id > %s
        ORDER BY id ASC
    """, (prog["last_id"],))
    rows = cur.fetchall()

    n_ok = n_empty = n_err = 0
    for i, row in enumerate(rows, 1):
        if args.limit and n_ok + n_empty + n_err >= args.limit:
            print(f"[중단] --limit {args.limit} 도달")
            break
        if prog["calls_today"] >= args.daily_cap:
            print(f"[중단] 일일캡({args.daily_cap}) 도달 — 내일 이어서 실행하세요.")
            break

        bid = row["id"]
        name = row["building_name"] or "-"
        if not _reserve_attempt(conn, prog, bid, args.daily_cap):
            print(f"[중단] 일일캡({args.daily_cap}) 도달 — 내일 이어서 실행하세요.")
            break
        outcome, detail, changed = _attempt_address(
            conn, cur, prog, row, road_to_jibun
        )
        if outcome == "ok":
            if changed:
                try:
                    mark_master_stats_invalidated("zip_code_backfill")
                except Exception as e:
                    print(f"[zip_code_backfill] 통계 원본 캐시 표식 갱신 실패: {e}")
            n_ok += 1
            print(f"  [{i}/{len(rows)}] OK   id={bid} {name[:30]} → {detail}", flush=True)
        elif outcome == "empty":
            n_empty += 1
            print(f"  [{i}/{len(rows)}] EMPTY id={bid} {name[:30]} — JUSO 응답 없음 또는 zipNo 빈값", flush=True)
        else:
            n_err += 1
            print(f"  [{i}/{len(rows)}] ERR  id={bid} {name[:30]} — {type(detail).__name__}: {detail}", flush=True)

        save_progress(conn, prog)
        if args.sleep > 0:
            time.sleep(args.sleep)

    cur.close()
    conn.close()

    print(f"\n[완료] 성공: {n_ok}건 / 응답없음: {n_empty}건 / 오류: {n_err}건")
    print(f"[현황] 총 JUSO 호출: {prog['calls_today']}건 (일일캡 {args.daily_cap})")

    # 최종 채움 현황
    conn2 = get_conn()
    _configure_timeouts(conn2)
    cur2 = conn2.cursor()
    cur2.execute("SELECT COUNT(*) AS c FROM master_buildings WHERE zip_code IS NOT NULL")
    filled = cur2.fetchone()["c"]
    cur2.execute("SELECT COUNT(*) AS c FROM master_buildings WHERE zip_code IS NULL AND road_address IS NOT NULL")
    remaining = cur2.fetchone()["c"]
    cur2.close(); conn2.close()
    print(f"[DB 현황] zip_code 채움: {filled}건 / 미채움(road_address 있음): {remaining}건")
    # Only mark a child complete after its final DB work/reporting succeeds.
    conn3 = get_conn()
    _configure_timeouts(conn3)
    prog.update(state="done", done=True, heartbeat=datetime_now())
    save_progress(conn3, prog)
    conn3.close()


def _mark_failed(error, run_id):
    """Best-effort terminal status for supervisor/admin relaunch decisions."""
    conn = None
    try:
        conn = get_conn()
        _configure_timeouts(conn)
        cur = conn.cursor()
        cur.execute("SELECT value FROM app_meta WHERE key=%s FOR UPDATE", (PROGRESS_META_KEY,))
        row = cur.fetchone()
        prog = _normalise_progress(row["value"] if row else {}, _date.today().isoformat())
        if not run_id or prog.get("run_id") != run_id:
            conn.rollback()
            cur.close()
            return
        prog.update(
            state="failed",
            done=False,
            heartbeat=datetime_now(),
            last_error=f"{type(error).__name__}: {str(error)[:500]}",
        )
        _save_progress_cursor(cur, prog)
        conn.commit()
        cur.close()
    except Exception:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
    finally:
        if conn is not None:
            conn.close()


def main():
    try:
        main_impl()
    except LeaseAlreadyHeld as error:
        print(f"[중단] {error}")
        return
    except Exception as error:
        _mark_failed(error, _CURRENT_RUN_ID)
        raise


if __name__ == "__main__":
    main()
