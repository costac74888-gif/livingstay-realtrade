# -*- coding: utf-8 -*-
"""
reclassify_buildings.py — lodging_type이 비어있는 건물을 재검증해서
                          '생활'/'호텔'/'콘도' 중 하나로 분류한다.

이전 cleanup_unverified.py(삭제형)를 대체한다. 삭제는 되돌리기 어렵고,
"애매해서 삭제 못 함(판정보류)"으로 계속 쌓이는 게 비효율적이었다.
이제는 무엇이든 분류만 하고, 화면에서 용도 필터로 나눠 보여준다.

- 표제부/층별개요에서 판정 자체가 안 되는 건(표제부 없음 = 일반건축물 추정)은
  삭제하지 않고 lodging_type을 NULL로 남겨둔다 (화면 기본 필터에서 자연히 제외됨).
- 이미 lodging_type이 있는 건물(한 번 분류 완료)은 재검증 대상에서 제외 —
  --force 옵션을 주면 전체 재검증 가능.

주의(실거래 라벨 반영 키):
  마스터의 umd_nm은 정규화된 '봉평면면온리'(공백 없음)이고, 실거래(transactions)의
  umd_nm은 RTMS 원문 '봉평면 면온리'(공백 있음)라서 표기가 다르다. 또 같은 지번에
  여러 건물이 서 있는 경우(예: 대관령면 용산리 130)도 있어, 지번(sgg_cd+umd_nm+jibun)
  으로 실거래를 갱신하면 잘못된 건물끼리 라벨이 섞인다.
  → 실거래 라벨은 '건물명(building_name) + sgg_cd + jibun'으로 반영한다.
    (실거래는 매칭 시 마스터 building_name/sgg_cd/jibun을 그대로 복사해 저장하므로 정확히 일치)

사용법
------------------------------------------------------------
python reclassify_buildings.py                # 미분류 건물만 재검증
python reclassify_buildings.py --force        # 이미 분류된 것까지 전부 재검증
python reclassify_buildings.py --dry-run      # 실제 UPDATE 없이 결과만 출력
"""

import argparse
import os
import time

from db import get_conn
from address_utils import BjdongMap
from building_registry import classify_lodging_type

BJDONG_CODE_CSV = os.environ.get("BJDONG_CODE_CSV", "법정동코드 전체자료.csv")


def parse_jibun_simple(jibun: str):
    plat_gb = "1" if jibun.startswith("산") else "0"
    jibun = jibun.replace("산", "").strip()
    if "-" in jibun:
        bun, ji = jibun.split("-", 1)
    else:
        bun, ji = jibun, "0"
    return plat_gb, bun or "0", ji or "0"


def reclassify(force: bool, dry_run: bool):
    bjdong = BjdongMap(BJDONG_CODE_CSV)
    conn = get_conn()
    cur = conn.cursor()

    where = "sgg_cd IS NOT NULL AND umd_nm IS NOT NULL AND jibun IS NOT NULL"
    if not force:
        where += " AND lodging_type IS NULL"

    cur.execute(f"SELECT id, building_name, sgg_cd, umd_nm, jibun FROM master_buildings WHERE {where}")
    targets = cur.fetchall()
    print(f"재분류 대상: {len(targets)}건 (force={force})")

    counts = {"생활": 0, "호텔": 0, "콘도": 0, "복합(병기)": 0, "미확인": 0}

    for row in targets:
        plat_gb, bun, ji = parse_jibun_simple(row["jibun"])
        bjdong_cd = bjdong.find_bjdong_cd(row["sgg_cd"], row["umd_nm"])
        if not bjdong_cd:
            counts["미확인"] += 1
            continue

        try:
            label, detail, title, reason = classify_lodging_type(row["sgg_cd"], bjdong_cd, plat_gb, bun, ji)
        except Exception as e:
            print(f"  분류 실패 (id={row['id']}, {row['building_name']}): {e}")
            counts["미확인"] += 1
            continue

        key = "복합(병기)" if (label and "·" in label) else (label or "미확인")
        counts[key] += 1
        print(f"  [{key}] {row['building_name']} ({row['umd_nm']} {row['jibun']}) — {(detail or '')[:60]}")

        if not dry_run and label:
            cur.execute("""
                UPDATE master_buildings
                SET lodging_type = %s, lodging_type_detail = %s, verified_at = NOW()
                WHERE id = %s
            """, (label, detail, row["id"]))
            # 이 건물에 이미 쌓인 실거래에도 라벨을 같이 반영.
            # 지번 키가 아니라 '건물명+sgg_cd+jibun'으로 반영한다 (docstring 참조):
            #  - 마스터 umd_nm(정규화)과 실거래 umd_nm(RTMS 원문)이 공백 표기가 달라 지번키가 안 맞음
            #  - 같은 지번에 여러 건물이 있으면 라벨이 섞임
            cur.execute("""
                UPDATE transactions SET lodging_type = %s, lodging_type_detail = %s
                WHERE building_name = %s AND sgg_cd = %s AND jibun = %s
            """, (label, detail, row["building_name"], row["sgg_cd"], row["jibun"]))
            conn.commit()

        time.sleep(0.1)

    cur.close()
    conn.close()

    mode = "(시뮬레이션만 — 실제 반영 안 함)" if dry_run else ""
    print(f"\n완료 {mode}")
    for k, v in counts.items():
        print(f"  {k}: {v}건")


