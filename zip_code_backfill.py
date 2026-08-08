#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
zip_code_backfill.py — master_buildings.zip_code 1회성 백필

zip_code가 NULL이고 road_address가 있는 건물을 대상으로
JUSO API(address_utils.road_to_jibun)를 재호출해 zipNo만 채워넣는다.

JUSO API 일일 한도: 행안부 기본 제공 500,000건/일 (공공데이터 일반).
이 배치 전용 캡(--daily-cap)은 기본 3,000건으로 설정해 다른 JUSO 호출과
예산을 공유하지 않는다(PROJECT_PRINCIPLES.md 영역1 원칙).

사용법:
  python zip_code_backfill.py               # 기본 실행 (캡 3,000, 슬립 0.3초)
  python zip_code_backfill.py --daily-cap 1000 --sleep 0.5
  python zip_code_backfill.py --limit 50    # 소량 테스트
"""

import argparse
import json
import os
import sys
import time

import psycopg2
import psycopg2.extras

PROGRESS_FILE = "zip_code_backfill_progress.json"
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("PROD_DATABASE_URL", "")


def get_conn():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)


def load_progress():
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"done": 0, "calls_today": 0, "last_id": 0}


def save_progress(prog):
    with open(PROGRESS_FILE, "w") as f:
        json.dump(prog, f)


def main():
    parser = argparse.ArgumentParser(description="zip_code 백필 배치")
    parser.add_argument("--daily-cap", type=int, default=3000, help="JUSO API 일일 최대 호출수 (기본 3,000)")
    parser.add_argument("--sleep", type=float, default=0.3, help="건물 간 대기(초, 기본 0.3)")
    parser.add_argument("--limit", type=int, default=0, help="처리 건수 제한 (0=무제한, 테스트용)")
    parser.add_argument("--prod", action="store_true", help="Prod DB(PROD_DATABASE_URL) 대상")
    parser.add_argument("--reset-progress", action="store_true", help="진행 파일 초기화 후 처음부터")
    args = parser.parse_args()

    if args.prod and not os.environ.get("PROD_DATABASE_URL"):
        print("[오류] --prod 옵션이지만 PROD_DATABASE_URL 환경변수가 없습니다.")
        sys.exit(1)

    # --prod면 PROD_DATABASE_URL, 아니면 DATABASE_URL
    global DATABASE_URL
    if args.prod:
        DATABASE_URL = os.environ["PROD_DATABASE_URL"]

    if args.reset_progress and os.path.exists(PROGRESS_FILE):
        os.remove(PROGRESS_FILE)
        print("[초기화] 진행 파일 삭제 — 처음부터 재시작합니다.")

    prog = load_progress()
    print(f"[시작] 오늘 호출 수: {prog['calls_today']}, 마지막 처리 id: {prog['last_id']}")

    # 로컬 임포트 (address_utils가 같은 디렉터리에 있어야 함)
    from address_utils import road_to_jibun

    conn = get_conn()
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
        road = row["road_address"]

        try:
            juso = road_to_jibun(road)
            prog["calls_today"] += 1
            if juso and (juso.get("zipNo") or "").strip():
                zip_val = juso["zipNo"].strip()
                cur.execute(
                    "UPDATE master_buildings SET zip_code=%s WHERE id=%s AND zip_code IS NULL",
                    (zip_val, bid),
                )
                conn.commit()
                prog["last_id"] = bid
                prog["done"] += 1
                n_ok += 1
                print(f"  [{i}/{len(rows)}] OK   id={bid} {name[:30]} → {zip_val}", flush=True)
            else:
                prog["last_id"] = bid
                n_empty += 1
                print(f"  [{i}/{len(rows)}] EMPTY id={bid} {name[:30]} — JUSO 응답 없음 또는 zipNo 빈값", flush=True)
        except Exception as e:
            n_err += 1
            print(f"  [{i}/{len(rows)}] ERR  id={bid} {name[:30]} — {type(e).__name__}: {e}", flush=True)

        save_progress(prog)
        if args.sleep > 0:
            time.sleep(args.sleep)

    cur.close()
    conn.close()

    print(f"\n[완료] 성공: {n_ok}건 / 응답없음: {n_empty}건 / 오류: {n_err}건")
    print(f"[현황] 총 JUSO 호출: {prog['calls_today']}건 (일일캡 {args.daily_cap})")

    # 최종 채움 현황
    conn2 = get_conn()
    cur2 = conn2.cursor()
    cur2.execute("SELECT COUNT(*) AS c FROM master_buildings WHERE zip_code IS NOT NULL")
    filled = cur2.fetchone()["c"]
    cur2.execute("SELECT COUNT(*) AS c FROM master_buildings WHERE zip_code IS NULL AND road_address IS NOT NULL")
    remaining = cur2.fetchone()["c"]
    cur2.close(); conn2.close()
    print(f"[DB 현황] zip_code 채움: {filled}건 / 미채움(road_address 있음): {remaining}건")


if __name__ == "__main__":
    main()
