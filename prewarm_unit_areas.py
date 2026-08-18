# -*- coding: utf-8 -*-
"""
prewarm_unit_areas.py — building_unit_areas 프리워밍 배치

master_buildings 중 building_unit_areas 캐시가 없거나 만료된 건물에 대해
건축HUB 전유부 API(fetch_expos_area_strict)를 미리 호출해 DB에 채워 둔다.

채워 두면 건물 패널을 처음 열 때부터 전용면적 드롭다운에 호실수(N실)가 즉시 표시된다.

동작 원칙
---------
- API가 정상 응답하되 전유부가 0건이면 sentinel row(NULL, NULL) 저장 → 7일간 재조회 억제.
- HTTP 오류·재시도 초과·XML 파싱 실패 등 전송 계층 장애는 예외로 전파되므로,
  sentinel을 쓰지 않고 consec_err를 증가시킨다.
  연속 10건 실패 시 API 쿼터 소진/장애로 판단해 자동 중단한다.

사용법
------
python prewarm_unit_areas.py               # 미캐시 건물 전체 (기본)
python prewarm_unit_areas.py --limit 200   # 앞 200건만
python prewarm_unit_areas.py --ids 1,2,3   # 특정 id만
python prewarm_unit_areas.py --all         # 7일 캐시가 있어도 재조회
python prewarm_unit_areas.py --daily-cap 500 --sleep 0.5   # 하루 500건, 호출간 0.5s

속도 지침 (건축HUB 부담 최소화)
  --sleep 기본 0.3s.  야간 실행 시 0.2~0.3s 권장.
  연속 오류 10건이면 API 쿼터 소진/장애로 판단, 자동 중단.
"""

import argparse
import os
import sys
import time
from datetime import datetime

from psycopg2.extras import execute_values

from address_utils import BjdongMap, parse_jibun
from building_registry import fetch_expos_area_strict
from db import get_conn, init_db

BJDONG_CSV = os.environ.get("BJDONG_CODE_CSV", "법정동코드_전체자료.zip")


def _target_query(ids=None, only_missing=True, limit=None):
    """대상 건물 SELECT SQL + params 반환."""
    base_where = [
        "sgg_cd IS NOT NULL",
        "umd_nm IS NOT NULL",
        "jibun IS NOT NULL",
    ]
    params = []

    if ids:
        base_where.append("id = ANY(%s)")
        params.append(ids)
    elif only_missing:
        # 7일 이내 캐시 행이 하나도 없는 건물만
        base_where.append("""NOT EXISTS (
            SELECT 1 FROM building_unit_areas
            WHERE master_building_id = master_buildings.id
              AND fetched_at > NOW() - INTERVAL '7 days'
        )""")

    sql = (
        "SELECT id, building_name, sgg_cd, umd_nm, jibun "
        f"FROM master_buildings WHERE {' AND '.join(base_where)} ORDER BY id"
    )
    if limit:
        sql += f" LIMIT {int(limit)}"
    return sql, params


def _save_areas(cur, building_id, raw):
    """raw=[(ho, sqm), ...] 또는 [] → building_unit_areas에 저장 (기존 행 교체).

    raw가 비어 있으면 sentinel row(NULL, NULL)를 삽입해 7일간 재조회를 억제한다.
    이 함수는 API가 정상 응답했을 때만 호출해야 한다.
    전송 계층 오류는 호출 전에 예외로 처리한다.
    """
    cur.execute("DELETE FROM building_unit_areas WHERE master_building_id = %s", [building_id])
    if raw:
        execute_values(
            cur,
            "INSERT INTO building_unit_areas (master_building_id, ho, area_sqm) VALUES %s",
            [(building_id, ho, sqm) for ho, sqm in raw],
        )
    else:
        # API 정상 응답 + 0건 → sentinel: 7일간 재조회 억제
        cur.execute(
            "INSERT INTO building_unit_areas (master_building_id, ho, area_sqm)"
            " VALUES (%s, NULL, NULL)",
            [building_id],
        )


