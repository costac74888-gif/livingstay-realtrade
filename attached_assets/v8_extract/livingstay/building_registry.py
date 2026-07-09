# -*- coding: utf-8 -*-
"""
building_registry.py — "이 건물이 진짜 생활숙박시설인가"를 판별하는 로직을 한 곳에 모은 공용 모듈.

배경
------------------------------------------------------------
건축HUB 표제부(getBrTitleInfo)의 주용도/기타용도 필드는 건물마다 표기가 들쭉날쭉하다.
- 어떤 건물(경희마크329)은 "숙박시설(생활숙박시설)"처럼 친절하게 괄호로 표기
- 어떤 건물(휘닉스파크레드앤핑크콘도미니엄)은 그냥 "숙박시설"(주용도)뿐이고,
  실제로는 "휴양콘도미니엄"(층별 용도)이라 생숙이 아님
- 어떤 건물(휴스테이 등)은 표제부엔 표기가 없지만 층별개요엔 "생활숙박시설"로 명확히 나옴

그래서 표제부 하나만 보고 판정하면 안 되고, 아래 순서로 확인해야 정확하다.
  1) 표제부 주용도/기타용도에 "생활숙박시설"이 있으면 즉시 확정 (API 호출 절약)
  2) 없으면 층별개요(getBrFlrOulnInfo)를 추가 조회해서, 각 층 용도에
     "생활숙박시설"이 하나라도 있는지 확인
  3) 층별개요에도 없으면(예: "휴양콘도미니엄"만 있음) → 생숙 아님으로 최종 판정

discover_new_buildings.py, verify_units.py, sync_batch.py 전부 반드시 이 모듈의
함수만 사용해야 한다 — 각 파일에 판정 로직을 따로 구현하면 이번처럼 한쪽만
고쳐지고 한쪽은 옛 기준(30실 게이트, 검증 없는 통과 등)으로 남는 문제가 반복된다.
"""

import os
import time
from xml.etree import ElementTree as ET

import requests

BLD_SERVICE_KEY = os.environ["BLD_SERVICE_KEY"]
BLD_TITLE_URL = "https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo"
BLD_FLOOR_URL = "https://apis.data.go.kr/1613000/BldRgstHubService/getBrFlrOulnInfo"

REQUEST_SLEEP = 0.15
LIVINGSTAY_KEYWORD = "생활숙박시설"


def fetch_building_title(sigungu_cd: str, bjdong_cd: str, plat_gb: str, bun: str, ji: str):
    """표제부(getBrTitleInfo) 조회 → dict 또는 None (결과 없음)"""
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
        "etc_purps": row.get("etcPurps", ""),
        "new_plat_plc": row.get("newPlatPlc", "").strip(),
        "plat_plc": row.get("platPlc", "").strip(),
    }


def fetch_floor_outline(sigungu_cd: str, bjdong_cd: str, plat_gb: str, bun: str, ji: str):
    """층별개요(getBrFlrOulnInfo) 조회 → 각 층의 주용도/상세용도 리스트. 실패 시 None(조회실패, '없음'과 구분)."""
    params = {
        "serviceKey": BLD_SERVICE_KEY,
        "sigunguCd": sigungu_cd,
        "bjdongCd": bjdong_cd,
        "platGbCd": plat_gb,
        "bun": bun.zfill(4),
        "ji": ji.zfill(4),
        "numOfRows": 100,
        "pageNo": 1,
    }
    try:
        resp = requests.get(BLD_FLOOR_URL, params=params, timeout=15)
        resp.raise_for_status()
    except Exception:
        return None  # 조회 자체 실패 — "생숙 아님"과 구분해서 나중에 재시도 가능하게 함

    root = ET.fromstring(resp.content)
    items = root.findall(".//item")
    floors = []
    for item in items:
        row = {child.tag: (child.text or "").strip() for child in item}
        floors.append({
            "flr_gb_nm": row.get("flrGbCdNm", ""),
            "flr_no_nm": row.get("flrNoNm", ""),
            "main_purps": row.get("mainPurpsCdNm", ""),
            "etc_purps": row.get("etcPurps", ""),
        })
    return floors


def is_living_stay(sigungu_cd: str, bjdong_cd: str, plat_gb: str, bun: str, ji: str):
    """
    이 지번의 건물이 생활숙박시설인지 최종 판정한다.

    반환값: (판정결과: True/False/None, 건물정보 dict 또는 None, 판정근거 문자열)
      - True  : 생활숙박시설로 확인됨 (표제부 또는 층별개요에서 확인)
      - False : 확인 결과 생활숙박시설이 아님 (예: 휴양콘도미니엄, 일반숙박시설만 있음)
      - None  : 표제부 자체가 없음(=집합건축물이 아님, 일반건축물로 등록된 것으로 추정)
                또는 API 조회 자체가 실패함 (나중에 재시도 필요, '아니다'와는 다름)
    """
    title = fetch_building_title(sigungu_cd, bjdong_cd, plat_gb, bun, ji)
    time.sleep(REQUEST_SLEEP)

    if title is None:
        return None, None, "표제부 없음(일반건축물 추정)"

    # 1차: 표제부 주용도/기타용도에서 바로 확인
    combined = f"{title['main_purps']} {title['etc_purps']}"
    if LIVINGSTAY_KEYWORD in combined:
        return True, title, "표제부에서 확인"

    # 2차: 표제부에 명시가 없으면 층별개요 추가 조회
    floors = fetch_floor_outline(sigungu_cd, bjdong_cd, plat_gb, bun, ji)
    time.sleep(REQUEST_SLEEP)

    if floors is None:
        return None, title, "층별개요 조회 실패(재시도 필요)"

    for f in floors:
        if LIVINGSTAY_KEYWORD in f["main_purps"] or LIVINGSTAY_KEYWORD in f["etc_purps"]:
            return True, title, "층별개요에서 확인"

    return False, title, "표제부·층별개요 모두 생활숙박시설 아님(호텔/콘도 등으로 추정)"
