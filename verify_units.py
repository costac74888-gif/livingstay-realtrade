# -*- coding: utf-8 -*-
"""
verify_units.py — 마스터파일에서 "호수 미확인"으로 제외됐던 건물들을
                   건축HUB 건축물대장 표제부(getBrTitleInfo)로 실제 호수를 조회해
                   재확인한다.

왜 필요한가
------------------------------------------------------------
load_master.py가 30실 미만/미확인 건물을 excluded_small_buildings.csv 로 빼두는데,
그 중 "호수 정보 없음(엑셀 미기재)" 건은 실제로는 대형 건물인데 입력만 누락됐을
가능성이 있다. 이 스크립트는 그런 건들을 국토부 공식 데이터로 재확인해서
잘못 제외된 건물을 구제한다.

중요 — 실제 API 응답으로 검증한 사실
------------------------------------------------------------
* 생활숙박시설(집합) 호실수는 표제부(getBrTitleInfo) 응답의 **hoCnt(호수)** 에 들어있다.
  hhldCnt(세대수)·fmlyCnt(가구수)는 생숙에선 항상 0 이다.
* 단일 집합건물은 "총괄표제부(getBrRecapTitleInfo)"가 아니라 "표제부(getBrTitleInfo)"에
  등록돼 있다. (총괄표제부로 조회하면 totalCount=0 으로 안 잡힌다.)
* 한 지번에 여러 동이 있으면 표제부가 여러 건 반환되므로, mainPurpsCdNm 이 '숙박시설'
  인 동을 우선 선택하고 그중 hoCnt 최댓값을 취한다.
* 시군구코드/법정동코드는 JUSO 건물관리번호(bdMgtSn) 앞 10자리에서 뽑는다.
  → 별도의 법정동코드 CSV 가 필요 없다.

흐름
------------------------------------------------------------
excluded_small_buildings.csv 의 도로명주소
  → juso.go.kr 로 지번/건물관리번호 확보 (address_utils.road_to_jibun)
  → bdMgtSn 에서 sigunguCd/bjdongCd 추출
  → 건축HUB 표제부 조회(getBrTitleInfo) 로 공식 호수(hoCnt) 확인
  → 30실 이상이면 master_buildings 에 INSERT (재등록)
  → 결과를 verify_result.csv 로 남김 (재등록 여부, 확인된 호수)

사용법
------------------------------------------------------------
python verify_units.py excluded_small_buildings.csv --min-units 30
"""

import argparse
import os
import re
import time
from xml.etree import ElementTree as ET

import requests
import pandas as pd

from db import get_conn
from address_utils import road_to_jibun

BLD_SERVICE_KEY = os.environ.get("BLD_SERVICE_KEY", "")
BLD_TITLE_URL = "https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo"

REQUEST_SLEEP = 0.15


def codes_from_juso(juso: dict):
    """JUSO 응답에서 표제부 조회에 필요한 코드들을 뽑는다.
    건물관리번호(bdMgtSn) 앞 10자리 = 법정동코드 = 시군구코드(5) + 법정동코드(5)."""
    bdmgt = (juso.get("bdMgtSn") or "").strip()
    if len(bdmgt) < 10:
        return None
    sigungu_cd = bdmgt[:5]
    bjdong_cd = bdmgt[5:10]
    plat_gb = "1" if str(juso.get("mtYn", "0")) == "1" else "0"
    bun = re.sub(r"[^0-9]", "", str(juso.get("lnbrMnnm", "0"))) or "0"
    ji = re.sub(r"[^0-9]", "", str(juso.get("lnbrSlno", "0"))) or "0"
    return sigungu_cd, bjdong_cd, plat_gb, bun, ji


