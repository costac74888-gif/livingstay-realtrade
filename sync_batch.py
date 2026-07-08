# -*- coding: utf-8 -*-
"""
sync_batch.py — 매일/매주 스케줄러가 실행하는 배치 작업 본체

실행 흐름
------------------------------------------------------------
STEP 0. (최초 1회 또는 마스터파일 갱신 시) load_master.py 로 마스터 적재
STEP 1. prepare_master_addresses()
        마스터파일의 도로명주소 → 지번주소 변환 → sgg_cd/umd_nm/jibun 채우기
        (이미 채워진 행은 재호출하지 않음 → API 절약)
STEP 2. sync_transactions()
        마스터에 있는 시군구(57개)만 대상으로 RTMS 상업업무용 매매 조회
        유형='집합'만 필터 → 마스터와 법정동+지번 매칭 → 매칭 실패시 건축HUB 표제부 보완
        transactions 테이블에 중복 없이 적재

실행
------------------------------------------------------------
python sync_batch.py                # 최근 3개월 갱신 (기본, 매일 실행에 적합)
python sync_batch.py --months 36    # 최근 36개월 백필 (최초 1회 대량 적재용)
"""

import argparse
import os
import time
from datetime import datetime
from xml.etree import ElementTree as ET

import requests

from db import get_conn, init_db
from address_utils import road_to_jibun, BjdongMap, parse_jibun

# ------------------------------------------------------------------
# 설정값 — API 키는 Replit Secrets(환경변수)에서 읽음
# ------------------------------------------------------------------
RTMS_SERVICE_KEY = os.environ.get("RTMS_SERVICE_KEY", "")
BLD_SERVICE_KEY = os.environ.get("BLD_SERVICE_KEY", "")
BJDONG_CODE_CSV = os.environ.get("BJDONG_CODE_CSV", "법정동코드 전체자료.csv")   # code.go.kr 다운로드 파일 경로

RTMS_URL = "https://apis.data.go.kr/1613000/RTMSDataSvcNrgTrade/getRTMSDataSvcNrgTrade"
BLD_TITLE_URL = "https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo"

REQUEST_SLEEP = 0.15  # 공공데이터 API 과호출 방지용 딜레이(초)


# ------------------------------------------------------------------
# 매칭키 정규화 — RTMS umdNm은 면/리 지역에서 '설악면 방일리'처럼 공백이 있으므로
# 마스터/실거래 양쪽 모두 공백을 제거해 비교한다.
# ------------------------------------------------------------------
def _norm_umd(s: str) -> str:
    return (s or "").replace(" ", "")


# ------------------------------------------------------------------
# STEP 1. 마스터파일 주소 보강 (도로명 → 지번/시군구코드)
#   * JUSO 행정동코드(admCd) 앞 5자리 = 시군구코드(=RTMS sggCd) → 법정동코드 CSV 불필요.
#   * umd_nm 은 emdNm+liNm 을 공백제거해 저장(면/리 지역 매칭률 향상).
# ------------------------------------------------------------------
def prepare_master_addresses(region_kw: str | None = None):
    conn = get_conn()
    cur = conn.cursor()
    if region_kw:
        cur.execute(
            "SELECT id, road_address, sgg_text FROM master_buildings "
            "WHERE jibun IS NULL AND road_address LIKE %s",
            (f"%{region_kw}%",),
        )
    else:
        cur.execute("SELECT id, road_address, sgg_text FROM master_buildings WHERE jibun IS NULL")
    targets = cur.fetchall()
    print(f"[STEP1] 주소 변환 대상 {len(targets)}건" + (f" (지역='{region_kw}')" if region_kw else ""))

    updated = 0
    for row in targets:
        try:
            juso = road_to_jibun(row["road_address"])
            if not juso:
                continue
            si_do = juso.get("siNm", "")
            sgg_nm = juso.get("sggNm", "")
            sgg_cd = (juso.get("admCd", "") or "")[:5] or None
            umd_nm = _norm_umd(juso.get("emdNm", "") + juso.get("liNm", ""))
            bun = juso.get("lnbrMnnm", "0")
            ji = juso.get("lnbrSlno", "0")
            jibun_str = f"{bun}-{ji}" if ji not in ("0", "", None) else bun

            if not sgg_cd:
                continue

            cur.execute("""
                UPDATE master_buildings
                SET jibun_address = %s, sgg_cd = %s, umd_nm = %s, jibun = %s
                WHERE id = %s
            """, (f"{si_do} {sgg_nm} {umd_nm} {jibun_str}", sgg_cd, umd_nm, jibun_str, row["id"]))
            updated += 1
        except Exception as e:
            print(f"  주소변환 실패 (id={row['id']}): {e}")
        time.sleep(REQUEST_SLEEP)

    conn.commit()
    cur.close()
    conn.close()
    print(f"[STEP1] 주소 보강 완료: {updated}/{len(targets)}건")


