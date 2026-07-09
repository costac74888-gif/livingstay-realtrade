# -*- coding: utf-8 -*-
"""
building_registry.py — "이 건물이 진짜 생활숙박시설인가"를 판별하는 로직을 한 곳에 모은 공용 모듈.

discover_new_buildings.py, verify_units.py, sync_batch.py, app.py, cleanup_unverified.py
전부 반드시 이 모듈의 함수만 사용해야 한다 — 각 파일에 판정 로직을 따로 구현하면
한쪽만 고쳐지고 다른 쪽은 옛 기준(30실 게이트, 검증 없는 통과 등)으로 남는 드리프트가 반복된다.

배경 (실측으로 확인됨)
------------------------------------------------------------
건축HUB 표제부(getBrTitleInfo)의 주용도/기타용도 표기는 건물마다 들쭉날쭉하다.
- 경희마크329: "숙박시설(생활숙박시설)"처럼 괄호로 친절하게 표기
- 휘닉스파크레드앤핑크콘도미니엄: 주용도는 "숙박시설"뿐이고 실제로는 층별 전부
  "휴양콘도미니엄" → 생숙 아님
- 휴스테이 등: 표제부엔 표기가 없지만 층별개요엔 "생활숙박시설"로 명확히 나옴

그래서 표제부 하나만 보고 판정하면 안 되고 아래 순서로 확인한다.
  1) 표제부 주용도/기타용도에 "생활숙박시설"이 있으면 즉시 확정 (API 호출 절약)
  2) 없으면 층별개요(getBrFlrOulnInfo)를 추가 조회해서 각 층 용도 확인
  3) 층별개요에도 없으면(예: "휴양콘도미니엄"만 있음) → 생숙 아님으로 최종 판정
"""

import os
import time
from xml.etree import ElementTree as ET

import requests

BLD_SERVICE_KEY = os.environ.get("BLD_SERVICE_KEY", "")
BLD_TITLE_URL = "https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo"
BLD_FLOOR_URL = "https://apis.data.go.kr/1613000/BldRgstHubService/getBrFlrOulnInfo"

REQUEST_SLEEP = 0.15
LIVINGSTAY_KEYWORD = "생활숙박시설"


def _hocnt(row: dict) -> int:
    try:
        return int(row.get("hoCnt", "0") or 0)
    except (ValueError, TypeError):
        return 0


def fetch_building_title(sigungu_cd, bjdong_cd, plat_gb, bun, ji):
    """표제부(getBrTitleInfo) 조회 → dict 반환. 없으면 None.

    한 지번에 여러 동이 잡히면 '숙박' 용도 동을 우선하고 그중 호수(hoCnt) 최댓값을 취한다.
    (sleep은 호출자 is_living_stay 에서 관리한다.)
    """
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
    lodging = [r for r in rows if "숙박" in (r.get("mainPurpsCdNm", "") or "")]
    pool = lodging if lodging else rows
    row = max(pool, key=_hocnt)
    return {
        "bld_nm": row.get("bldNm", "").strip(),
        "ho_cnt": _hocnt(row),
        "main_purps": row.get("mainPurpsCdNm", ""),
        "etc_purps": row.get("etcPurps", ""),
        "new_plat_plc": row.get("newPlatPlc", "").strip(),
        "plat_plc": row.get("platPlc", "").strip(),
    }


def fetch_floor_outline(sigungu_cd, bjdong_cd, plat_gb, bun, ji):
    """층별개요(getBrFlrOulnInfo) 조회 → 각 층의 주용도/상세용도 리스트.
    조회 자체 실패 시 None(재시도 필요) — '층에 생숙 없음'(빈 리스트)과 구분한다."""
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
        return None  # 조회 실패 — "생숙 아님"과 구분해서 나중에 재시도 가능하게 함

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


