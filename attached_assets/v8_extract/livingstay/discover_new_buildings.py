# -*- coding: utf-8 -*-
"""
discover_new_buildings.py — 마스터파일에 없는 지역까지 포함해 "전국"에서
                             생활형숙박시설(집합건물)을 스스로 찾아 마스터에 등록하는 배치.

sync_batch.py와의 역할 차이
------------------------------------------------------------
sync_batch.py       : 마스터에 "이미 있는" 건물의 최신 실거래만 갱신 (빠름, 매일 실행)
discover_new_buildings.py : 마스터에 "아직 없는" 지역까지 전국을 훑어서 신규 생숙을 찾아냄
                            (느림, API 호출량 큼, 월 1회 정도 권장)

등록 기준 (중요 — 호실 수는 필터가 아니라 정보용)
------------------------------------------------------------
① RTMS 상업업무용 매매 조회 → buildingType=='집합' AND buildingUse=='숙박'
② 그 지번으로 건축HUB 표제부(getBrTitleInfo) 조회
③ 응답의 주용도(mainPurpsCdNm)에 '생활숙박시설' 문자열이 포함되는가?
   → 포함 O: 등록 (호텔/콘도가 아니라 생숙임이 문서로 확인됨)
   → 포함 X: 제외 (관광숙박시설=호텔 등, 집합+숙박이어도 생숙이 아닐 수 있음)
   호실 수(hoCnt)는 등록 여부와 무관하게 항상 같이 저장 — 참고 정보일 뿐

실행 환경 특성 반영 (장시간 실행이 끊기는 문제 대응)
------------------------------------------------------------
- 시군구 목록을 --region-offset/--region-limit로 잘라서 여러 번 나눠 실행
- 성공 건마다 즉시 commit (중간에 죽어도 그동안 처리분은 보존)
- 이미 처리한 (시군구, 계약월) 조합은 progress 테이블에 기록해 재실행 시 건너뜀

사용법
------------------------------------------------------------
# 1회차: 처음 30개 시군구, 최근 3개월
python discover_new_buildings.py --region-offset 0 --region-limit 30 --months 3

# 2회차: 다음 30개
python discover_new_buildings.py --region-offset 30 --region-limit 30 --months 3

# 전체 시군구 개수 확인만
python discover_new_buildings.py --list-only
"""

import os
import argparse
import time
from datetime import datetime
from xml.etree import ElementTree as ET

import requests

from db import get_conn, init_db
from address_utils import road_to_jibun, BjdongMap, parse_jibun

RTMS_SERVICE_KEY = os.environ["RTMS_SERVICE_KEY"]
BLD_SERVICE_KEY = os.environ["BLD_SERVICE_KEY"]
BJDONG_CODE_CSV = os.environ.get("BJDONG_CODE_CSV", "법정동코드 전체자료.csv")

RTMS_URL = "https://apis.data.go.kr/1613000/RTMSDataSvcNrgTrade/getRTMSDataSvcNrgTrade"
BLD_TITLE_URL = "https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo"

REQUEST_SLEEP = 0.15


def init_progress_table():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS discover_progress (
            sgg_cd TEXT,
            deal_ymd TEXT,
            processed_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (sgg_cd, deal_ymd)
        )
    """)
    conn.commit()
    cur.close()
    conn.close()


def already_processed(sgg_cd: str, deal_ymd: str) -> bool:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM discover_progress WHERE sgg_cd=%s AND deal_ymd=%s", (sgg_cd, deal_ymd))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row is not None


def mark_processed(sgg_cd: str, deal_ymd: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO discover_progress (sgg_cd, deal_ymd) VALUES (%s, %s)
        ON CONFLICT (sgg_cd, deal_ymd) DO NOTHING
    """, (sgg_cd, deal_ymd))
    conn.commit()
    cur.close()
    conn.close()


def fetch_nrg_trade(sgg_cd: str, deal_ymd: str) -> list[dict]:
    params = {
        "serviceKey": RTMS_SERVICE_KEY,
        "LAWD_CD": sgg_cd,
        "DEAL_YMD": deal_ymd,
        "numOfRows": 999,
        "pageNo": 1,
    }
    resp = requests.get(RTMS_URL, params=params, timeout=15)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)

    items = []
    for item in root.iter("item"):
        row = {child.tag: (child.text or "").strip() for child in item}
        items.append(row)

    return [r for r in items if r.get("buildingType", "") == "집합" and r.get("buildingUse", "") == "숙박"]


def fetch_building_title(sigungu_cd: str, bjdong_cd: str, plat_gb: str, bun: str, ji: str):
    """표제부 조회 → (건물명, 호수, 주용도, 도로명주소) 반환. 없으면 None."""
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
    return {
        "bld_nm": row.get("bldNm", "").strip(),
        "ho_cnt": int(row.get("hoCnt", 0) or 0),
        "main_purps": row.get("mainPurpsCdNm", ""),
        "new_plat_plc": row.get("newPlatPlc", "").strip(),
        "plat_plc": row.get("platPlc", "").strip(),
    }


def already_in_master(cur, sgg_cd, umd_nm, jibun) -> bool:
    cur.execute("""
        SELECT 1 FROM master_buildings WHERE sgg_cd=%s AND umd_nm=%s AND jibun=%s
    """, (sgg_cd, umd_nm, jibun))
    return cur.fetchone() is not None


