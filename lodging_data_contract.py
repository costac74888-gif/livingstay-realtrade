"""숙박 정부 원장과 서비스 분류가 공유하는 데이터 계약.

이 모듈은 CSV/API importer, staging, 관리자 검증, 통계가 같은 정책값을
사용하도록 하는 순수 규칙 모듈이다. DB나 외부 API를 호출하지 않는다.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from urllib.parse import quote


# 정부 숙박 원장에 포함할 원본 8종. 값은 파일명이나 표시 문구가 바뀌어도
# 유지할 내부 키이고, label은 관리자 화면·보고서용 원본명이다.
GOVERNMENT_LODGING_SOURCES = {
    "tourism_lodging": {
        "label": "관광숙박업",
        "raw_types": frozenset({"관광숙박업"}),
    },
    "tourism_pension": {
        "label": "관광펜션업",
        "raw_types": frozenset({"관광펜션업"}),
    },
    "rural_homestay": {
        "label": "농어촌민박업",
        "raw_types": frozenset({"농어촌민박업"}),
    },
    "lodging": {
        "label": "숙박업",
        "raw_types": frozenset({
            "숙박업(생활)",
            "여관업",
            "여인숙업",
            "일반호텔",
            "관광호텔",
            "휴양콘도미니엄업",
            "숙박업 기타",
            "",
        }),
    },
    "foreign_city_homestay": {
        "label": "외국인관광도시민박업",
        "raw_types": frozenset({"외국인관광도시민박업"}),
    },
    "general_camping": {
        "label": "일반야영장업",
        "raw_types": frozenset({"일반야영장업"}),
    },
    "auto_camping": {
        "label": "자동차야영장업",
        "raw_types": frozenset({"자동차야영장업"}),
    },
    "hanok": {
        "label": "한옥체험업",
        "raw_types": frozenset({"한옥체험업"}),
    },
}

SUPPORTED_SOURCE_KEYS = frozenset(GOVERNMENT_LODGING_SOURCES)
EXCLUDED_SOURCE_KEYS = frozenset({"special_recreation"})
EXCLUDED_SOURCE_LABELS = frozenset({"전문휴양업"})

# 현재 lodging_registry에서 이미 사용하는 접두어와 호환한다. 일반 숙박 API
# 원장은 관리번호 원문을 그대로 사용하고, 나머지는 기존 importer 접두어를
# 유지해 신규로 오인하지 않게 한다.
REGISTRY_PERMIT_PREFIX_BY_SOURCE = {
    "tourism_lodging": "TOURISM",
    "tourism_pension": "PENSION",
    "rural_homestay": "RURAL",
    "lodging": None,
    "foreign_city_homestay": "AIRBNB",
    "general_camping": "CAMPING",
    "auto_camping": "CAMPING",
    "hanok": "HANOK",
}

SERVICE_CATEGORY_TOURISM = "관광숙박"
SERVICE_CATEGORY_GENERAL = "일반숙박"
SERVICE_CATEGORY_LIVING = "생활숙박"
SERVICE_CATEGORY_AIRBNB = "에어비앤비"
SERVICE_CATEGORY_RURAL = "농어촌민박"
SERVICE_CATEGORY_CAMPING = "캠핑"
SERVICE_CATEGORY_HANOK = "한옥"
SERVICE_CATEGORY_UNCLASSIFIED = "미분류"

SERVICE_CATEGORIES = frozenset({
    SERVICE_CATEGORY_TOURISM,
    SERVICE_CATEGORY_GENERAL,
    SERVICE_CATEGORY_LIVING,
    SERVICE_CATEGORY_AIRBNB,
    SERVICE_CATEGORY_RURAL,
    SERVICE_CATEGORY_CAMPING,
    SERVICE_CATEGORY_HANOK,
    SERVICE_CATEGORY_UNCLASSIFIED,
})

# 정부 원문 업태를 서비스 분류로 바꾸는 정책 매핑이다. 건축물대장
# building_use_type에는 사용하지 않는다.
RAW_HYGIENE_TYPE_TO_SERVICE_CATEGORY = {
    "관광숙박업": SERVICE_CATEGORY_TOURISM,
    "관광펜션업": SERVICE_CATEGORY_TOURISM,
    "농어촌민박업": SERVICE_CATEGORY_RURAL,
    "숙박업(생활)": SERVICE_CATEGORY_LIVING,
    "여관업": SERVICE_CATEGORY_GENERAL,
    "여인숙업": SERVICE_CATEGORY_GENERAL,
    "일반호텔": SERVICE_CATEGORY_GENERAL,
    "관광호텔": SERVICE_CATEGORY_TOURISM,
    "휴양콘도미니엄업": SERVICE_CATEGORY_TOURISM,
    "숙박업 기타": SERVICE_CATEGORY_GENERAL,
    "외국인관광도시민박업": SERVICE_CATEGORY_AIRBNB,
    "일반야영장업": SERVICE_CATEGORY_CAMPING,
    "자동차야영장업": SERVICE_CATEGORY_CAMPING,
    "한옥체험업": SERVICE_CATEGORY_HANOK,
}

# 기존 master_buildings.lodging_type와 호환되는 내부 값이다.
RAW_HYGIENE_TYPE_TO_LEGACY_TYPE = {
    raw_type: {
        SERVICE_CATEGORY_TOURISM: "관광",
        SERVICE_CATEGORY_GENERAL: "일반",
        SERVICE_CATEGORY_LIVING: "생활",
        SERVICE_CATEGORY_AIRBNB: "에어비앤비",
        SERVICE_CATEGORY_RURAL: "농어촌민박",
        SERVICE_CATEGORY_CAMPING: "캠핑",
        SERVICE_CATEGORY_HANOK: "한옥",
    }[service_category]
    for raw_type, service_category in RAW_HYGIENE_TYPE_TO_SERVICE_CATEGORY.items()
}

STATUS_ACTIVE = "active"
STATUS_TEMPORARILY_CLOSED = "temporarily_closed"
STATUS_CLOSED = "closed"
STATUS_EXCLUDED = "excluded"
STATUS_REVIEW = "review"

ACTIVE_STATUS_LABEL = "영업/정상"
TEMPORARILY_CLOSED_STATUS_LABEL = "휴업"
_CLOSED_STATUS_TOKENS = ("폐업", "취소", "말소", "만료", "정지", "중지")
_EXCLUDED_STATUS_TOKENS = ("제외", "삭제", "전출")


def normalize_text(value) -> str:
    """원문 비교용 공백을 제거하되 내부 원문은 임의로 바꾸지 않는다."""
    return str(value or "").strip()


def source_is_supported(source_key) -> bool:
    return normalize_text(source_key) in SUPPORTED_SOURCE_KEYS


def source_label(source_key):
    source = GOVERNMENT_LODGING_SOURCES.get(normalize_text(source_key))
    return source["label"] if source else None


def service_category_for_hygiene(value):
    """원문 업태를 서비스 분류로 변환한다.

    빈 업태는 정책상 미분류·관리자 확인으로 보존하고, 알려지지 않은
    비어 있지 않은 값은 조용히 승인하지 않도록 None을 반환한다.
    """
    raw_type = normalize_text(value)
    if not raw_type:
        return SERVICE_CATEGORY_UNCLASSIFIED
    return RAW_HYGIENE_TYPE_TO_SERVICE_CATEGORY.get(raw_type)


def legacy_lodging_type_for_hygiene(value):
    category = service_category_for_hygiene(value)
    if category == SERVICE_CATEGORY_UNCLASSIFIED:
        return None
    return {
        SERVICE_CATEGORY_TOURISM: "관광",
        SERVICE_CATEGORY_GENERAL: "일반",
        SERVICE_CATEGORY_LIVING: "생활",
        SERVICE_CATEGORY_AIRBNB: "에어비앤비",
        SERVICE_CATEGORY_RURAL: "농어촌민박",
        SERVICE_CATEGORY_CAMPING: "캠핑",
        SERVICE_CATEGORY_HANOK: "한옥",
    }.get(category)


def classify_operation_status(value) -> str:
    """원문 영업상태를 목록·통계용 상태 버킷으로 분류한다."""
    status = normalize_text(value)
    if status == ACTIVE_STATUS_LABEL:
        return STATUS_ACTIVE
    if status == TEMPORARILY_CLOSED_STATUS_LABEL:
        return STATUS_TEMPORARILY_CLOSED
    if any(token in status for token in _EXCLUDED_STATUS_TOKENS):
        return STATUS_EXCLUDED
    if any(token in status for token in _CLOSED_STATUS_TOKENS):
        return STATUS_CLOSED
    return STATUS_REVIEW


def is_visible_in_basic_list(value) -> bool:
    return classify_operation_status(value) in {
        STATUS_ACTIVE,
        STATUS_TEMPORARILY_CLOSED,
    }


def is_in_active_statistics(value) -> bool:
    return classify_operation_status(value) == STATUS_ACTIVE


def build_permit_identity(source_key, authority_code, permit_number):
    """원장 upsert용 원본·관할기관·관리번호 식별키를 만든다."""
    source = normalize_text(source_key)
    if source not in SUPPORTED_SOURCE_KEYS:
        raise ValueError("지원하지 않는 숙박 원본입니다.")
    permit = normalize_text(permit_number)
    if not permit:
        return None
    authority = normalize_text(authority_code) or "_"
    # 식별자에는 구분자를 그대로 허용하지 않아도 되지만, 저장·로그 비교 시
    # 모호성이 없도록 각 구성요소를 URL-safe 텍스트로 고정한다.
    return ":".join(
        quote(part, safe="-_.~")
        for part in (source.upper(), authority, permit)
    )


def build_registry_permit_identity(source_key, authority_code, permit_number):
    """기존 lodging_registry 키와 호환되는 관리번호를 만든다."""
    source = normalize_text(source_key)
    if source not in SUPPORTED_SOURCE_KEYS:
        raise ValueError("지원하지 않는 숙박 원본입니다.")
    permit = normalize_text(permit_number)
    if not permit:
        return None
    prefix = REGISTRY_PERMIT_PREFIX_BY_SOURCE[source]
    if prefix is None:
        return permit
    authority = normalize_text(authority_code)
    if authority:
        return ":".join(
            quote(part, safe="-_.~")
            for part in (prefix, authority, permit)
        )
    return ":".join(
        quote(part, safe="-_.~")
        for part in (prefix, permit)
    )


def normalize_reference_date(value):
    """원본 기준일을 YYYY-MM-DD로 정규화한다."""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = normalize_text(value)
    match = re.match(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", text)
    if not match:
        return None
    try:
        return date(
            int(match.group(1)),
            int(match.group(2)),
            int(match.group(3)),
        ).isoformat()
    except ValueError:
        return None


def build_source_snapshot_identity(
    source_key,
    reference_date,
    authority_code,
    permit_number,
):
    """staging 검증용 원본·기준일·관할기관·관리번호 식별키를 만든다.

    기준일이 없는 행은 어느 원본 스냅샷에 속하는지 검증할 수 없으므로
    조용히 임의의 날짜를 넣지 않고 None으로 보류한다.
    """
    source = normalize_text(source_key)
    if source not in SUPPORTED_SOURCE_KEYS:
        raise ValueError("지원하지 않는 숙박 원본입니다.")
    permit = normalize_text(permit_number)
    snapshot_date = normalize_reference_date(reference_date)
    if not permit or not snapshot_date:
        return None
    authority = normalize_text(authority_code) or "_"
    return ":".join(
        quote(part, safe="-_.~")
        for part in (source.upper(), snapshot_date, authority, permit)
    )