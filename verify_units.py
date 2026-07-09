# -*- coding: utf-8 -*-
"""
verify_units.py — 마스터파일에서 "호수 미확인"으로 제외됐던 건물들을
                   건축HUB 건축물대장 표제부(getBrTitleInfo)로 실제 호수를 조회해
                   재확인한다.

왜 필요한가
------------------------------------------------------------
load_master.py가 "호수 미확인(엑셀 미기재)" 건물을 excluded_small_buildings.csv 로
빼두는데, 그 중 상당수는 실제로는 정상적인 집합 생활숙박시설인데 입력만 누락된
경우다. 이 스크립트는 그런 건들을 국토부 공식 건축물대장으로 재확인해서 잘못 제외된
생숙을 구제한다.

판정 기준 — 30실 게이트 폐기
------------------------------------------------------------
과거에는 표제부 호수(hoCnt) 30실 이상만 구제했으나, 이 기준은 소형 집합 생숙
(4~15실 풀빌라형 등)을 대거 잘못 제외했다. 이제는 **크기와 무관하게 '집합 생활숙박
시설'이면 구제**한다. 생숙 판정 자체는 building_registry.is_living_stay 가 담당한다:
표제부에 '생활숙박' 표기가 있으면 통과, 없으면 층별개요(getBrFlrOulnInfo)까지 확인.
호수(hoCnt)는 게이트가 아니라 정보용으로만 저장한다.

흐름
------------------------------------------------------------
excluded_small_buildings.csv 의 도로명주소
  → juso.go.kr 로 지번/건물관리번호 확보 (address_utils.road_to_jibun)
  → bdMgtSn 에서 sigunguCd/bjdongCd 추출
  → building_registry.fetch_building_title / is_living_stay 로 집합 생숙 여부 확인
  → 집합 생숙이면 master_buildings 에 INSERT (재등록)
  → 결과를 verify_result.csv 로 남김 (재등록 여부, 확인된 호수)

사용법
------------------------------------------------------------
python verify_units.py excluded_small_buildings.csv
python verify_units.py excluded_small_buildings.csv --offset 0 --limit 50
"""

import argparse
import re
import time

import pandas as pd

from db import get_conn
from address_utils import road_to_jibun
from building_registry import is_living_stay

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


def verify(csv_path: str, offset: int = 0, limit: int | None = None):
    df = pd.read_csv(csv_path)
    df = df[df["unit_est"].isna()].reset_index(drop=True)  # 호수 정보 자체가 없던 건만 재검증
    total = len(df)
    df = df.iloc[offset:offset + limit] if limit is not None else df.iloc[offset:]
    end = offset + len(df)
    print(f"재검증 대상(호수 미기재): 전체 {total}건 중 [{offset}:{end}] = {len(df)}건 처리")

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

            # 30실 게이트 폐기 → 크기와 무관하게 '집합 생활숙박시설'이면 구제한다.
            # 표제부만으로는 생숙/일반호텔 구분이 안 되므로(휴스테이 등) 층별개요까지 확인.
            # is_living_stay가 표제부를 내부에서 조회하므로 별도 fetch_building_title 불필요.
            verdict, title, reason = is_living_stay(sigungu_cd, bjdong_cd, plat_gb, bun, ji)
            if verdict is None:
                status = "대장조회실패(정보없음)" if title is None else "층별개요조회실패(재시도)"
                results.append({"road_address": road_address, "building_name": building_name,
                                "status": status, "confirmed_units": None})
                continue

            confirmed_units = title["ho_cnt"]  # 호수는 정보용으로만 저장 (게이트 아님)

            if verdict is False:
                results.append({"road_address": road_address, "building_name": building_name,
                                "status": "제외확정(생숙아님)", "confirmed_units": confirmed_units})
                continue

            # 재실행 시 중복 등록 방지
            cur.execute(
                "SELECT 1 FROM master_buildings WHERE road_address=%s AND building_name=%s",
                (road_address, building_name),
            )
            if cur.fetchone():
                results.append({"road_address": road_address, "building_name": building_name,
                                "status": "이미등록됨", "confirmed_units": confirmed_units})
            else:
                # verdict True = 생숙 확정(위에서 None/False는 이미 continue)
                # → lodging_type='생활'로 태깅해 기본 '생숙만' 필터에서 숨지 않게 한다.
                cur.execute(
                    """
                    INSERT INTO master_buildings
                        (building_name, road_address, sgg_text, sgg_cd, umd_nm, jibun, units, source, lodging_type)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 'verify_rescued', '생활')
                    """,
                    (building_name, road_address, f"{si_do} {sgg_nm}".strip(),
                     sigungu_cd, umd_nm, jibun_str, confirmed_units),
                )
                conn.commit()  # 청크 도중 강제종료돼도 구제분 보존 (증분 커밋)
                rescued += 1
                results.append({"road_address": road_address, "building_name": building_name,
                                "status": "구제됨(생숙확인)", "confirmed_units": confirmed_units})

        except Exception as e:
            results.append({"road_address": road_address, "building_name": building_name,
                            "status": f"오류:{e}", "confirmed_units": None})

    conn.commit()
    cur.close()
    conn.close()

    out = f"verify_result_{offset}_{end}.csv"
    pd.DataFrame(results).to_csv(out, index=False, encoding="utf-8-sig")
    print(f"검증 완료 — 구제(재등록): {rescued}건 / 결과 저장: {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path", help="load_master.py가 생성한 excluded_small_buildings.csv")
    parser.add_argument("--offset", type=int, default=0, help="재검증 대상 목록에서 시작 인덱스")
    parser.add_argument("--limit", type=int, default=None, help="이번 실행에서 처리할 건수 (청크 크기)")
    args = parser.parse_args()
    verify(args.csv_path, offset=args.offset, limit=args.limit)
