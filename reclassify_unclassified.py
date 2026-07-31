# -*- coding: utf-8 -*-
"""
reclassify_unclassified.py — master_buildings에서 lodging_type이 NULL/빈값인
건물을 건축물대장(표제부+층별개요) API로 재판정해 lodging_type/
lodging_type_detail/lodging_subtype/verified_at을 업데이트하는 배치.

판정 실패(label=None) 건물은 건너뜀(DB 미반영).
일일 캡(기본 200건)에 도달하면 체크포인트 저장 후 중단.
다음 실행 때 이어서 처리(id ASC 순 전수).

사용:
  python -u reclassify_unclassified.py --probe            # 3건 원본 결과 확인, DB 안 씀
  python -u reclassify_unclassified.py --dry-run --limit 20  # 결과만 출력
  python -u reclassify_unclassified.py --limit 50         # 50건 UPDATE
  python -u reclassify_unclassified.py                    # 이어서 실행 (일일캡까지)
"""

import argparse
import json
import os
import sys
import threading
import time
from datetime import date, datetime

from db import get_conn
from address_utils import BjdongMap, parse_jibun
from building_registry import classify_lodging_type
from sync_lodgings import _read_status, _write_status, _touch, _still_owner, HEARTBEAT_SEC

PROGRESS_KEY = "reclassify_unclassified_progress"
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
    return {"calls_date": "", "calls_today": 0, "updated_total": 0, "skipped_total": 0}


def _save_progress(conn, cur, prog):
    cur.execute("""
        INSERT INTO app_meta (key, value) VALUES (%s, %s)
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
    """, (PROGRESS_KEY, json.dumps(prog, ensure_ascii=False)))
    conn.commit()


# ── probe ─────────────────────────────────────────────────────
def probe():
    """미분류 건물 3건 classify_lodging_type() 원본 결과 확인. DB 안 씀."""
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("""
        SELECT id, building_name, sgg_cd, umd_nm, jibun
        FROM master_buildings
        WHERE (lodging_type IS NULL OR lodging_type = '')
          AND sgg_cd IS NOT NULL AND umd_nm IS NOT NULL AND jibun IS NOT NULL
        ORDER BY id
        LIMIT 5
    """)
    rows = cur.fetchall()
    cur.close(); conn.close()

    bjd = _get_bjdmap()
    done = 0
    for row in rows:
        bjd_cd = bjd.find_bjdong_cd(row["sgg_cd"], row["umd_nm"])
        if not bjd_cd:
            print(f"[{row['building_name']}] bjdong_cd 없음 — skip")
            continue
        plat_gb, bun, ji = parse_jibun(row["jibun"])
        print(f"\n[probe] {row['building_name']} (id={row['id']}) "
              f"sgg={row['sgg_cd']} umd={row['umd_nm']} jibun={row['jibun']}")
        try:
            label, detail, subtype, title, reason = classify_lodging_type(
                row["sgg_cd"], bjd_cd, plat_gb, bun, ji
            )
            print(f"  → label={label!r}  detail={detail!r}  subtype={subtype!r}")
            print(f"  → reason={reason!r}")
            if title:
                print(f"  → 건물명={title.get('bld_nm')!r}  호실수={title.get('ho_cnt')}")
        except Exception as e:
            print(f"  오류: {e}")
        done += 1
        if done >= 3:
            break


# ── 메인 실행 ─────────────────────────────────────────────────
def run(args, status_key=None, run_id=None):
    conn = get_conn()
    cur  = conn.cursor()
    prog = _get_progress(cur)

    today = date.today().isoformat()
    if prog.get("calls_date") != today:
        prog["calls_date"]  = today
        prog["calls_today"] = 0

    if prog["calls_today"] >= args.daily_cap:
        print(f"오늘 호출 {prog['calls_today']}건 — 일일캡({args.daily_cap}) 도달. 내일 재실행하세요.")
        cur.close(); conn.close()
        return False, 0, 0, prog["calls_today"]

    cur.execute("""
        SELECT id, building_name, sgg_cd, umd_nm, jibun
        FROM master_buildings
        WHERE (lodging_type IS NULL OR lodging_type = '')
          AND sgg_cd IS NOT NULL AND umd_nm IS NOT NULL AND jibun IS NOT NULL
        ORDER BY id ASC
    """)
    buildings = cur.fetchall()
    cur.close(); conn.close()

    total_bldgs = len(buildings)
    print(f"[시작] 미분류 대상 {total_bldgs}건, 오늘 호출 {prog['calls_today']}/{args.daily_cap}")

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

    bjd = _get_bjdmap()

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
                        print("[reclassify] 다른 실행이 소유권을 가져갔습니다 — 중단.")
                        return False, processed, updated, prog["calls_today"]
                except Exception:
                    pass

            bname = row.get("building_name") or f"id={row['id']}"

            bjd_cd = bjd.find_bjdong_cd(row["sgg_cd"], row["umd_nm"])
            if not bjd_cd:
                skipped += 1
                processed += 1
                print(f"  [{processed:4d}] {bname[:28]:28s} → bjdong_cd 없음, skip")
                continue

            plat_gb, bun, ji = parse_jibun(row["jibun"])
            processed += 1
            prog["calls_today"] += 1

            try:
                label, detail, subtype, title, reason = classify_lodging_type(
                    row["sgg_cd"], bjd_cd, plat_gb, bun, ji
                )
            except Exception as e:
                skipped += 1
                print(f"  [{processed:4d}] {bname[:28]:28s} → API 오류: {e}")
                time.sleep(args.sleep)
                continue

            if label is None:
                skipped += 1
                reason_short = (reason or "")[:60]
                print(f"  [{processed:4d}] {bname[:28]:28s} → 판정 불가(그대로), {reason_short!r}")
                time.sleep(args.sleep)
                continue

            print(f"  [{processed:4d}] {bname[:28]:28s} → {label} / {detail or '-'} / {subtype or '-'}")
            if not args.dry_run:
                try:
                    upd_conn = get_conn(); upd_cur = upd_conn.cursor()
                    upd_cur.execute("""
                        UPDATE master_buildings
                        SET lodging_type=%s, lodging_type_detail=%s, lodging_subtype=%s,
                            verified_at=NOW()
                        WHERE id=%s
                    """, (label, detail, subtype, row["id"]))
                    upd_conn.commit()
                    upd_cur.close(); upd_conn.close()
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
    ap = argparse.ArgumentParser(description="미분류 건물 재판정 배치")
    ap.add_argument("--probe",      action="store_true", help="3건 원본 결과 확인 후 종료 (DB 안 씀)")
    ap.add_argument("--dry-run",    action="store_true", help="UPDATE 없이 결과만 출력")
    ap.add_argument("--limit",      type=int, default=0, help="처리 건수 상한 (0=무제한)")
    ap.add_argument("--daily-cap",  type=int, default=200, dest="daily_cap",
                    help="일일 처리 건수 상한 (기본 200)")
    ap.add_argument("--sleep",      type=float, default=0.5,
                    help="API 호출 간 대기 초 (기본 0.5)")
    ap.add_argument("--reset",      action="store_true", help="체크포인트 초기화 후 처음부터")
    ap.add_argument("--status-key", default=None, dest="status_key",
                    help="app_meta heartbeat 키 (관리자 버튼용)")
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
