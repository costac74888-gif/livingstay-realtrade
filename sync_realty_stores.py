# -*- coding: utf-8 -*-
"""
sync_realty_stores.py — 소상공인 상가정보 API(storeListInPnu)로
master_buildings 각 건물의 입주 부동산 중개업소를 조회하여
realty_store_name 컬럼에 저장하는 배치 스크립트.

건당 평균 3초 소요 → 관리자 버튼으로 백그라운드 실행 필수.
일일 캡(--daily-cap, 기본 300건)에 도달하면 체크포인트 저장 후 중단,
다음 실행 때 realty_checked_at 오래된 순으로 이어서 처리.

사용:
  python -u sync_realty_stores.py --probe            # 3건만 조회해서 원본 응답 출력, DB 안 씀
  python -u sync_realty_stores.py --dry-run --limit 20  # UPDATE 없이 결과만 출력
  python -u sync_realty_stores.py --limit 50         # 50건만 UPDATE (파일럿)
  python -u sync_realty_stores.py                    # 이어서 실행 (일일캡까지)
"""

import argparse
import json
import os
import sys
import threading
import time
from datetime import date, datetime

from db import get_conn
from quota_policy import korea_today, regular_cap
from address_utils import BjdongMap, parse_jibun
from store_info_util import build_pnu, get_stores_by_pnu, STORE_INFO_SERVICE_KEY
from sync_lodgings import _read_status, _write_status, _touch, _still_owner, HEARTBEAT_SEC
from stats_cache import mark_master_stats_invalidated

PROGRESS_KEY = "realty_stores_progress"
BJDONG_CSV   = os.environ.get("BJDONG_CODE_CSV", "법정동코드_전체자료.zip")

_bjdmap = None
_bjdmap_lock = threading.Lock()


def _get_bjdmap():
    global _bjdmap
    if _bjdmap is None:
        with _bjdmap_lock:
            if _bjdmap is None:
                _bjdmap = BjdongMap(BJDONG_CSV)
    return _bjdmap


# ── 체크포인트 ──────────────────────────────────────────────
def _get_progress(cur):
    cur.execute("SELECT value FROM app_meta WHERE key=%s", (PROGRESS_KEY,))
    row = cur.fetchone()
    if row and row["value"]:
        try:
            return json.loads(row["value"])
        except ValueError:
            pass
    return {"calls_date": "", "calls_today": 0, "updated_total": 0}


def _save_progress(conn, cur, prog):
    cur.execute("""
        INSERT INTO app_meta (key, value) VALUES (%s, %s)
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
    """, (PROGRESS_KEY, json.dumps(prog, ensure_ascii=False)))
    conn.commit()


# ── 건물 1건 처리 ────────────────────────────────────────────
def _process_building(row, dry_run=False):
    """(realty_store_name, skipped) 반환. skipped=True면 PNU 산출 불가."""
    sgg_cd = row.get("sgg_cd") or ""
    umd_nm = row.get("umd_nm") or ""
    jibun  = row.get("jibun")  or ""
    if not (sgg_cd and umd_nm and jibun):
        return None, True

    bjd = _get_bjdmap().find_bjdong_cd(sgg_cd, umd_nm)
    if not bjd:
        return None, True

    plat_gb, bun, ji = parse_jibun(jibun)
    pnu = build_pnu(sgg_cd, bjd, plat_gb, bun, ji)
    if not pnu:
        return None, True

    stores = get_stores_by_pnu(pnu)
    names  = [s["name"] for s in stores if s.get("category") == "부동산"]
    result = ", ".join(names) if names else ""
    return result, False


