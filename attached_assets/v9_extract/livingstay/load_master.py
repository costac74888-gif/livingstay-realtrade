# -*- coding: utf-8 -*-
"""
load_master.py — 첨부 마스터파일(생활숙박시설현황_전국통합.xlsx)을
                 master_buildings 테이블에 적재한다.

30실 미만(개인 소유 소형 펜션·풀빌라 등)은 집합건축물대장이 아니라
일반건축물대장으로 등록되는 경우가 대부분이라, 우리 파이프라인
(RTMS 유형='집합' 매칭)이 애초에 커버할 수 없다. 그래서 기본값으로
30실 이상만 적재하고 나머지는 별도 로그로만 남긴다.

사용법
------------------------------------------------------------
python load_master.py /path/to/생활숙박시설현황_전국통합_....xlsx
python load_master.py /path/to/파일.xlsx --min-units 20   # 기준 조정 시
python load_master.py /path/to/파일.xlsx --min-units 0    # 전체 적재(필터 끄기)
"""

import sys
import argparse
import pandas as pd
from db import get_conn, init_db


def extract_sgg_text(addr: str):
    """'경기도 가평군 청평면 ...' → '경기도 가평군' """
    toks = str(addr).split()
    if len(toks) >= 2:
        return f"{toks[0]} {toks[1]}"
    return None


def load_master_file(xlsx_path: str, min_units: int = 30):
    init_db()

    # 실제 헤더는 2번째 행(0-index 1)에 있음: 소재지/건물명/호수/영업신고호수/비고
    df = pd.read_excel(xlsx_path, sheet_name=0, header=1)
    df.columns = ["road_address", "building_name", "units", "biz_units", "note"][: len(df.columns)]
    df = df.dropna(subset=["road_address", "building_name"])

    df["units_num"] = pd.to_numeric(df["units"], errors="coerce")
    df["biz_units_num"] = pd.to_numeric(df["biz_units"], errors="coerce")
    df["unit_est"] = df["units_num"].fillna(df["biz_units_num"])

    total_count = len(df)

    if min_units > 0:
        kept = df[df["unit_est"] >= min_units].copy()
        dropped = df[~(df["unit_est"] >= min_units)].copy()
    else:
        kept = df.copy()
        dropped = df.iloc[0:0].copy()

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("DELETE FROM master_buildings")  # 매번 최신 마스터파일로 전체 교체

    inserted = 0
    for _, row in kept.iterrows():
        road_address = str(row["road_address"]).strip()
        building_name = str(row["building_name"]).strip()
        sgg_text = extract_sgg_text(road_address)
        units = int(row["units_num"]) if pd.notna(row.get("units_num")) else None
        biz_units = int(row["biz_units_num"]) if pd.notna(row.get("biz_units_num")) else None

        cur.execute("""
            INSERT INTO master_buildings (building_name, road_address, sgg_text, units, biz_units)
            VALUES (%s, %s, %s, %s, %s)
        """, (building_name, road_address, sgg_text, units, biz_units))
        inserted += 1

    conn.commit()

    # 배치 대상 시군구 목록 미리 확인
    cur.execute("SELECT sgg_text, COUNT(*) c FROM master_buildings GROUP BY sgg_text ORDER BY c DESC")
    regions = cur.fetchall()
    cur.close()
    conn.close()

    print(f"원본 마스터 {total_count}건 중 기준({min_units}실 이상) 충족 {inserted}건 적재")
    print(f"제외된 소규모/미확인 건물: {len(dropped)}건 (일반건축물 등록 추정, 이번 파이프라인 대상 아님)")
    print(f"배치 대상 시군구 수: {len(regions)}개")
    for r in regions[:15]:
        print(f"  {r['sgg_text']}: {r['c']}건")

    # 제외된 목록은 참고용으로 csv에 남겨둠 (나중에 별도 소형 펜션 트랙 만들 때 활용 가능)
    if len(dropped) > 0:
        drop_path = "excluded_small_buildings.csv"
        dropped[["road_address", "building_name", "unit_est"]].to_csv(drop_path, index=False, encoding="utf-8-sig")
        print(f"제외 목록 저장: {drop_path}")

    return inserted, [r["sgg_text"] for r in regions]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("xlsx_path", help="마스터파일 경로")
    parser.add_argument("--min-units", type=int, default=30, help="최소 호수 기준 (기본 30, 0이면 전체 적재)")
    args = parser.parse_args()

    load_master_file(args.xlsx_path, min_units=args.min_units)

