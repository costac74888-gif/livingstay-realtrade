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


def _title_row_to_dict(row: dict) -> dict:
    return {
        "bld_nm": row.get("bldNm", "").strip(),
        "dong_nm": row.get("dongNm", "").strip(),
        "ho_cnt": _hocnt(row),
        "main_purps": row.get("mainPurpsCdNm", ""),
        "etc_purps": row.get("etcPurps", ""),
        "new_plat_plc": row.get("newPlatPlc", "").strip(),
        "plat_plc": row.get("platPlc", "").strip(),
        # 관리건축물대장PK — 주의: 상가업소정보의 25자리 건물관리번호(bldMngNo)와는
        # 다른 번호라 storeListInBuilding 키로 못 씀(store_info_util.py 참고)
        "mgm_bldrgst_pk": row.get("mgmBldrgstPk", "").strip(),
    }


def _fetch_title_rows(sigungu_cd, bjdong_cd, plat_gb, bun, ji):
    """표제부(getBrTitleInfo) 조회 → 이 지번에 선 '모든 동'의 raw dict 리스트. 없으면 []

    용도 병기는 '지번 내 전체 동'을 봐야 정확하므로, totalCount만큼 페이징해서
    한 페이지(numOfRows) 초과분(예: 동 50개 초과 대단지)도 빠짐없이 모은다.
    """
    rows = []
    page = 1
    num = 100
    while True:
        params = {
            "serviceKey": BLD_SERVICE_KEY,
            "sigunguCd": sigungu_cd,
            "bjdongCd": bjdong_cd,
            "platGbCd": plat_gb,
            "bun": bun.zfill(4),
            "ji": ji.zfill(4),
            "numOfRows": num,
            "pageNo": page,
        }
        resp = requests.get(BLD_TITLE_URL, params=params, timeout=15)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        items = root.findall(".//item")
        rows.extend({c.tag: (c.text or "").strip() for c in it} for it in items)

        total_txt = root.findtext(".//totalCount")
        try:
            total = int(total_txt) if total_txt else len(rows)
        except ValueError:
            total = len(rows)

        if not items or len(rows) >= total or page >= 20:
            break
        page += 1
        time.sleep(REQUEST_SLEEP)
    return rows


def fetch_building_title(sigungu_cd, bjdong_cd, plat_gb, bun, ji):
    """표제부 조회 → 대표 동 dict 1개 반환(없으면 None).

    한 지번에 여러 동이 잡히면 '숙박' 용도 동을 우선하고 그중 호수(hoCnt) 최댓값을 취한다.
    (용도 분류는 classify_lodging_type이 전 동을 합쳐서 하고, 이 함수는 대표 동 정보용.)
    """
    rows = _fetch_title_rows(sigungu_cd, bjdong_cd, plat_gb, bun, ji)
    if not rows:
        return None
    lodging = [r for r in rows if "숙박" in (r.get("mainPurpsCdNm", "") or "")]
    pool = lodging if lodging else rows
    return _title_row_to_dict(max(pool, key=_hocnt))


def fetch_floor_outline(sigungu_cd, bjdong_cd, plat_gb, bun, ji):
    """층별개요(getBrFlrOulnInfo) 조회 → 각 층의 주용도/상세용도 리스트.
    조회 자체 실패 시 None(재시도 필요) — '층에 생숙 없음'(빈 리스트)과 구분한다.
    층수가 많은 대형 건물도 빠짐없이 보도록 totalCount만큼 페이징한다."""
    floors = []
    page = 1
    num = 100
    while True:
        params = {
            "serviceKey": BLD_SERVICE_KEY,
            "sigunguCd": sigungu_cd,
            "bjdongCd": bjdong_cd,
            "platGbCd": plat_gb,
            "bun": bun.zfill(4),
            "ji": ji.zfill(4),
            "numOfRows": num,
            "pageNo": page,
        }
        try:
            resp = requests.get(BLD_FLOOR_URL, params=params, timeout=15)
            resp.raise_for_status()
        except Exception:
            return None  # 조회 실패 — "생숙 아님"과 구분해서 나중에 재시도 가능하게 함

        root = ET.fromstring(resp.content)
        items = root.findall(".//item")
        for item in items:
            row = {child.tag: (child.text or "").strip() for child in item}
            floors.append({
                "flr_gb_nm": row.get("flrGbCdNm", ""),
                "flr_no_nm": row.get("flrNoNm", ""),
                "main_purps": row.get("mainPurpsCdNm", ""),
                "etc_purps": row.get("etcPurps", ""),
            })

        total_txt = root.findtext(".//totalCount")
        try:
            total = int(total_txt) if total_txt else len(floors)
        except ValueError:
            total = len(floors)

        if not items or len(floors) >= total or page >= 20:
            break
        page += 1
        time.sleep(REQUEST_SLEEP)
    return floors