def discover(region_offset: int, region_limit: int, months: int, list_only: bool):
    init_db()
    init_progress_table()
    bjdong = BjdongMap(BJDONG_CODE_CSV)

    all_codes = bjdong.all_sgg_codes()
    print(f"전국 시군구 코드 총 {len(all_codes)}개")
    if list_only:
        return

    target_codes = all_codes[region_offset: region_offset + region_limit]
    print(f"이번 실행 대상: {len(target_codes)}개 (offset={region_offset})")

    deal_ymds = []
    today = datetime.today()
    y, m = today.year, today.month
    for _ in range(months):
        deal_ymds.append(f"{y}{m:02d}")
        m -= 1
        if m == 0:
            m = 12
            y -= 1

    conn = get_conn()
    cur = conn.cursor()

    new_buildings = 0
    new_transactions = 0
    checked = 0
    rejected_use = 0

    for sgg_cd in target_codes:
        for deal_ymd in deal_ymds:
            if already_processed(sgg_cd, deal_ymd):
                continue

            try:
                trades = fetch_nrg_trade(sgg_cd, deal_ymd)
            except Exception as e:
                print(f"  RTMS 조회 실패 ({sgg_cd}, {deal_ymd}): {e}")
                continue
            time.sleep(REQUEST_SLEEP)

            # sync_batch.py와 반드시 동일한 방식으로 순번을 매겨야, 나중에 sync_batch가
            # 같은 달을 다시 훑을 때 raw_key가 어긋나지 않고 정확히 이어진다.
            occurrence_counter = {}

            for t in trades:
                umd_nm = t.get("umdNm", "")
                jibun = t.get("jibun", "")
                if not umd_nm or not jibun:
                    continue

                deal_date = f"{t.get('dealYear','')}-{t.get('dealMonth','').zfill(2)}-{t.get('dealDay','').zfill(2)}"
                price = t.get("dealAmount", "0").replace(",", "")
                area = t.get("buildingAr", t.get("totalFloorAr", "0"))
                deal_type = t.get("dealingGbn", "")
                floor_val = (t.get("floor") or t.get("flrNo") or "").strip()

                base_key = f"{sgg_cd}|{umd_nm}|{jibun}|{deal_date}|{price}|{floor_val}"
                occurrence_counter[base_key] = occurrence_counter.get(base_key, 0) + 1
                raw_key = f"{base_key}|{occurrence_counter[base_key]}"

                checked += 1

                if already_in_master(cur, sgg_cd, umd_nm, jibun):
                    continue  # 이미 아는 건물 → sync_batch.py가 이 거래를 포함해 알아서 처리

                bjdong_cd = bjdong.find_bjdong_cd(sgg_cd, umd_nm)
                if not bjdong_cd:
                    continue

                plat_gb, bun, ji = parse_jibun(jibun)
                try:
                    title = fetch_building_title(sgg_cd, bjdong_cd, plat_gb, bun, ji)
                    time.sleep(REQUEST_SLEEP)
                except Exception as e:
                    print(f"  표제부 조회 실패: {e}")
                    continue

                if not title or not title["bld_nm"]:
                    continue

                if "생활숙박시설" not in title["main_purps"]:
                    rejected_use += 1
                    continue  # 집합+숙박이지만 호텔/콘도 등 → 생숙 아님

                sgg_text = bjdong.sgg_text(sgg_cd) or ""
                road_address = title["new_plat_plc"] or title["plat_plc"] or f"{sgg_text} {umd_nm} {jibun}"

                cur.execute("""
                    INSERT INTO master_buildings
                        (building_name, road_address, sgg_text, sgg_cd, umd_nm, jibun, units, source)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 'api_discovered')
                """, (title["bld_nm"], road_address, sgg_text, sgg_cd, umd_nm, jibun, title["ho_cnt"]))
                new_buildings += 1

                si_do_val, sgg_nm_val = (sgg_text.split(" ", 1) + [None])[:2] if sgg_text else (None, None)

                cur.execute("""
                    INSERT INTO transactions
                        (building_name, address, si_do, sgg_nm, area, price, deal_date, deal_type, floor,
                         sgg_cd, umd_nm, jibun, match_source, raw_key)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'api_discovered', %s)
                    ON CONFLICT (raw_key) DO NOTHING
                """, (title["bld_nm"], f"{umd_nm} {jibun}", si_do_val, sgg_nm_val,
                      float(area or 0), int(price or 0), deal_date, deal_type, floor_val,
                      sgg_cd, umd_nm, jibun, raw_key))
                if cur.rowcount:
                    new_transactions += 1

                conn.commit()  # 건별 즉시 커밋 — 중간에 죽어도 여기까지는 보존
                print(f"  신규 등록: {title['bld_nm']} ({sgg_text} {umd_nm} {jibun}) — {title['ho_cnt']}실")

            mark_processed(sgg_cd, deal_ymd)

    conn.commit()
    cur.close()
    conn.close()

    print(f"\n완료 — 검사한 거래 {checked}건 / 신규 건물 {new_buildings}건 / 신규 거래 {new_transactions}건 "
          f"/ 용도불일치 제외 {rejected_use}건")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--region-offset", type=int, default=0)
    parser.add_argument("--region-limit", type=int, default=20, help="한 번에 처리할 시군구 개수")
    parser.add_argument("--months", type=int, default=3)
    parser.add_argument("--list-only", action="store_true", help="전국 시군구 개수만 확인하고 종료")
    args = parser.parse_args()

    discover(args.region_offset, args.region_limit, args.months, args.list_only)
