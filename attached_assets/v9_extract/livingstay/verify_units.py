# -*- coding: utf-8 -*-
"""
verify_units.py — 마스터파일에서 "호수 미확인"으로 제외됐던 건물들을
                   건축HUB 총괄표제부(getBrRecapTitleInfo)로 실제 세대수를 조회해
                   재확인한다.

왜 필요한가
------------------------------------------------------------
load_master.py가 30실 미만/미확인 건물을 excluded_small_buildings.csv 로 빼두는데,
그 중 "호수 정보 없음(엑셀 미기재)" 건은 실제로는 대형 건물인데 입력만 누락됐을
가능성이 있다. 이 스크립트는 그런 건들을 국토부 공식 데이터로 재확인해서
잘못 제외된 건물을 구제한다.

흐름
------------------------------------------------------------
excluded_small_buildings.csv 의 도로명주소
  → juso.go.kr 로 지번주소/법정동 확보 (address_utils.road_to_jibun)
  → 건축HUB 총괄표제부 조회(getBrRecapTitleInfo) 로 공식 세대수/호수 확인
  → 30실 이상이면 master_buildings 에 INSERT (재등록)
  → 결과를 verify_result.csv 로 남김 (재등록 여부, 확인된 세대수)

사용법
------------------------------------------------------------
python verify_units.py excluded_small_buildings.csv --min-units 30
"""

import os
import argparse
import time
from xml.etree import ElementTree as ET

import requests
import pandas as pd

from db import get_conn
from address_utils import road_to_jibun, BjdongMap

BLD_SERVICE_KEY = os.environ["BLD_SERVICE_KEY"]  # sync_batch.py와 동일한 키
# 총괄표제부(getBrRecapTitleInfo)는 대지에 동(棟)이 여러 개일 때만 생성되는 문서라
# 단일 동 건물(생숙 대부분)에서는 0건으로 잡히는 문제가 있어 표제부(getBrTitleInfo)로 조회한다.
BLD_TITLE_URL = "https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo"
BJDONG_CODE_CSV = os.environ.get("BJDONG_CODE_CSV", "법정동코드 전체자료.csv")

REQUEST_SLEEP = 0.15


def fetch_recap_title(sigungu_cd: str, bjdong_cd: str, plat_gb: str, bun: str, ji: str):
    """표제부(getBrTitleInfo) 조회 → 호수(hoCnt), 주용도(mainPurpsCdNm) 등 반환.
    실제 필드명은 '경희마크329' 표제부로 raw 확인 완료: bldNm(명칭), hoCnt(호수),
    mainPurpsCdNm(주용도, '생활숙박시설' 포함 여부로 판별), useAprDay(사용승인일)."""
    params = {
        "serviceKey": BLD_SERVICE_KEY,
        "sigunguCd": sigungu_cd,
        "bjdongCd": bjdong_cd,
        "platGbCd": plat_gb,
        "bun": bun.zfill(4),
        "ji": ji.zfill(4),
        "numOfRows": 5,
        "pageNo": 1,
    }
    resp = requests.get(BLD_TITLE_URL, params=params, timeout=15)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    items = root.findall(".//item")
    if not items:
        return None
    row = {child.tag: (child.text or "").strip() for child in items[0]}
    ho_cnt = int(row.get("hoCnt", 0) or 0)
    return ho_cnt, row


def parse_jibun_simple(jibun: str):
    plat_gb = "1" if jibun.startswith("산") else "0"
    jibun = jibun.replace("산", "").strip()
    if "-" in jibun:
        bun, ji = jibun.split("-", 1)
    else:
        bun, ji = jibun, "0"
    return plat_gb, bun or "0", ji or "0"