# ------------------------------------------------------------------
# STEP 2. RTMS 수집 + 매칭 + 적재
# ------------------------------------------------------------------
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

    # 실제 RTMS(NrgTrade) 응답을 raw로 확인한 결과:
    #  - 유형 필드는 buildingType 이며 값은 '일반' / '집합' → 생숙은 집합건물이므로 '집합'.
    #  - 용도 필드는 buildingUse 이며 값 예: 판매/제1종근린생활/제2종근린생활/기타/숙박 → 생숙은 '숙박'.
    # 1차: buildingType == '집합', 2차: buildingUse에 '숙박' 포함.
    # buildingUse 필드가 비어있는 응답 케이스는 일단 통과시켜(매칭 단계에서 걸러짐)
    # 필드 누락 때문에 데이터가 전부 사라지는 사고를 방지한다.
    def _is_saengsuk(r):
        if r.get("buildingType", "") != "집합":
            return False
        use = r.get("buildingUse", "")
        return (not use) or ("숙박" in use)

    return [r for r in items if _is_saengsuk(r)]


def fetch_building_name_fallback(sigungu_cd: str, bjdong_cd: str, plat_gb: str, bun: str, ji: str):
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
    return row.get("bldNm") or None


def sync_transactions(months: int, bjdong=None, sgg_filter=None):
    conn = get_conn()
    cur = conn.cursor()

    # 마스터에 존재하는 (매칭 준비 완료된) 시군구만 대상으로
    cur.execute("SELECT DISTINCT sgg_cd FROM master_buildings WHERE sgg_cd IS NOT NULL")
    sgg_list = [r["sgg_cd"] for r in cur.fetchall()]
    if sgg_filter:
        sgg_list = [s for s in sgg_list if s in sgg_filter]
    print(f"[STEP2] 배치 대상 시군구 {len(sgg_list)}개, 최근 {months}개월"
          + (f" (sgg 한정: {sorted(sgg_filter)})" if sgg_filter else ""))

    deal_ymds = []
    today = datetime.today()
    y, m = today.year, today.month
    for _ in range(months):
        deal_ymds.append(f"{y}{m:02d}")
        m -= 1
        if m == 0:
            m = 12
            y -= 1

    inserted = matched_master = matched_bld = unmatched = 0

    for sgg_cd in sgg_list:
        for deal_ymd in deal_ymds:
            try:
                trades = fetch_nrg_trade(sgg_cd, deal_ymd)
            except Exception as e:
                print(f"  RTMS 조회 실패 ({sgg_cd}, {deal_ymd}): {e}")
                continue
            time.sleep(REQUEST_SLEEP)

            for t in trades:
                umd_nm = t.get("umdNm", "")
                jibun = t.get("jibun", "")
                if not umd_nm or not jibun:
                    continue
                umd_key = _norm_umd(umd_nm)  # 마스터 umd_nm(공백제거)과 맞추기 위한 매칭키

                deal_date = f"{t.get('dealYear','')}-{t.get('dealMonth','').zfill(2)}-{t.get('dealDay','').zfill(2)}"
                price = t.get("dealAmount", "0").replace(",", "")
                area = t.get("buildingAr", t.get("totalFloorAr", "0"))
                deal_type = t.get("dealingGbn", "")
                raw_key = f"{sgg_cd}|{umd_key}|{jibun}|{deal_date}|{price}"

                # 1) 마스터파일과 매칭 시도 (건물명 확정)
                cur.execute("""
                    SELECT building_name, sgg_text FROM master_buildings
                    WHERE sgg_cd=%s AND umd_nm=%s AND jibun=%s
                """, (sgg_cd, umd_key, jibun))
                m_row = cur.fetchone()

                building_name = None
                match_source = "unmatched"
                si_do_val, sgg_nm_val = None, None  # 시/군구 계층 검색용

                if m_row:
                    building_name = m_row["building_name"]
                    match_source = "master"
                    matched_master += 1
                    if m_row["sgg_text"]:
                        parts = m_row["sgg_text"].split(" ", 1)
                        si_do_val = parts[0] if len(parts) > 0 else None
                        sgg_nm_val = parts[1] if len(parts) > 1 else None
                elif bjdong is None:
                    # 법정동코드 CSV 미제공 → 건축HUB 보완 생략, 미매칭으로 처리
                    unmatched += 1
                    continue
                else:
                    # 2) 매칭 실패 → 건축HUB 표제부로 보완 (신규 준공 등 마스터에 없는 건물)
                    bjdong_cd = bjdong.find_bjdong_cd(sgg_cd, umd_nm)
                    if bjdong_cd:
                        plat_gb, bun, ji = parse_jibun(jibun)
                        try:
                            building_name = fetch_building_name_fallback(sgg_cd, bjdong_cd, plat_gb, bun, ji)
                            time.sleep(REQUEST_SLEEP)
                        except Exception:
                            building_name = None
                    if building_name:
                        match_source = "buildinghub"
                        matched_bld += 1
                    else:
                        unmatched += 1
                        continue  # 건물명 특정 안 되는 건 게시판에서 제외 (원하면 저장은 하되 표시만 숨겨도 됨)

                try:
                    cur.execute("""
                        INSERT INTO transactions
                        (building_name, address, si_do, sgg_nm, area, price, deal_date, deal_type,
                         floor, sgg_cd, umd_nm, jibun, match_source, raw_key)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (raw_key) DO NOTHING
                    """, (building_name, f"{umd_nm} {jibun}", si_do_val, sgg_nm_val,
                          float(area or 0), int(price or 0),
                          deal_date, deal_type, (t.get("floor") or "").strip(),
                          sgg_cd, umd_nm, jibun, match_source, raw_key))
                    if cur.rowcount:
                        inserted += 1
                except Exception as e:
                    print(f"  적재 실패: {e}")

    conn.commit()

    cur.execute("""
        INSERT INTO sync_log (started_at, finished_at, regions_processed, rows_inserted,
                               rows_matched_master, rows_matched_buildinghub, rows_unmatched, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (datetime.now(), datetime.now(), len(sgg_list), inserted,
          matched_master, matched_bld, unmatched, "success"))
    conn.commit()
    cur.close()
    conn.close()

    print(f"[STEP2] 완료 — 신규 {inserted}건 (마스터매칭 {matched_master} / 건축HUB보완 {matched_bld} / 미매칭제외 {unmatched})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--months", type=int, default=3, help="최근 N개월 수집 (기본 3, 최초 백필 시 --months 36 권장)")
    parser.add_argument("--region", default=None, help="STEP1 주소보강을 특정 지역(도로명주소 키워드)만 수행 (예: 서귀포시)")
    parser.add_argument("--sgg", default=None, help="STEP2를 특정 시군구코드만 수행, 콤마구분 (예: 50130,41220)")
    args = parser.parse_args()

    init_db()

    # 법정동코드 CSV는 '건축HUB 보완'(마스터에 없는 신축 건물명 확정)에만 필요.
    # 파일이 없으면 마스터 매칭만 수행한다 (JUSO admCd로 시군구코드를 얻으므로 CSV 없이도 동작).
    bjdong_map = None
    if os.path.exists(BJDONG_CODE_CSV):
        bjdong_map = BjdongMap(BJDONG_CODE_CSV)
        print(f"[SETUP] 법정동코드 CSV 로드 → 건축HUB 보완 활성화 ({BJDONG_CODE_CSV})")
    else:
        print("[SETUP] 법정동코드 CSV 없음 → 마스터 매칭만 수행(건축HUB 보완 생략)")

    sgg_filter = set(s.strip() for s in args.sgg.split(",")) if args.sgg else None

    prepare_master_addresses(region_kw=args.region)
    sync_transactions(months=args.months, bjdong=bjdong_map, sgg_filter=sgg_filter)