# ── probe ─────────────────────────────────────────────────────
def probe():
    """PNU 조합 + raw 응답 확인용. DB 안 씀."""
    if not STORE_INFO_SERVICE_KEY:
        print("⚠ STORE_INFO_SERVICE_KEY 환경변수가 없습니다.")
        return
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("""
        SELECT id, building_name, sgg_cd, umd_nm, jibun
        FROM master_buildings
        WHERE sgg_cd IS NOT NULL AND umd_nm IS NOT NULL AND jibun IS NOT NULL
        ORDER BY id
        LIMIT 5
    """)
    rows = cur.fetchall()
    cur.close(); conn.close()

    import requests
    from store_info_util import STORE_IN_PNU_URL
    from xml.etree import ElementTree as ET

    for row in rows:
        bjd = _get_bjdmap().find_bjdong_cd(row["sgg_cd"], row["umd_nm"])
        if not bjd:
            print(f"[{row['building_name']}] bjdong_cd 없음 — skip")
            continue
        plat_gb, bun, ji = parse_jibun(row["jibun"])
        pnu = build_pnu(row["sgg_cd"], bjd, plat_gb, bun, ji)
        print(f"\n[probe] {row['building_name']} (id={row['id']}) → PNU={pnu}")
        if not pnu:
            continue
        params = {"serviceKey": STORE_INFO_SERVICE_KEY, "key": pnu, "numOfRows": 5, "pageNo": 1}
        try:
            resp = requests.get(STORE_IN_PNU_URL, params=params, timeout=15)
            print(f"  HTTP {resp.status_code}")
            root = ET.fromstring(resp.content)
            rc   = root.findtext(".//resultCode") or ""
            msg  = root.findtext(".//resultMsg")  or ""
            print(f"  resultCode={rc!r}  resultMsg={msg!r}")
            items = root.findall(".//item")
            print(f"  {len(items)}개 업소 (최대 5개 노출)")
            for it in items[:5]:
                d = {c.tag: (c.text or "").strip() for c in it}
                print(f"    {d.get('bizesNm','?'):25s} | 대분류={d.get('indsLclsNm','?')}"
                      f" | 중분류={d.get('indsMclsNm','?')} | 층={d.get('flrNo','?')}")
        except Exception as e:
            print(f"  오류: {e}")
        break  # 첫 번째 성공 건 확인 후 종료


# ── 메인 실행 ─────────────────────────────────────────────────
def run(args, status_key=None, run_id=None):
    if not STORE_INFO_SERVICE_KEY:
        print("⚠ STORE_INFO_SERVICE_KEY 환경변수가 없습니다. 종료.")
        return False, 0, 0, 0

    conn = get_conn()
    cur  = conn.cursor()
    prog = _get_progress(cur)

    today = korea_today()
    if prog.get("calls_date") != today:
        prog["calls_date"]  = today
        prog["calls_today"] = 0

    if prog["calls_today"] >= args.daily_cap:
        print(f"오늘 호출 {prog['calls_today']}건 — 일일캡({args.daily_cap}) 도달. 내일 재실행하세요.")
        cur.close(); conn.close()
        return False, 0, 0, prog["calls_today"]

    # realty_checked_at IS NULL 우선, 그 다음 오래된 순
    cur.execute("""
        SELECT id, building_name, sgg_cd, umd_nm, jibun
        FROM master_buildings
        WHERE sgg_cd IS NOT NULL AND umd_nm IS NOT NULL AND jibun IS NOT NULL
        ORDER BY realty_checked_at ASC NULLS FIRST, id ASC
    """)
    buildings = cur.fetchall()
    cur.close(); conn.close()

    total_bldgs = len(buildings)
    print(f"[시작] 처리 대상 {total_bldgs}건, 오늘 호출 {prog['calls_today']}/{args.daily_cap}")

    processed = 0
    updated   = 0
    skipped   = 0

    # heartbeat 스레드 (관리자 버튼 상태 연동)
    stop_beat = threading.Event()
    if status_key and run_id:
        def _beat():
            while not stop_beat.wait(HEARTBEAT_SEC):
                try:
                    _touch(status_key, run_id)
                except Exception:
                    pass
        threading.Thread(target=_beat, daemon=True).start()

    try:
        for row in buildings:
            if args.limit and processed >= args.limit:
                print(f"--limit {args.limit} 도달 — 중단.")
                break
            if prog["calls_today"] >= args.daily_cap:
                print(f"일일캡({args.daily_cap}) 도달 — 체크포인트 저장 후 중단.")
                break
            if status_key and run_id:
                try:
                    conn2 = get_conn(); cur2 = conn2.cursor()
                    owned = _still_owner(cur2, status_key, run_id)
                    cur2.close(); conn2.close()
                    if not owned:
                        print("[realty] 다른 실행이 소유권을 가져갔습니다 — 중단.")
                        return False, processed, updated, prog["calls_today"]
                except Exception:
                    pass

            name, was_skipped = _process_building(row)
            processed += 1
            if processed == 1 or processed % 25 == 0 or processed == total_bldgs:
                print(
                    f"[수집진행] 대상 {processed}/{total_bldgs}",
                    flush=True,
                )
            prog["calls_today"] += 1

            bname = row.get("building_name") or f"id={row['id']}"
            if was_skipped:
                skipped += 1
                print(f"  [{processed:4d}] {bname[:28]:28s} → PNU 산출 불가, skip")
            else:
                display = name if name else "(부동산 없음)"
                print(f"  [{processed:4d}] {bname[:28]:28s} → {display}")
                if not args.dry_run:
                    try:
                        upd_conn = get_conn(); upd_cur = upd_conn.cursor()
                        upd_cur.execute("""
                            UPDATE master_buildings
                            SET realty_store_name=%s, realty_checked_at=NOW()
                            WHERE id=%s
                        """, (name, row["id"]))
                        changed = upd_cur.rowcount > 0
                        upd_conn.commit()
                        upd_cur.close(); upd_conn.close()
                        if changed:
                            try:
                                mark_master_stats_invalidated("sync_realty_stores")
                            except Exception as e:
                                print(f"    ↳ 통계 원본 캐시 표식 갱신 실패: {e}")
                        updated += 1
                        prog["updated_total"] = prog.get("updated_total", 0) + 1
                    except Exception as e:
                        print(f"    ↳ UPDATE 실패: {e}")

            # 체크포인트 10건마다
            if processed % 10 == 0 and not args.dry_run:
                try:
                    cp_conn = get_conn(); cp_cur = cp_conn.cursor()
                    _save_progress(cp_conn, cp_cur, prog)
                    cp_cur.close(); cp_conn.close()
                except Exception:
                    pass

            if not was_skipped:
                time.sleep(args.sleep)

        # 루프 종료 후 최종 체크포인트
        if not args.dry_run:
            try:
                fp_conn = get_conn(); fp_cur = fp_conn.cursor()
                _save_progress(fp_conn, fp_cur, prog)
                fp_cur.close(); fp_conn.close()
            except Exception:
                pass

    finally:
        stop_beat.set()

    completed = processed >= total_bldgs and not args.limit
    print(f"\n[완료] 처리 {processed}건 (UPDATE {updated}건, skip {skipped}건)"
          f"{' — 전체 완료' if completed else ''}")
    return completed, processed, updated, prog["calls_today"]


