"""숙박 통계에서 원본 간 동일 영업신고를 한 번만 세는 순수 규칙."""

from __future__ import annotations

import re


_TOURISM_PREFIX = "TOURISM:"


def _text_key(value):
    return re.sub(r"[^0-9A-Za-z가-힣]", "", str(value or "")).lower()


def _date_key(value):
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)[:10]


def _address_key(row):
    road = str(row.get("road_norm") or "").strip()
    if road:
        return f"road:{road}"
    jibun = str(row.get("jibun_norm") or "").strip()
    return f"jibun:{jibun}" if jibun else ""


def _cross_source_identity(row):
    """확실하게 비교 가능한 원본 간 동일 신고 후보 키를 반환한다."""
    address = _address_key(row)
    permit_date = _date_key(row.get("permit_date"))
    if not address or not permit_date:
        return None
    room_count = row.get("room_count")
    if room_count is not None:
        try:
            return address, permit_date, int(room_count), ""
        except (TypeError, ValueError):
            return None
    # 객실수가 없으면 같은 날짜·주소의 별도 영업장을 합치지 않도록 명칭까지 요구한다.
    name = _text_key(row.get("biz_name"))
    return (address, permit_date, None, name) if name else None


def deduplicate_cross_source_lodgings(rows):
    """TOURISM 원본과 기존 숙박 원장의 동일 신고를 한 번만 남긴다.

    기존 신고 행을 우선 보존한다. 같은 식별키에 한 원본 행이 여러 개면 반대편
    원본 수만큼만 제거해, 실제로 별도 신고일 수 있는 나머지 행은 유지한다.
    """
    rows = list(rows)
    groups = {}
    for index, row in enumerate(rows):
        identity = _cross_source_identity(row)
        if identity is None:
            continue
        permit = str(row.get("permit_number") or "")
        if permit.startswith(_TOURISM_PREFIX):
            side = "tourism"
        elif ":" not in permit:
            side = "legacy"
        else:
            continue
        groups.setdefault(identity, {"tourism": [], "legacy": []})[side].append(index)

    dropped = set()
    for group in groups.values():
        duplicate_count = min(len(group["tourism"]), len(group["legacy"]))
        dropped.update(group["tourism"][:duplicate_count])
    return [row for index, row in enumerate(rows) if index not in dropped]