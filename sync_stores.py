# -*- coding: utf-8 -*-
"""
sync_stores.py — 소상공인시장진흥공단 상가업소 API(storeListInPnu)로
전국 master_buildings의 입주 상가업소를 사전 수집해 building_stores 테이블에 저장한다.

• sync_permits.py와 동일한 골격(체크포인트·일일캡·재시도·하트비트)을 재사용한다.
• 건물 목록을 id 순으로 순회하며, 체크포인트는 마지막 처리한 building_id 기준으로 저장한다.
• 한 건물에 대해 기존 데이터를 전부 삭제(DELETE) 후 재삽입(INSERT)한다.

사용:
  python -u sync_stores.py --limit 20      # 건물 20개만 (파일럿)
  python -u sync_stores.py --dry-run       # DB에 안 쓰고 발견 내역만 출력
  python -u sync_stores.py                 # 이어서 실행 (일일캡까지)
  python -u sync_stores.py --reset         # 체크포인트 초기화 후 처음부터
"""

import argparse
import json
import os
import sys
import threading
import time
from datetime import date, datetime

import psycopg2

from db import get_conn
from address_utils import BjdongMap, parse_jibun
from store_info_util import get_stores_by_pnu, build_pnu
from sync_lodgings import _read_status, _write_status, _touch, _still_owner, HEARTBEAT_SEC

PROGRESS_KEY = "stores_progress"
BJDONG_CSV   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "법정동코드_전체자료.zip")

_MAX_RETRY    = 3
_RETRY_WAITS  = [10, 30, 60]  # 초


# ── 법정동 코드 맵 (BjdongMap) ────────────────────────────────────────────────
_bjdong_map = None
_bjdong_lock = threading.Lock()

def _get_bjdong_map():
    global _bjdong_map
    if _bjdong_map is None:
        with _bjdong_lock:
            if _bjdong_map is None:
                _bjdong_map = BjdongMap(BJDONG_CSV)
    return _bjdong_map


# ── PNU 생성 헬퍼 ────────────────────────────────────────────────────────────
def _make_pnu(sgg_cd, umd_nm, jibun):
    """건물 행의 sgg_cd·umd_nm·jibun으로 PNU(19자리)를 생성한다. 실패 시 None."""
    if not (sgg_cd and umd_nm and jibun):
        return None
    try:
        bjd = _get_bjdong_map().find_bjdong_cd(sgg_cd, umd_nm)
        if not bjd:
            return None
        plat_gb, bun, ji = parse_jibun(jibun)
        return build_pnu(sgg_cd, bjd, plat_gb, bun, ji)
    except Exception:
        return None


# ── 체크포인트 로드/저장 ─────────────────────────────────────────────────────
def _load_progress(conn):
    cur = conn.cursor()
    try:
        cur.execute("SELECT value FROM app_meta WHERE key = %s", (PROGRESS_KEY,))
        row = cur.fetchone()
        if row and row["value"]:
            return json.loads(row["value"])
    except Exception:
        pass
    finally:
        cur.close()
    return {}


