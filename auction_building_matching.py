"""공매 주소를 기존 건물에 연결한다. 원장 변경이나 외부 API 호출은 하지 않는다."""
import re
import threading
import time
from collections import defaultdict

from addr_norm import normalize_road_prefix, normalize_jibun_prefix, get_building_jibun_key
from auction_domain import category

_cache = None
_expires_at = 0
_lock = threading.Lock()
_MULTI_PARCEL = re.compile(r"외\s*\d+\s*필지|,\s*\d+-\d+")


def building_jibun_key(building):
    key = get_building_jibun_key(building)
    if key:
        return key
    # 지번주소 문자열이 비어 있어도 공적 지역·법정동·번지가 모두 있으면 대조한다.
    parts = [building.get(field) for field in ("sgg_text", "umd_nm", "jibun")]
    return normalize_jibun_prefix(" ".join(parts)) if all(parts) else None


def build_indexes(rows):
    road, jibun = defaultdict(list), defaultdict(list)
    by_id = {}
    for row in rows:
        row = dict(row)
        by_id[row["id"]] = row
        rk = normalize_road_prefix(row.get("road_address"))
        jk = building_jibun_key(row)
        if rk:
            road[rk].append(row)
        if jk:
            jibun[jk].append(row)
    return road, jibun, by_id


def choose_building(item, road_index, jibun_index):
    """도로명 복수 후보는 지번 교집합으로 좁히되 충돌·복수 필지는 보류한다."""
    title = item.get("title") or ""
    if _MULTI_PARCEL.search((item.get("address_jibun") or "") + " " + title):
        return None
    # 목록 단계에서 주소 필드가 비어도 공식 물건명에 있는 완전한 주소만 대조한다.
    # 상호 유사도나 좌표 근접도로 연결하지 않으며 여전히 정규 주소 키 일치가 필요하다.
    rk = normalize_road_prefix(item.get("address_road")) or normalize_road_prefix(title)
    jk = normalize_jibun_prefix(item.get("address_jibun")) or normalize_jibun_prefix(title)
    roads = road_index.get(rk, []) if rk else []
    parcels = jibun_index.get(jk, []) if jk else []
    if roads and parcels:
        parcel_ids = {row["id"] for row in parcels}
        candidates = [row for row in roads if row["id"] in parcel_ids]
    elif roads:
        if len(roads) != 1:
            return None
        # 지번이 서로 다른 것으로 확인되면 도로명 한 건만으로 연결하지 않는다.
        candidates = [row for row in roads if not jk or
                      building_jibun_key(row) in (None, jk)]
    else:
        candidates = parcels
    return candidates[0] if len(candidates) == 1 else None


def get_indexes(cur):
    global _cache, _expires_at
    now = time.monotonic()
    if _cache is not None and now < _expires_at:
        return _cache
    with _lock:
        if _cache is None or time.monotonic() >= _expires_at:
            cur.execute("""SELECT id,building_name,road_address,jibun_address,
              sgg_text,umd_nm,jibun,lodging_type,lodging_type_detail,lat,lng FROM master_buildings""")
            _cache = build_indexes(cur.fetchall())
            _expires_at = time.monotonic() + 300
    return _cache


def resolve_building(cur, item):
    roads, parcels, by_id = get_indexes(cur)
    # 기존 확정 연결은 유지하고 미연결·삭제된 ID만 주소로 재검증한다.
    building = by_id.get(item.get("master_building_id"))
    if not building:
        building = choose_building(item, roads, parcels)
    item["master_building_id"] = building["id"] if building else None
    if building:
        if item.get("lodging_category") in (None, "", "기타"):
            item["lodging_category"] = category({
                "cltrUsgSclsCtgrNm": item.get("usage_name"),
                "onbidCltrNm": item.get("title"),
            }, building)
        item["building_name"] = building.get("building_name")
        item["building_lodging_type"] = building.get("lodging_type")
        for coordinate in ("lat", "lng"):
            if building.get(coordinate) is not None:
                item[coordinate] = building[coordinate]
    return building