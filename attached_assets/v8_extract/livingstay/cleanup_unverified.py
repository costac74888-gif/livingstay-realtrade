# -*- coding: utf-8 -*-
"""
cleanup_unverified.py — verified_at이 비어있는 기존 master_buildings 항목을
                        전부 재검증해서, 생숙이 아닌 것으로 판명되면 제거한다.

배경
------------------------------------------------------------
sync_batch.py의 예전 "건축HUB 보완" 경로가 검증 없이 이름만 붙이던 시절 들어온
데이터(대표적으로 '한화호텔앤드리조트/평창' = 실제로는 휴양콘도미니엄)를 정리한다.
verified_at이 있는 항목(신규 발굴/재검증/sync_verified로 이미 검증된 것)은 건드리지 않는다.

실행
------------------------------------------------------------
python cleanup_unverified.py            # 실제로 삭제 실행
python cleanup_unverified.py --dry-run  # 뭐가 지워질지만 미리 보기 (삭제 안 함)
"""

import argparse
import time

from db import get_conn
from address_utils import BjdongMap
from building_registry import is_living_stay

import os
BJDONG_CODE_CSV = os.environ.get("BJDONG_CODE_CSV", "법정동코드 전체자료.csv")


def parse_jibun_simple(jibun: str):
    plat_gb = "1" if jibun.startswith("산") else "0"
    jibun = jibun.replace("산", "").strip()
    if "-" in jibun:
        bun, ji = jibun.split("-", 1)
    else:
        bun, ji = jibun, "0"
    return plat_gb, bun or "0", ji or "0"


def cleanup(dry_run: bool):
    bjdong = BjdongMap(BJDONG_CODE_CSV)
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, building_name, sgg_cd, umd_nm, jibun
        FROM master_buildings
        WHERE verified_at IS NULL AND sgg_cd IS NOT NULL AND umd_nm IS NOT NULL AND jibun IS NOT NULL
    """)
    targets = cur.fetchall()
    print(f"재검증 대상(미검증): {len(targets)}건")

    kept, removed, unknown = 0, 0, 0

    for row in targets:
        plat_gb, bun, ji = parse_jibun_simple(row["jibun"])
        bjdong_cd = bjdong.find_bjdong_cd(row["sgg_cd"], row["umd_nm"])
        if not bjdong_cd:
            unknown += 1
            continue

        try:
            verdict, title, reason = is_living_stay(row["sgg_cd"], bjdong_cd, plat_gb, bun, ji)
        except Exception as e:
            print(f"  검증 실패 (id={row['id']}, {row['building_name']}): {e}")
            unknown += 1
            continue

        if verdict is True:
            kept += 1
            if not dry_run:
                cur.execute("UPDATE master_buildings SET verified_at = NOW() WHERE id = %s", (row["id"],))
        elif verdict is False:
            removed += 1
            print(f"  제거 대상: {row['building_name']} ({row['umd_nm']} {row['jibun']}) — {reason}")
            if not dry_run:
                # 연관된 실거래도 함께 제거 (생숙 아닌 건물의 거래를 화면에 남겨두지 않음)
                cur.execute("""
                    DELETE FROM transactions
                    WHERE sgg_cd=%s AND umd_nm=%s AND jibun=%s
                """, (row["sgg_cd"], row["umd_nm"], row["jibun"]))
                cur.execute("DELETE FROM master_buildings WHERE id = %s", (row["id"],))
        else:
            unknown += 1  # 조회 실패 등 — 다음에 다시 시도

        if not dry_run:
            conn.commit()
        time.sleep(0.1)

    cur.close()
    conn.close()

    mode = "(시뮬레이션만 — 실제 삭제 안 함)" if dry_run else ""
    print(f"\n완료 {mode} — 확인/유지: {kept}건 / 제거: {removed}건 / 판정보류(재시도필요): {unknown}건")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    cleanup(args.dry_run)
