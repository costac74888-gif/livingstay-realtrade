# -*- coding: utf-8 -*-
"""
reclassify_brhub.py — sync_brhub.py가 미분류(lodging_type IS NULL)로 남긴 brhub_bulk 건물을
층별개요(getBrFlrOulnInfo)까지 조회하는 building_registry.classify_lodging_type()으로 재분류.

- 대상: source='brhub_bulk' AND lodging_type IS NULL AND sgg_cd/umd_nm/jibun 존재
- 판정 성공 → lodging_type/lodging_type_detail 갱신
- 여전히 판정불가 → lodging_type_detail 앞에 '[재분류불가]' 마커를 붙여 재시도 대상에서 제외
- 체크포인트 불필요(대상 쿼리 자체가 남은 것만 뽑음), 건별 커밋

사용:
  python -u reclassify_brhub.py                # 전량
  python -u reclassify_brhub.py --limit 100    # 일부만
"""

import argparse
import os

from db import get_conn
from address_utils import parse_jibun, BjdongMap
from building_registry import classify_lodging_type

MARKER = "[재분류불가]"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    conn = get_conn()
    cur = conn.cursor()
    bjdong = BjdongMap(os.environ.get("BJDONG_CODE_CSV", "법정동코드_전체자료.zip"))

    q = """
        SELECT id, building_name, sgg_cd, umd_nm, jibun, lodging_type_detail
        FROM master_buildings
        WHERE source='brhub_bulk' AND lodging_type IS NULL
          AND sgg_cd IS NOT NULL AND umd_nm IS NOT NULL AND jibun IS NOT NULL
          AND (lodging_type_detail IS NULL OR lodging_type_detail NOT LIKE %s)
        ORDER BY id
    """
    params = [MARKER + "%"]
    if args.limit:
        q += " LIMIT %s"
        params.append(args.limit)
    cur.execute(q, params)
    rows = cur.fetchall()
    print(f"재분류 대상: {len(rows)}건")

    ok = fail = 0
    for r in rows:
        bjdong_cd = bjdong.find_bjdong_cd(r["sgg_cd"], r["umd_nm"])
        if not bjdong_cd:
            print(f"  [{r['id']}] {r['building_name']}: 법정동코드 못 찾음({r['umd_nm']}) — 건너뜀")
            fail += 1
            continue
        plat_gb, bun, ji = parse_jibun(r["jibun"])
        try:
            label, detail, _title, reason = classify_lodging_type(r["sgg_cd"], bjdong_cd, plat_gb, bun, ji)
        except Exception as e:
            print(f"  [{r['id']}] {r['building_name']}: API 오류 {repr(e)[:100]} — 다음 실행 때 재시도")
            continue
        if label:
            cur.execute("UPDATE master_buildings SET lodging_type=%s, lodging_type_detail=%s WHERE id=%s",
                        (label, (detail or "")[:500] or None, r["id"]))
            ok += 1
            print(f"  [{r['id']}] {r['building_name']} → {label} ({reason})")
        elif "실패" in (reason or "") or "재시도" in (reason or ""):
            # API 일시 실패 — 마커를 붙이지 않아 다음 실행 때 자동 재시도
            fail += 1
            print(f"  [{r['id']}] {r['building_name']} → 일시 실패, 다음 실행 때 재시도 ({reason})")
        else:
            old = r["lodging_type_detail"] or ""
            cur.execute("UPDATE master_buildings SET lodging_type_detail=%s WHERE id=%s",
                        ((MARKER + " " + old)[:500], r["id"]))
            fail += 1
            print(f"  [{r['id']}] {r['building_name']} → 판정불가 ({reason})")
        conn.commit()

    print(f"\n[종료] 재분류 성공 {ok}, 판정불가/실패 {fail}")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()