def _find_categories(text):
    """텍스트에 생활/호텔/콘도 키워드가 각각 있는지 집합으로 반환(동시에 여러 개 가능)."""
    found = set()
    if "생활숙박시설" in text:
        found.add("생활")
    if "휴양콘도미니엄" in text:
        found.add("콘도")
    # 호텔 판정 주의: "관광숙박시설"은 호텔업과 휴양콘도미니엄업을 모두 포함하는 **상위 분류명**이다.
    # 그래서 "관광숙박시설(휴양콘도미니엄)"은 순수 콘도인데, 여기서 "관광숙박시설"만 보고 호텔로
    # 잡으면 콘도가 '호텔·콘도'로 오분류된다(아폴리스/골드훼미리/스카이콘도 등에서 실제 발생).
    # 따라서 (1) 구체적 호텔 표기("관광호텔"/"일반숙박시설")가 있거나,
    #        (2) 콘도 표기 없이 상위명 "관광숙박시설"만 있을 때에만 호텔로 본다.
    if "관광호텔" in text or "일반숙박시설" in text:
        found.add("호텔")
    elif "관광숙박시설" in text and "휴양콘도미니엄" not in text:
        found.add("호텔")
    return found


_CATEGORY_ORDER = ["생활", "호텔", "콘도"]  # 병기할 때 항상 이 순서로 표기 (예: "호텔·콘도")


def _combine_labels(categories):
    """카테고리 집합을 '호텔·콘도'처럼 정해진 순서로 병기한 문자열로 만든다.
    '혼재'라고 뭉뚱그리지 않고 실제 해당하는 라벨을 그대로 보여주기 위함."""
    return "·".join(c for c in _CATEGORY_ORDER if c in categories)


def classify_lodging_type(sigungu_cd, bjdong_cd, plat_gb, bun, ji):
    """
    이 지번의 건물을 생활/호텔/콘도로 분류한다 (표제부 → 필요시 층별개요 순).
    한 건물에 2가지 이상 용도가 동시에 있으면 '혼재'로 뭉뚱그리지 않고
    "호텔·콘도"처럼 실제 해당 라벨을 정해진 순서(생활→호텔→콘도)로 병기한다.
    (표제부 기타용도에 "관광호텔,휴양콘도미니엄"이 나란히 적힌 빌라쥬 드 아난티류,
     또는 층마다 용도가 다른 건물 등)

    반환값: (label, detail, title정보 dict 또는 None, 판정근거)
      label: '생활' | '호텔' | '콘도' | '호텔·콘도' 등 병기 조합 | None(판정불가)
      detail: 건축물대장에 실제로 적힌 원문 표기 — 화면 배지 툴팁에 근거로 그대로 보여주는 용도.

    표제부에서 확정되면 층별개요는 조회하지 않는다(불필요한 대기 제거).
    """
    rows = _fetch_title_rows(sigungu_cd, bjdong_cd, plat_gb, bun, ji)
    time.sleep(REQUEST_SLEEP)

    if not rows:
        return None, "", None, "표제부 없음(집합 표제부 미등록 추정)"

    # 대표 동(숙박 우선, hoCnt 최댓값) — 반환용 title dict (ho_cnt 등 부가정보)
    lodging = [r for r in rows if "숙박" in (r.get("mainPurpsCdNm", "") or "")]
    pool = lodging if lodging else rows
    title = _title_row_to_dict(max(pool, key=_hocnt))

    # 카테고리는 '이 지번의 모든 동'을 훑어 합친다.
    # 아난티 앳 부산(호텔 동 + 콘도 동이 한 지번에 나란히 선 복합단지)처럼
    # 대표 동 하나만 보면 한쪽 용도를 놓치므로, 반드시 전 동을 합쳐야 "호텔·콘도" 병기가 된다.
    categories = set()
    detail_parts = []
    for r in rows:
        etc = r.get("etcPurps", "")
        text = f"{r.get('mainPurpsCdNm', '')} {etc}".strip()
        cats = _find_categories(text)
        if cats:
            categories |= cats
            dong = r.get("dongNm", "").strip()
            detail_parts.append(f"{dong}: {etc}".strip() if dong else etc)
    combined = " / ".join(detail_parts) if detail_parts else f"{title['main_purps']} {title['etc_purps']}".strip()

    # 1차: 표제부(전 동)에서 바로 확인
    if len(categories) == 1:
        return next(iter(categories)), combined, title, "표제부에서 확인"
    if len(categories) > 1:
        return _combine_labels(categories), combined, title, "표제부의 여러 동/용도를 합쳐 병기"

    # 2차: 표제부만으론 판정 안 됨 → 층별개요 추가 조회, 전 층을 훑어 카테고리 집합을 모은다
    floors = fetch_floor_outline(sigungu_cd, bjdong_cd, plat_gb, bun, ji)
    time.sleep(REQUEST_SLEEP)

    if floors is None:
        return None, combined, title, "층별개요 조회 실패(재시도 필요)"

    all_categories = set()
    floor_detail_parts = []
    for f in floors:
        floor_text = f"{f['main_purps']} {f['etc_purps']}".strip()
        if floor_text:
            floor_detail_parts.append(floor_text)
        all_categories |= _find_categories(floor_text)

    full_detail = (combined + " / " + " / ".join(sorted(set(floor_detail_parts)))).strip(" /")

    if len(all_categories) == 1:
        return next(iter(all_categories)), full_detail, title, "층별개요에서 확인"
    if len(all_categories) > 1:
        return _combine_labels(all_categories), full_detail, title, "층별개요에 여러 용도가 섞여 있음"

    return None, full_detail, title, "표제부·층별개요 모두 판정 불가(용도 표기 없음)"


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
    if label:  # '호텔','콘도', 또는 '호텔·콘도' 등 병기 라벨 전부 생숙 아님으로 축약
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