def verify(csv_path: str, min_units: int):
    """
    min_units는 더 이상 등록 여부를 가르는 '필터'가 아니라, 참고용 로그 표시 기준일 뿐이다.
    등록 여부는 오직 "건축HUB 표제부가 실제로 존재하고, 주용도에 '생활숙박시설'이 포함되는가"로 정해진다.
    (표제부가 없으면 → 애초에 집합건축물이 아니라 일반건축물로 등록된 것 → 정당한 제외)
    """
    df = pd.read_csv(csv_path)
    df = df[df["unit_est"].isna()]  # 호수 정보 자체가 없던 건만 재검증
    print(f"재검증 대상: {len(df)}건")

    bjdong_map = BjdongMap(BJDONG_CODE_CSV)
    conn = get_conn()
    cur = conn.cursor()

    results = []
    rescued = 0

    for _, row in df.iterrows():
        road_address = row["road_address"]
        building_name = row["building_name"]
        try:
            juso = road_to_jibun(road_address)
            if not juso:
                results.append({**row, "status": "주소변환실패", "confirmed_units": None})
                continue

            si_do, sgg_nm, umd_nm = juso.get("siNm", ""), juso.get("sggNm", ""), juso.get("emdNm", "")
            bun, ji = juso.get("lnbrMnnm", "0"), juso.get("lnbrSlno", "0")
            jibun_str = f"{bun}-{ji}" if ji not in ("0", "", None) else bun

            sgg_cd = bjdong_map.find_sgg_cd(si_do, sgg_nm)
            bjdong_cd = bjdong_map.find_bjdong_cd(sgg_cd, umd_nm) if sgg_cd else None
            if not (sgg_cd and bjdong_cd):
                results.append({**row, "status": "법정동코드매칭실패", "confirmed_units": None})
                continue

            plat_gb, bun2, ji2 = parse_jibun_simple(jibun_str)
            recap = fetch_recap_title(sgg_cd, bjdong_cd, plat_gb, bun2, ji2)
            time.sleep(REQUEST_SLEEP)

            if not recap:
                # 표제부 자체가 없음 = 집합건축물대장이 아예 없는 건물 = 일반건축물로 등록된 것 → 정당한 제외
                results.append({**row, "status": "제외확정(집합건축물대장없음)", "confirmed_units": None})
                continue

            confirmed_units, raw = recap
            main_purps = raw.get("mainPurpsCdNm", "")  # 실제 필드명은 raw 응답으로 재확인 필요
            is_livingstay = "생활숙박시설" in main_purps

            if is_livingstay:
                cur.execute("""
                    INSERT INTO master_buildings (building_name, road_address, sgg_text, sgg_cd, umd_nm, jibun, units)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (building_name, road_address, f"{si_do} {sgg_nm}", sgg_cd, umd_nm, jibun_str, confirmed_units))
                rescued += 1
                results.append({**row, "status": "구제됨(생활숙박시설 확인)", "confirmed_units": confirmed_units})
            else:
                # 집합건축물은 맞지만 주용도가 생활숙박시설이 아님 (호텔/오피스텔 등) → 제외
                results.append({**row, "status": f"제외(주용도불일치:{main_purps})", "confirmed_units": confirmed_units})

        except Exception as e:
            results.append({**row, "status": f"오류:{e}", "confirmed_units": None})

    conn.commit()
    cur.close()
    conn.close()

    pd.DataFrame(results).to_csv("verify_result.csv", index=False, encoding="utf-8-sig")
    print(f"검증 완료 — 구제(재등록): {rescued}건 / 결과 저장: verify_result.csv")
    print("※ 이번부터는 호실 수와 무관하게 '생활숙박시설 용도 확인' 여부만으로 등록합니다.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path", help="load_master.py가 생성한 excluded_small_buildings.csv")
    parser.add_argument("--min-units", type=int, default=0,
                         help="더 이상 등록 기준(필터)이 아님 — 참고용. 등록 여부는 '생활숙박시설 용도 확인'만으로 결정됨")
    args = parser.parse_args()
    verify(args.csv_path, args.min_units)