def fetch_title_hocnt(sigungu_cd, bjdong_cd, plat_gb, bun, ji, bld_nm=""):
    """표제부 조회 → (호수, 매칭된 raw row) 반환.
    여러 동이 잡히면 '숙박시설' 용도를 우선하고 그중 hoCnt 최댓값을 취한다."""
    params = {
        "serviceKey": BLD_SERVICE_KEY,
        "sigunguCd": sigungu_cd,
        "bjdongCd": bjdong_cd,
        "platGbCd": plat_gb,
        "bun": bun.zfill(4),
        "ji": ji.zfill(4),
        "numOfRows": 50,
        "pageNo": 1,
    }
    resp = requests.get(BLD_TITLE_URL, params=params, timeout=15)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    items = root.findall(".//item")
    if not items:
        return None

    rows = [{c.tag: (c.text or "").strip() for c in it} for it in items]

    def hoc(r):
        try:
            return int(r.get("hoCnt", "0") or 0)
        except ValueError:
            return 0

    # 숙박시설 용도 우선
    lodging = [r for r in rows if "숙박" in (r.get("mainPurpsCdNm", "") or "")]
    pool = lodging if lodging else rows
    best = max(pool, key=hoc)
    return hoc(best), best


def verify(csv_path: str, min_units: int):
    df = pd.read_csv(csv_path)
    df = df[df["unit_est"].isna()]  # 호수 정보 자체가 없던 건만 재검증
    print(f"재검증 대상(호수 미기재): {len(df)}건")

    conn = get_conn()
    cur = conn.cursor()

    results = []
    rescued = 0

    for _, row in df.iterrows():
        road_address = row["road_address"]
        building_name = row["building_name"]
        try:
            juso = road_to_jibun(road_address)
            time.sleep(REQUEST_SLEEP)
            if not juso:
                results.append({"road_address": road_address, "building_name": building_name,
                                "status": "주소변환실패", "confirmed_units": None})
                continue

            codes = codes_from_juso(juso)
            if not codes:
                results.append({"road_address": road_address, "building_name": building_name,
                                "status": "건물관리번호없음", "confirmed_units": None})
                continue

            sigungu_cd, bjdong_cd, plat_gb, bun, ji = codes
            si_do = juso.get("siNm", ""); sgg_nm = juso.get("sggNm", "")
            umd_nm = (juso.get("emdNm", "") + juso.get("liNm", "")).replace(" ", "")
            jibun_str = f"{bun}-{ji}" if ji not in ("0", "", None) else bun

            title = fetch_title_hocnt(sigungu_cd, bjdong_cd, plat_gb, bun, ji, building_name)
            time.sleep(REQUEST_SLEEP)
            if not title:
                results.append({"road_address": road_address, "building_name": building_name,
                                "status": "대장조회실패(정보없음)", "confirmed_units": None})
                continue

            confirmed_units, _raw = title
            if confirmed_units >= min_units:
                cur.execute(
                    """
                    INSERT INTO master_buildings
                        (building_name, road_address, sgg_text, sgg_cd, umd_nm, jibun, units)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (building_name, road_address, f"{si_do} {sgg_nm}".strip(),
                     sigungu_cd, umd_nm, jibun_str, confirmed_units),
                )
                rescued += 1
                results.append({"road_address": road_address, "building_name": building_name,
                                "status": "구제됨(재등록)", "confirmed_units": confirmed_units})
            else:
                results.append({"road_address": road_address, "building_name": building_name,
                                "status": "제외확정", "confirmed_units": confirmed_units})

        except Exception as e:
            results.append({"road_address": road_address, "building_name": building_name,
                            "status": f"오류:{e}", "confirmed_units": None})

    conn.commit()
    cur.close()
    conn.close()

    pd.DataFrame(results).to_csv("verify_result.csv", index=False, encoding="utf-8-sig")
    print(f"검증 완료 — 구제(재등록): {rescued}건 / 결과 저장: verify_result.csv")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path", help="load_master.py가 생성한 excluded_small_buildings.csv")
    parser.add_argument("--min-units", type=int, default=30)
    args = parser.parse_args()
    verify(args.csv_path, args.min_units)
