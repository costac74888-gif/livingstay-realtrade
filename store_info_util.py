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
from urllib.parse import unquote
from xml.etree import ElementTree as ET

import requests

# data.go.kr 콘솔에서 복사한 키는 URL인코딩 포함(%2B, %3D 등).
# requests가 params로 넘길 때 다시 인코딩하면 이중 인코딩(%252B)이 돼 403이 난다.
# unquote로 한 번 디코딩해서 실제 바이트로 저장한다.
STORE_INFO_SERVICE_KEY = unquote(os.environ.get("STORE_INFO_SERVICE_KEY", ""))
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
    """공통 JSON 페이징 조회. 실패 시 예외를 올려 호출자(_bg_fetch)가 로그를 남기게 한다.

    API 응답 형식 (2026-07 확인):
      {"header": {"resultCode": "00", ...},
       "body": {"items": {"item": [ {...}, ... ]}}}
    resultCode "03" = NODATA, "00" = 정상.
    totalCount 필드가 없으므로 반환 item 수 < numOfRows이면 마지막 페이지로 판단.
    """
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
        except Exception as e:
            raise RuntimeError(f"상가업소 API HTTP 오류: {e}") from e

        try:
            data = resp.json()
        except Exception:
            # 비JSON 응답 (XML 오류 페이지 등)
            raise RuntimeError(f"상가업소 API 비JSON 응답: {resp.text[:200]}")

        # 인증 오류 등은 OpenAPI_ServiceResponse 래퍼로 온다
        if "OpenAPI_ServiceResponse" in data:
            err = (data["OpenAPI_ServiceResponse"]
                   .get("cmmMsgHeader", {})
                   .get("errMsg", "unknown"))
            raise RuntimeError(f"상가업소 API 게이트웨이 오류: {err}")

        result_code = str(data.get("header", {}).get("resultCode", "")).strip()
        if result_code not in ("00", "0"):
            # "03" = NODATA — 업소 없는 지번은 정상 빈 결과
            return []

        body = data.get("body", {})
        if not isinstance(body, dict):
            return []

        items_wrap = body.get("items", {})
        if not isinstance(items_wrap, dict):
            return []

        raw_items = items_wrap.get("item", [])
        # 단건이면 dict로 오는 경우가 있음 — 리스트로 정규화
        if isinstance(raw_items, dict):
            raw_items = [raw_items]

        page_count = 0
        for it in raw_items:
            name = (it.get("bizesNm") or "").strip()
            if not name:
                continue
            stores.append({
                "name": name,
                "category": (it.get("indsLclsNm") or "").strip(),
                "floor": str(it.get("flrNo") or "").strip(),
            })
            page_count += 1

        # 마지막 페이지 판단: 반환 수 < 요청 수
        if page_count < _PAGE_SIZE:
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
