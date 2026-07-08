"""
building_registry.py — 건축HUB 건축물대장 조회 + 생활숙박시설(생숙) 판별 공용 모듈.

discover_new_buildings.py 와 verify_units.py 가 "같은 로직을 각자 따로 구현"하다
한쪽만 고쳐지는 문제가 반복돼서, 표제부 조회와 생숙 판정 로직을 이 한 곳으로 모은다.
두 스크립트는 반드시 이 모듈의 함수를 import 해서 쓴다.

핵심 사실 (실측으로 확인됨)
------------------------------------------------------------
- 생숙/일반호텔/관광호텔은 표제부(getBrTitleInfo) 주용도(mainPurpsCdNm)에서 대부분
  '숙박시설'로만 나와 구분이 안 된다. 어떤 건물은 기타용도(etcPurps)에
  '숙박시설(생활숙박시설)'처럼 표기되지만(예: 경희마크329), 어떤 생숙은 그냥
  '숙박시설'로만 나온다(예: 휴스테이). 즉 표제부 표기는 건물마다 들쭉날쭉하다.
- 반면 층별개요(getBrFlrOulnInfo)에는 층마다 주용도='생활숙박시설'로 일관되게 찍힌다.
  → 생숙 판별의 신뢰 가능한 기준은 층별개요다.
- 그래서 판별은 하이브리드: 표제부에 '생활숙박' 표기가 있으면 통과(API 호출 절약),
  없으면 그때만 층별개요를 추가 조회해서 확인한다.
"""

import os
import time
from xml.etree import ElementTree as ET

import requests

BLD_SERVICE_KEY = os.environ.get("BLD_SERVICE_KEY", "")
BLD_TITLE_URL = "https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo"
BLD_FLR_URL = "https://apis.data.go.kr/1613000/BldRgstHubService/getBrFlrOulnInfo"

REQUEST_SLEEP = 0.15


def _hocnt(row: dict) -> int:
    try:
        return int(row.get("hoCnt", "0") or 0)
    except (ValueError, TypeError):
        return 0


def fetch_building_title(sigungu_cd, bjdong_cd, plat_gb, bun, ji):
    """표제부(getBrTitleInfo) 조회 → dict 반환. 없으면 None.

    한 지번에 여러 동이 잡히면 '숙박' 용도 동을 우선하고 그중 호수(hoCnt) 최댓값을 취한다.
    반환 후 REQUEST_SLEEP 만큼 쉰다(호출 간격 확보).
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
    time.sleep(REQUEST_SLEEP)
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
        "raw": row,
    }


def is_living_stay(sigungu_cd, bjdong_cd, plat_gb, bun, ji, title: dict) -> bool:
    """생활숙박시설(생숙) 여부 판정.

    1) 표제부 주용도/기타용도에 '생활숙박' 표기가 있으면 즉시 True (층별개요 호출 없음).
    2) 없으면 층별개요(getBrFlrOulnInfo)를 조회해 층별 용도에 '생활숙박'이 있는지 확인.

    표제부 fast-pass일 때는 추가 sleep 없음(불필요한 대기 제거).
    층별개요를 실제로 조회했을 때만 REQUEST_SLEEP 만큼 쉰다.
    """
    if "생활숙박" in (title.get("main_purps", "") or "") or "생활숙박" in (title.get("etc_purps", "") or ""):
        return True

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
    resp = requests.get(BLD_FLR_URL, params=params, timeout=15)
    resp.raise_for_status()
    time.sleep(REQUEST_SLEEP)
    root = ET.fromstring(resp.content)
    for it in root.findall(".//item"):
        d = {c.tag: (c.text or "").strip() for c in it}
        if "생활숙박" in d.get("mainPurpsCdNm", "") or "생활숙박" in d.get("etcPurps", ""):
            return True
    return False
