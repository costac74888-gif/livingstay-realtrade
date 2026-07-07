# -*- coding: utf-8 -*-
"""
load_master.py — 첨부 마스터파일(생활숙박시설현황_전국통합.xlsx)을
                 master_buildings 테이블에 적재한다.

사용법
------------------------------------------------------------
python load_master.py /path/to/생활숙박시설현황_전국통합_....xlsx
"""

import sys
import pandas as pd
from db import get_conn, init_db


def extract_sgg_text(addr: str):
    """'경기도 가평군 청평면 ...' → '경기도 가평군' """
    toks = str(addr).split()
    if len(toks) >= 2:
        return f"{toks[0]} {toks[1]}"
    return None


def load_master_file(xlsx_path: str):
    init_db()

    # 실제 헤더는 2번째 행(0-index 1)에 있음: 소재지/건물명/호수/영업신고호수/비고
    df = pd.read_excel(xlsx_path, sheet_name=0, header=1)
    df.columns = ["road_address", "building_name", "units", "biz_units", "note"][: len(df.columns)]
    df = df.dropna(subset=["road_address", "building_name"])

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("DELETE FROM master_buildings")  # 매번 최신 마스터파일로 전체 교체

    inserted = 0
    for _, row in df.iterrows():
        road_address = str(row["road_address"]).strip()
        building_name = str(row["building_name"]).strip()
        sgg_text = extract_sgg_text(road_address)
        units = int(row["units"]) if pd.notna(row.get("units")) else None
        biz_units = int(row["biz_units"]) if pd.notna(row.get("biz_units")) else None

        cur.execute("""
            INSERT INTO master_buildings (building_name, road_address, sgg_text, units, biz_units)
            VALUES (?, ?, ?, ?, ?)
        """, (building_name, road_address, sgg_text, units, biz_units))
        inserted += 1

    conn.commit()

    # 배치 대상 시군구 목록 미리 확인
    cur.execute("SELECT sgg_text, COUNT(*) c FROM master_buildings GROUP BY sgg_text ORDER BY c DESC")
    regions = cur.fetchall()
    conn.close()

    print(f"마스터 건물 {inserted}건 적재 완료")
    print(f"배치 대상 시군구 수: {len(regions)}개")
    for r in regions[:10]:
        print(f"  {r['sgg_text']}: {r['c']}건")

    return inserted, [r["sgg_text"] for r in regions]


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법: python load_master.py <마스터파일.xlsx>")
        sys.exit(1)
    load_master_file(sys.argv[1])
