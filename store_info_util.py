# -*- coding: utf-8 -*-
"""
store_info_util.py — 소상공인시장진흥공단 상가(상권)정보 API 헬퍼.

B화면 "상거래정보" 카드용: 이 건물(지번) 안의 상가업소(사업자) 목록을
층 정보까지 조회한다.

조회 키에 대한 실측 결과 (2026-07 확인)
------------------------------------------------------------
- storeListInBuilding 의 key(건물관리번호)는 도로명주소 체계의 25자리
  bldMngNo(PNU 19자리 + 일련번호 6자리)다. 표제부의 mgmBldrgstPk
  (관리건축물대장PK)와는 **다른 번호**라 그대로 넣으면 NODATA가 난다.
  마지막 6자리 일련번호는 우리 데이터로 만들 수 없음.
- 대신 storeListInPnu(key=PNU 19자리)는 sgg_cd(5)+법정동(5)+토지구분(1)
  +본번(4)+부번(4)으로 우리가 직접 만들 수 있고, 같은 지번의 업소가
  층 정보 포함으로 정확히 나온다 → 이것을 사용한다.
- 이 API는 type=json 지정 시 게이트웨이가 403 Forbidden을 반환함(같은 키로
  XML 요청은 정상 200). 반드시 XML로 받을 것. storeListInRadius도 403.

- 서비스키: STORE_INFO_SERVICE_KEY (data.go.kr 발급)
- 실패(키 없음/타임아웃/쿼터/파싱오류)해도 예외를 던지지 않고 빈 리스트를
  반환한다 — 건물상세 화면이 이 카드 때문에 죽으면 안 되기 때문.
"""

import os
from xml.etree import ElementTree as ET

import requests

STORE_INFO_SERVICE_KEY = os.environ.get("STORE_INFO_SERVICE_KEY", "")
_BASE = "https://apis.data.go.kr/B553077/api/open/sdsc2"
STORE_IN_PNU_URL = f"{_BASE}/storeListInPnu"
STORE_IN_BUILDING_URL = f"{_BASE}/storeListInBuilding"

_PAGE_SIZE = 100
_MAX_PAGES = 10  # 안전 상한(최대 1,000개) — 단일 지번이 이걸 넘는 경우는 사실상 없음


def build_pnu(sgg_cd, bjdong_cd, plat_gb, bun, ji):
    """PNU 19자리 생성. plat_gb: 건축물대장 대지구분(0=대지,1=산) → PNU 토지구분(1=일반,2=산)."""
    if not sgg_cd or not bjdong_cd:
        return None
    land_gb = "2" if str(plat_gb).strip() == "1" else "1"
    return f"{sgg_cd}{bjdong_cd}{land_gb}{str(bun).zfill(4)}{str(ji).zfill(4)}"


def _fetch_stores(url, key):
    """공통 XML 페이징 조회. 실패 시 빈 리스트."""
    key = (key or "").strip()
    if not key or not STORE_INFO_SERVICE_KEY:
        return []

    stores = []
    page = 1
    while page <= _MAX_PAGES:
        params = {
            "serviceKey": STORE_INFO_SERVICE_KEY,
            "key": key,
            "numOfRows": _PAGE_SIZE,
            "pageNo": page,
        }
        try:
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
        except Exception:
            return []  # 어떤 실패든 조용히 빈 결과 (화면은 "준비 중" 유지)

        result_code = (root.findtext(".//resultCode") or "").strip()
        if result_code not in ("00", "0"):
            return []  # 03 NODATA_ERROR 포함

        items = root.findall(".//item")
        for it in items:
            row = {c.tag: (c.text or "").strip() for c in it}
            name = row.get("bizesNm", "")
            if not name:
                continue
            stores.append({
                "name": name,
                "category": row.get("indsLclsNm", ""),
                "floor": row.get("flrNo", ""),
            })

        total_txt = root.findtext(".//totalCount")
        try:
            total = int(total_txt) if total_txt else len(stores)
        except ValueError:
            total = len(stores)
        if not items or len(stores) >= total:
            break
        page += 1

    return stores


def get_stores_by_pnu(pnu):
    """PNU(19자리)로 그 지번 건물의 상가업소 목록 조회.

    반환: [{"name": 상호명, "category": 상권업종대분류명, "floor": 층(문자, 없으면 "")}]
    실패 시(키 없음 포함) 빈 리스트.
    """
    return _fetch_stores(STORE_IN_PNU_URL, pnu)


def get_stores_in_building(bld_mng_no):
    """건물관리번호(25자리 bldMngNo)로 조회 — bldMngNo를 확보한 경우에만 사용.
    (표제부 mgmBldrgstPk는 이 번호가 아님 — 모듈 docstring 참고)"""
    return _fetch_stores(STORE_IN_BUILDING_URL, bld_mng_no)
