# -*- coding: utf-8 -*-
"""
backfill_address.py — transactions에 si_do/sgg_nm이 비어있는 기존 행을
                       sgg_cd 하나만으로 일괄 채운다.

배경
------------------------------------------------------------
sgg_cd(법정동코드 5자리)는 어떤 적재 경로로 들어왔든 RTMS 원본에 항상 있는 값이라
누락될 수 없다. 그런데 si_do/sgg_nm은 예전 코드가 "마스터 건물의 sgg_text를 파싱"
하는 방식에 의존하고 있어서, 그 파싱이 안 된 일부 행만 시/도가 비어있었다.
(예: "둔산동 1313"처럼 표시되던 행들)

이 스크립트는 그런 행을 전부 sgg_cd → BjdongMap.sgg_text()로 다시 계산해 채운다.
이후 sync_batch.py는 항상 이 방식(sgg_cd 기준)으로 계산하도록 이미 고쳐졌으므로,
이 백필은 "지금까지 쌓인 것"만 한 번 정리하면 되는 1회성 작업이다.

사용법
------------------------------------------------------------
python backfill_address.py --dry-run   # 몇 건이 채워질지만 미리 확인
python backfill_address.py             # 실제 반영
"""

import argparse
import os

from db import get_conn
from address_utils import BjdongMap

BJDONG_CODE_CSV = os.environ.get("BJDONG_CODE_CSV", "법정동코드 전체자료.csv")


def backfill(dry_run: bool):
    bjdong = BjdongMap(BJDONG_CODE_CSV)
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT DISTINCT sgg_cd FROM transactions
        WHERE (si_do IS NULL OR sgg_nm IS NULL) AND sgg_cd IS NOT NULL
    """)
    codes = [r["sgg_cd"] for r in cur.fetchall()]
    print(f"시/도 보강이 필요한 시군구코드: {len(codes)}개")

    total_updated = 0
    for sgg_cd in codes:
        sgg_text = bjdong.sgg_text(sgg_cd)
        if not sgg_text:
            print(f"  ⚠ {sgg_cd}: 법정동코드 매핑 실패 — 건너뜀")
            continue

        parts = sgg_text.split(" ", 1)
        si_do_val = parts[0] if len(parts) > 0 else None
        sgg_nm_val = parts[1] if len(parts) > 1 else None

        cur.execute("""
            SELECT COUNT(*) c FROM transactions
            WHERE sgg_cd = %s AND (si_do IS NULL OR sgg_nm IS NULL)
        """, (sgg_cd,))
        affected = cur.fetchone()["c"]

        print(f"  {sgg_cd} → {sgg_text} ({affected}건)")

        if not dry_run:
            cur.execute("""
                UPDATE transactions SET si_do = %s, sgg_nm = %s
                WHERE sgg_cd = %s AND (si_do IS NULL OR sgg_nm IS NULL)
            """, (si_do_val, sgg_nm_val, sgg_cd))
            conn.commit()

        total_updated += affected

    cur.close()
    conn.close()

    mode = "(시뮬레이션만 — 실제 반영 안 함)" if dry_run else "완료"
    print(f"\n{mode} — 총 {total_updated}건 대상")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    backfill(args.dry_run)