def _save_progress(conn, prog):
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO app_meta (key, value, updated_at) VALUES (%s, %s, NOW())
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
        """, (PROGRESS_KEY, json.dumps(prog, ensure_ascii=False)))
        conn.commit()
    finally:
        cur.close()


# ── 메인 실행 ────────────────────────────────────────────────────────────────
def run(args, status_key=None, run_id=None):
    daily_cap    = args.daily_cap
    sleep_sec    = args.sleep
    dry_run      = args.dry_run
    limit        = getattr(args, "limit", None)
    verbose      = getattr(args, "verbose", False)

    today = date.today().isoformat()

    conn = get_conn()
    prog = _load_progress(conn)

    # 초기화 옵션
    if getattr(args, "reset", False):
        prog = {}
        _save_progress(conn, prog)
        print("[reset] 체크포인트 초기화 완료")

    last_id     = prog.get("last_id", 0)
    calls_date  = prog.get("calls_date", today)
    calls_today = prog.get("calls_today", 0) if calls_date == today else 0

    # 오늘 일일캡 소진 확인
    if calls_today >= daily_cap:
        msg = f"[skip] 오늘 API 호출량({calls_today})이 일일캡({daily_cap})에 도달. 내일 이어서 실행합니다."
        print(msg)
        if status_key and run_id:
            _write_status(status_key, {
                "state": "done", "stop_reason": "daily_cap",
                "calls_today": calls_today, "daily_cap": daily_cap,
                "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }, run_id)
        conn.close()
        return

    # 건물 목록 조회 (마지막 처리 id 이후부터)
    cur = conn.cursor()
    cur.execute("""
        SELECT id, sgg_cd, umd_nm, jibun
        FROM master_buildings
        WHERE id > %s
          AND sgg_cd IS NOT NULL AND umd_nm IS NOT NULL AND jibun IS NOT NULL AND jibun != ''
        ORDER BY id
    """, (last_id,))
    buildings = cur.fetchall()
    cur.close()
    conn.close()

    if not buildings:
        msg = "모든 건물 처리 완료."
        print(msg)
        if status_key and run_id:
            _write_status(status_key, {
                "state": "done", "stop_reason": "all_done",
                "calls_today": calls_today,
                "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }, run_id)
        return

    total_buildings = len(buildings)
    processed = 0
    saved     = 0
    stop_reason = None

    # 하트비트 스레드 (status_key 있을 때만)
    # _touch()는 내부에서 get_conn()/commit()/close()를 직접 처리하므로
    # 호출자가 커서를 따로 열어줄 필요 없음 (sync_lodgings.py 패턴과 동일)
    stop_beat = threading.Event()
    if status_key and run_id:
        def _beat():
            while not stop_beat.wait(HEARTBEAT_SEC):
                try:
                    _touch(status_key, run_id)
                except Exception:
                    pass
        threading.Thread(target=_beat, daemon=True).start()

    # DB 재접속 주기
    RECONNECT_EVERY = 200
    db_conn = None

    def _get_db():
        nonlocal db_conn
        if db_conn is None:
            db_conn = get_conn()
        return db_conn

    def _close_db():
        nonlocal db_conn
        if db_conn:
            try:
                db_conn.close()
            except Exception:
                pass
            db_conn = None

    try:
        for i, bldg in enumerate(buildings):
            if limit and processed >= limit:
                stop_reason = "limit"
                break

            # 일일캡 재확인
            if calls_today >= daily_cap:
                stop_reason = "daily_cap"
                break

            bld_id = bldg["id"]
            pnu    = _make_pnu(bldg["sgg_cd"], bldg["umd_nm"], bldg["jibun"])
            if not pnu:
                processed += 1
                last_id = bld_id
                continue

            # API 호출 (재시도 포함)
            stores   = None
            api_ok   = False
            last_err = None
            for attempt in range(_MAX_RETRY):
                try:
                    stores = get_stores_by_pnu(pnu)
                    api_ok = True
                    break
                except Exception as e:
                    last_err = e
                    wait = _RETRY_WAITS[min(attempt, len(_RETRY_WAITS) - 1)]
                    print(f"[retry {attempt+1}/{_MAX_RETRY}] bld_id={bld_id} err={e} → {wait}초 대기")
                    time.sleep(wait)

            calls_today += 1

            if not api_ok:
                print(f"[fail] bld_id={bld_id} pnu={pnu} → {last_err}")
                processed += 1
                last_id = bld_id
                # 체크포인트는 계속 저장
                prog.update({"last_id": last_id, "calls_date": today, "calls_today": calls_today,
                             "processed": processed, "saved": saved})
                if not dry_run:
                    try:
                        _save_progress(_get_db(), prog)
                    except Exception:
                        _close_db()
                time.sleep(sleep_sec)
                continue

            # DB 저장
            if not dry_run and stores is not None:
                try:
                    c = _get_db()
                    cur2 = c.cursor()
                    try:
                        cur2.execute("DELETE FROM building_stores WHERE master_building_id = %s", (bld_id,))
                        for s in stores:
                            cur2.execute(
                                """INSERT INTO building_stores (master_building_id, store_name, category, floor, updated_at)
                                   VALUES (%s, %s, %s, %s, NOW())""",
                                (bld_id, s.get("name", ""), s.get("category", ""), s.get("floor", "")),
                            )
                        c.commit()
                        if stores:
                            saved += 1
                    finally:
                        cur2.close()
                except Exception as e:
                    print(f"[db_err] bld_id={bld_id} → {e}")
                    _close_db()

            if verbose or (stores and dry_run):
                print(f"[ok] bld_id={bld_id} pnu={pnu} stores={len(stores or [])}")

            processed += 1
            last_id = bld_id

            # 체크포인트 저장 (10건마다)
            if processed % 10 == 0:
                prog.update({"last_id": last_id, "calls_date": today, "calls_today": calls_today,
                             "processed": processed, "saved": saved})
                if not dry_run:
                    try:
                        _save_progress(_get_db(), prog)
                    except Exception:
                        _close_db()

            # DB 재접속 주기
            if processed % RECONNECT_EVERY == 0:
                _close_db()

            time.sleep(sleep_sec)

    finally:
        stop_beat.set()
        _close_db()

    # 최종 체크포인트 저장
    if not dry_run:
        try:
            final_conn = get_conn()
            prog.update({"last_id": last_id, "calls_date": today, "calls_today": calls_today,
                         "processed": processed, "saved": saved})
            _save_progress(final_conn, prog)
            final_conn.close()
        except Exception as e:
            print(f"[checkpoint_err] {e}")

    if not stop_reason:
        remaining = total_buildings - processed
        stop_reason = "all_done" if remaining == 0 else "completed_batch"

    summary = (f"처리={processed} / 저장건물={saved} / 오늘API={calls_today}/{daily_cap} / 종료={stop_reason}")
    print("[done]", summary)

    if status_key and run_id:
        _write_status(status_key, {
            "state": "done",
            "stop_reason": stop_reason,
            "processed": processed,
            "saved": saved,
            "calls_today": calls_today,
            "daily_cap": daily_cap,
            "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }, run_id)


# ── CLI 진입점 ────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="상가정보 사전수집 (building_stores 테이블)")
    parser.add_argument("--daily-cap",   type=int,   default=500,   help="오늘 최대 API 호출 수 (기본 500)")
    parser.add_argument("--sleep",       type=float, default=1.0,   help="건물당 API 호출 후 대기(초, 기본 1.0)")
    parser.add_argument("--limit",       type=int,   default=None,  help="이번 실행에서 처리할 최대 건물 수")
    parser.add_argument("--reset",       action="store_true",       help="체크포인트 초기화 후 처음부터")
    parser.add_argument("--dry-run",     action="store_true",       help="DB에 쓰지 않고 발견 내역만 출력")
    parser.add_argument("--verbose",     action="store_true",       help="모든 건물 처리 결과 출력")
    parser.add_argument("--status-key",  default=None,              help="관리자 상태 키 (app_meta)")
    parser.add_argument("--run-id",      default=None,              help="중복 실행 방지용 run_id")
    args = parser.parse_args()

    run(args, status_key=args.status_key, run_id=args.run_id)


if __name__ == "__main__":
    main()