def classify_lodging_type(sigungu_cd, bjdong_cd, plat_gb, bun, ji):
    """
    이 지번의 건물을 생활/호텔/콘도 3가지로 분류한다 (표제부 → 필요시 층별개요 순).

    반환값: (label, detail, title정보 dict 또는 None, 판정근거)
      label:
        '생활' — 생활숙박시설로 확인
        '호텔' — 관광숙박시설 또는 일반숙박시설로 확인 (개인분양 아닌 운영형)
        '콘도' — 휴양콘도미니엄으로 확인
        None   — 표제부 자체가 없음(일반건축물 추정) / 층별개요 조회 실패 / 위 세 키워드 다 없음(판정불가)
      detail: 건축물대장에 실제로 적힌 원문 표기 (예: "숙박시설(생활숙박시설),제1,2종근린생활시설")
              — 화면 배지 툴팁에 "이 근거로 분류했다"고 그대로 보여주기 위한 용도.

    표제부에서 확정되면 층별개요는 조회하지 않는다(불필요한 대기 제거).
    """
    title = fetch_building_title(sigungu_cd, bjdong_cd, plat_gb, bun, ji)
    time.sleep(REQUEST_SLEEP)

    if title is None:
        return None, "", None, "표제부 없음(집합 표제부 미등록 추정)"

    combined = f"{title['main_purps']} {title['etc_purps']}".strip()

    def _match(text):
        if "생활숙박시설" in text:
            return "생활"
        if "휴양콘도미니엄" in text:
            return "콘도"
        if "관광숙박시설" in text or "일반숙박시설" in text:
            return "호텔"
        return None

    # 1차: 표제부 주용도/기타용도에서 바로 확인
    label = _match(combined)
    if label:
        return label, combined, title, "표제부에서 확인"

    # 2차: 표제부만으론 판정 안 됨 → 층별개요 추가 조회
    floors = fetch_floor_outline(sigungu_cd, bjdong_cd, plat_gb, bun, ji)
    time.sleep(REQUEST_SLEEP)

    if floors is None:
        return None, combined, title, "층별개요 조회 실패(재시도 필요)"

    floor_detail_parts = []
    for f in floors:
        floor_text = f"{f['main_purps']} {f['etc_purps']}".strip()
        if floor_text:
            floor_detail_parts.append(floor_text)
        floor_label = _match(floor_text)
        if floor_label:
            full_detail = combined + " / " + " / ".join(sorted(set(floor_detail_parts)))
            return floor_label, full_detail.strip(" /"), title, "층별개요에서 확인"

    full_detail = combined + " / " + " / ".join(sorted(set(floor_detail_parts)))
    return None, full_detail.strip(" /"), title, "표제부·층별개요 모두 판정 불가(용도 표기 없음)"


def is_living_stay(sigungu_cd, bjdong_cd, plat_gb, bun, ji):
    """
    이 지번의 건물이 생활숙박시설인지 최종 판정한다 (하위호환용 얇은 래퍼).
    내부적으로 classify_lodging_type()을 호출해 3분류한 뒤 True/False/None으로 축약한다.
    새로 짜는 코드는 classify_lodging_type()을 직접 쓰는 걸 권장.

    반환값: (판정결과, 건물정보 dict 또는 None, 판정근거 문자열)
      - True  : 생활숙박시설(label='생활')
      - False : 생활숙박시설이 아님으로 확인(label='호텔' 또는 '콘도')
      - None  : 표제부 없음 / 층별개요 조회 실패 / 판정불가 (나중에 재시도 필요, '아니다'와 다름)
                title is None 여부로 '표제부 자체 없음'과 '조회는 됐으나 판정불가'를 구분할 수 있다.
    """
    label, _detail, title, reason = classify_lodging_type(sigungu_cd, bjdong_cd, plat_gb, bun, ji)
    if label == "생활":
        return True, title, reason
    if label in ("호텔", "콘도"):
        return False, title, reason

    # label is None — 레거시 semantics를 정확히 보존하기 위해 3가지로 나눈다:
    #  (a) 표제부 자체 없음(title is None)      → (None, None) : 집합 표제부 미등록. 재시도 아님.
    #  (b) 층별개요 조회 실패("재시도" 포함)     → (None, title): 일시적 API 실패 → 호출측 재시도 대상.
    #  (c) 표제부는 받았으나 생활/호텔/콘도 키워드가
    #      전혀 없음(판정 불가)                 → (False, title): 생숙 아님으로 확정(레거시 동작).
    # 이 구분이 없으면 discover/verify가 (c)를 일시 실패로 오인해 무한 재시도한다.
    if title is None:
        return None, None, reason
    if "재시도" in reason:
        return None, title, reason
    return False, title, reason
