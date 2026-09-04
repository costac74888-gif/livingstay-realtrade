"""활성 캠핑시설 통계용 원본 행 중복 제거 규칙."""

from __future__ import annotations


_CLASSIFICATIONS = (
    "general_only", "auto_only", "glamping_only", "caravan_only",
    "confirmed_mixed", "unknown",
)


def _location_business_key(row):
    """주소와 상호가 모두 있을 때만 원본 간 동일 시설로 간주한다."""
    address = str(row.get("road_norm") or row.get("jibun_norm") or "").strip()
    name = str(row.get("biz_name_norm") or "").strip()
    return (address, name) if address and name else None


def _representative(rows):
    """중복 원본은 유형 데이터가 가장 완전한(총 사이트가 큰) 행을 택한다."""
    def site_total(row):
        total = 0
        for key in (
            "camping_general_site_count", "camping_auto_site_count",
            "camping_glamping_site_count", "camping_caravan_site_count",
        ):
            try:
                total += max(0, int(row.get(key) or 0))
            except (TypeError, ValueError):
                pass
        return total

    return max(
        rows,
        key=lambda row: (
            site_total(row),
            str(row.get("permit_number") or ""),
        ),
    )


def summarize_active_camping_facilities(rows):
    """활성 캠핑 원장 행을 고유 시설과 사이트 유형 합계로 축약한다.

    ``applied_building_id``가 있는 행은 건물당 하나만 센다. 연결되지 않은
    토지·사업장 행은 주소와 정규화 상호가 함께 있을 때만 원본 간 중복을
    통합한다. 신뢰할 위치·상호 키가 없는 행은 관리번호별로 보존해 과도한
    추정을 하지 않는다. 연결 시설과 동일한 신뢰 키의 미연결 행은 제외한다.
    """
    linked = {}
    unlinked = {}
    linked_location_keys = set()
    for row in rows:
        building_id = row.get("applied_building_id")
        if building_id is not None:
            linked.setdefault(building_id, []).append(row)
            key = _location_business_key(row)
            if key:
                linked_location_keys.add(key)
            continue
        key = _location_business_key(row)
        # 이름과 위치가 모두 없는 미연결 행은 안전하게 각각 별개 시설이다.
        key = ("permit", str(row.get("permit_number") or id(row))) if key is None else key
        unlinked.setdefault(key, []).append(row)

    facilities = [_representative(group) for group in linked.values()]
    facilities.extend(
        _representative(group)
        for key, group in unlinked.items()
        if key not in linked_location_keys
    )
    result = {
        "camping_facility_count": len(facilities),
        "camping_general_site_count": 0,
        "camping_auto_site_count": 0,
        "camping_glamping_site_count": 0,
        "camping_caravan_site_count": 0,
        "camping_classification_breakdown": {
            classification: 0 for classification in _CLASSIFICATIONS
        },
    }
    for row in facilities:
        for key in (
            "camping_general_site_count", "camping_auto_site_count",
            "camping_glamping_site_count", "camping_caravan_site_count",
        ):
            try:
                result[key] += max(0, int(row.get(key) or 0))
            except (TypeError, ValueError):
                pass
        classification = row.get("camping_classification")
        result["camping_classification_breakdown"][
            classification if classification in _CLASSIFICATIONS else "unknown"
        ] += 1
    result["camping_site_count"] = sum(
        result[key] for key in (
            "camping_general_site_count", "camping_auto_site_count",
            "camping_glamping_site_count", "camping_caravan_site_count",
        )
    )
    return result