def run(limit=None, ids=None, only_missing=True, sleep=0.3, daily_cap=None):
    """
    Returns (n_ok, n_empty, n_skip, n_err).

    n_ok   : 전유부 데이터가 있어 ho/sqm 행을 저장한 건수
    n_empty: API 정상 응답 0건 → sentinel 저장
    n_skip : bjdong_cd 못 찾거나 주소 파싱 실패 → DB 미저장
    n_err  : 전송 계층 오류(HTTP/재시도/XML) 등 예외 발생
    """
    init_db()
    bjdong = BjdongMap(BJDONG_CSV)
    conn = get_conn()
    cur = conn.cursor()

    sql, params = _target_query(ids=ids, only_missing=only_missing, limit=limit)
    cur.execute(sql, params)
    targets = cur.fetchall()

    total = len(targets)
    mode = "all" if not only_missing and not ids else f"only_missing={only_missing}"
    print(f"[시작] 대상 {total}건 ({mode}, limit={limit}, daily_cap={daily_cap})", flush=True)

    n_ok = n_empty = n_skip = n_err = 0
    consec_err = 0

    for i, b in enumerate(targets, 1):
        if daily_cap and (n_ok + n_empty) >= daily_cap:
            print(f"[일일 한도] {daily_cap}건 도달. 나머지는 다음 실행에.", flush=True)
            break

        bid, name = b["id"], b["building_name"]

        try:
            bjd = bjdong.find_bjdong_cd(b["sgg_cd"], b["umd_nm"])
            if not bjd:
                n_skip += 1
                print(
                    f"  [{i}/{total}] SKIP  id={bid} {name}"
                    f" — bjdong_cd 못찾음(umd={b['umd_nm']})",
                    flush=True,
                )
                time.sleep(sleep)
                continue

            plat_gb, bun, ji = parse_jibun(b["jibun"])

            # fetch_expos_area_strict: 전송 오류·resultCode 비정상 시 예외 전파
            # 정상 응답 0건이면 [] 반환 → sentinel 삽입
            raw = fetch_expos_area_strict(b["sgg_cd"], bjd, plat_gb, bun, ji)
            # 여기까지 도달 = API 정상 응답 → consec_err 초기화
            consec_err = 0

            _save_areas(cur, bid, raw)
            # 건물별 즉시 커밋: 이후 건물에서 오류가 생겨도 이 건물의 쓰기는 보존
            conn.commit()

            if raw:
                n_ok += 1
                print(
                    f"  [{i}/{total}] OK    id={bid} {name}"
                    f" — {len(raw)}개 호실",
                    flush=True,
                )
            else:
                n_empty += 1
                print(
                    f"  [{i}/{total}] EMPTY id={bid} {name}"
                    f" — 전유부 없음(sentinel 저장)",
                    flush=True,
                )

        except Exception as e:
            # 전송 계층·API 오류: sentinel 미저장, consec_err 증가
            # 이 건물에 대해 uncommitted 상태인 변경은 없으므로 rollback 불필요
            n_err += 1
            consec_err += 1
            print(
                f"  [{i}/{total}] ERR   id={bid} {name}"
                f" — {type(e).__name__}: {e}",
                flush=True,
            )
            if consec_err >= 10:
                print(
                    "[중단] 연속 오류 10건 — API 쿼터 소진/장애 추정."
                    " 남은 건은 나중에 재실행하세요.",
                    flush=True,
                )
                return n_ok, n_empty, n_skip, n_err
            time.sleep(sleep)
            continue

        if i % 50 == 0:
            print(
                f"  ...진행 {i}/{total}"
                f" (OK={n_ok} EMPTY={n_empty} SKIP={n_skip} ERR={n_err})",
                flush=True,
            )

        time.sleep(sleep)

    cur.close()
    conn.close()

    print(
        f"[완료] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} —"
        f" 처리 {n_ok + n_empty + n_skip + n_err}건 /"
        f" OK={n_ok} EMPTY={n_empty} SKIP={n_skip} ERR={n_err}",
        flush=True,
    )
    return n_ok, n_empty, n_skip, n_err


def main():
    ap = argparse.ArgumentParser(
        description="building_unit_areas 프리워밍: 전유부(호실별 전용면적)를 DB에 미리 채운다."
    )
    ap.add_argument("--limit", type=int, default=None, help="처리 건수 상한 (샘플 확인용)")
    ap.add_argument("--ids", type=str, default=None, help="쉼표구분 id 목록 (예: 1,2,3)")
    ap.add_argument(
        "--all",
        action="store_true",
        help="7일 캐시가 있어도 재조회 (기본: 미캐시 건물만)",
    )
    ap.add_argument(
        "--daily-cap",
        type=int,
        default=None,
        metavar="N",
        help="하루 최대 처리 건수(OK+EMPTY 기준). 초과 시 중단.",
    )
    ap.add_argument(
        "--sleep",
        type=float,
        default=0.3,
        help="건물 간 대기 초 (기본 0.3s). 야간 실행 시 0.2~0.3 권장.",
    )
    args = ap.parse_args()

    ids = [int(x) for x in args.ids.split(",") if x.strip()] if args.ids else None

    n_ok, n_empty, n_skip, n_err = run(
        limit=args.limit,
        ids=ids,
        only_missing=not args.all,
        sleep=args.sleep,
        daily_cap=args.daily_cap,
    )
    if n_err and n_ok + n_empty == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