def reclassify_unmatched(dry_run: bool):
    """마스터에 없는(=lodging_type이 비어있는) 실거래 건물을 건축물대장으로 분류해서 라벨을 붙인다.

    '아난티'처럼 RTMS 실거래엔 있지만 생숙 마스터 목록엔 없는 건물이 대상.
    같은 지번(sgg_cd+umd_nm+jibun)의 건축물대장을 한 번만 조회해서, 그 위치의
    '아직 라벨 없는' 실거래에만 반영한다(이미 라벨된 실거래는 건드리지 않음).
    """
    bjdong = BjdongMap(BJDONG_CODE_CSV)
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT sgg_cd, umd_nm, jibun,
               COUNT(*) AS cnt,
               MIN(building_name) AS building_name
        FROM transactions
        WHERE lodging_type IS NULL
          AND sgg_cd IS NOT NULL AND umd_nm IS NOT NULL AND jibun IS NOT NULL
        GROUP BY sgg_cd, umd_nm, jibun
        ORDER BY cnt DESC
    """)
    targets = cur.fetchall()
    print(f"미매칭 실거래 위치: {len(targets)}곳 (라벨 없는 실거래를 건축물대장으로 분류)")

    counts = {"생활": 0, "호텔": 0, "콘도": 0, "복합(병기)": 0, "미확인": 0}
    updated_tx = 0

    for row in targets:
        plat_gb, bun, ji = parse_jibun_simple(row["jibun"])
        bjdong_cd = bjdong.find_bjdong_cd(row["sgg_cd"], row["umd_nm"])
        if not bjdong_cd:
            counts["미확인"] += 1
            continue

        try:
            label, detail, title, reason = classify_lodging_type(row["sgg_cd"], bjdong_cd, plat_gb, bun, ji)
        except Exception as e:
            print(f"  분류 실패 ({row['building_name']} {row['umd_nm']} {row['jibun']}): {e}")
            counts["미확인"] += 1
            continue

        key = "복합(병기)" if (label and "·" in label) else (label or "미확인")
        counts[key] += 1
        print(f"  [{key}] {row['building_name']} ({row['umd_nm']} {row['jibun']}, {row['cnt']}건) — {(detail or '')[:60]}")

        if not dry_run and label:
            # 이 지번의 '아직 라벨 없는' 실거래에만 반영 (이미 라벨된 매칭 실거래는 보존)
            cur.execute("""
                UPDATE transactions
                SET lodging_type = %s, lodging_type_detail = %s
                WHERE sgg_cd = %s AND umd_nm = %s AND jibun = %s AND lodging_type IS NULL
            """, (label, detail, row["sgg_cd"], row["umd_nm"], row["jibun"]))
            updated_tx += cur.rowcount
            conn.commit()

        time.sleep(0.1)

    cur.close()
    conn.close()

    mode = "(시뮬레이션만 — 실제 반영 안 함)" if dry_run else ""
    print(f"\n미매칭 실거래 분류 완료 {mode}  (라벨 반영 실거래 {updated_tx}건)")
    for k, v in counts.items():
        print(f"  {k}: {v}건")


def export_new_master():
    """건축물대장 용도가 반영된 master_buildings를 '신마스터' 엑셀로 내보낸다.
    파일명에 업데이트일(YYYYMMDD)을 붙여 이력 관리가 되게 한다."""
    from datetime import datetime
    import openpyxl

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT road_address, building_name, units, biz_units,
               lodging_type, lodging_type_detail, verified_at
        FROM master_buildings
        ORDER BY building_name
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    today = datetime.now().strftime("%Y%m%d")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "신마스터"
    ws.append([f"생활숙박시설 신마스터 (건축물대장 용도 반영) — 총 {len(rows)}건 · 업데이트일 {today}"])
    ws.append(["소재지", "건물명", "호수", "영업신고호수", "용도", "용도상세(대장원문)", "검증일"])
    for r in rows:
        va = r["verified_at"].strftime("%Y-%m-%d") if r["verified_at"] else ""
        ws.append([
            r["road_address"], r["building_name"], r["units"], r["biz_units"],
            r["lodging_type"] or "미확인", r["lodging_type_detail"] or "", va,
        ])

    fname = f"신마스터_생활숙박시설현황_{today}.xlsx"
    wb.save(fname)
    print(f"신마스터 저장: {fname} ({len(rows)}건)")
    return fname


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="이미 분류된 건물까지 전부 재검증")
    parser.add_argument("--dry-run", action="store_true", help="실제 반영 없이 결과만 출력")
    parser.add_argument("--unmatched", action="store_true", help="마스터에 없는 미매칭 실거래 건물도 건축물대장으로 분류/라벨")
    parser.add_argument("--export", action="store_true", help="완료 후 신마스터 엑셀(업데이트일 포함) 내보내기")
    args = parser.parse_args()

    # 아무 대상 플래그도 없거나 --force면 마스터 재분류를 먼저 수행 (기존 동작 유지)
    if args.force or not (args.unmatched or args.export):
        reclassify(args.force, args.dry_run)
    if args.unmatched:
        reclassify_unmatched(args.dry_run)
    if args.export:
        export_new_master()