# ── 진입점 ────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="단지부동산(상가정보) 배치 동기화")
    ap.add_argument("--probe",      action="store_true", help="PNU 확인 + raw 응답 출력 후 종료 (DB 안 씀)")
    ap.add_argument("--dry-run",    action="store_true", help="UPDATE 없이 결과만 출력")
    ap.add_argument("--limit",      type=int, default=0, help="처리 건수 상한 (0=무제한)")
    ap.add_argument("--daily-cap",  type=int, default=regular_cap("realty_store"), dest="daily_cap", help="일일 처리 건수 상한 (중앙 정책의 정기 몫)")
    ap.add_argument("--sleep",      type=float, default=1.5, help="API 호출 간 대기 초 (기본 1.5)")
    ap.add_argument("--reset",      action="store_true", help="체크포인트 초기화 후 처음부터")
    ap.add_argument("--status-key", default=None, dest="status_key", help="app_meta heartbeat 키 (관리자 버튼용)")
    args = ap.parse_args()

    if args.probe:
        probe()
        return

    if args.reset:
        conn = get_conn(); cur = conn.cursor()
        cur.execute("DELETE FROM app_meta WHERE key=%s", (PROGRESS_KEY,))
        conn.commit(); cur.close(); conn.close()
        print("체크포인트 초기화 완료.")

    run_id = None
    if args.status_key:
        status = _read_status(args.status_key) or {}
        run_id = status.get("run_id")

    if args.status_key and run_id:
        status = _read_status(args.status_key) or {}
        status.update({
            "state": "running",
            "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "finished_at": None, "processed": None, "updated": None,
            "calls_today": None, "error": None,
        })
        _write_status(args.status_key, status, run_id)

    try:
        completed, processed, updated, calls_today = run(args, args.status_key, run_id)
        if args.status_key and run_id:
            status = _read_status(args.status_key) or {}
            status.update({
                "state": "done",
                "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "processed": processed, "updated": updated,
                "calls_today": calls_today, "completed": completed, "error": None,
            })
            _write_status(args.status_key, status, run_id)
    except Exception as e:
        import traceback; traceback.print_exc()
        if args.status_key and run_id:
            status = _read_status(args.status_key) or {}
            status.update({
                "state": "failed",
                "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "error": str(e)[:300],
            })
            _write_status(args.status_key, status, run_id)
        sys.exit(1)


if __name__ == "__main__":
    main()
