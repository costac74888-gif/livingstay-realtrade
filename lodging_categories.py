"""행안부 문화_숙박업 조회서비스의 실제 위생업태명 분류."""

# 원본 API 표본(2026-08-22)에서 확인한 실제 값만 사용한다.
# '숙박업(일반)'은 API 응답에 나타나지 않아 대상값으로 사용하지 않는다.
LIVING_LODGING_HYGIENE_TYPES = frozenset({"숙박업(생활)"})
GENERAL_LODGING_HYGIENE_TYPES = frozenset({"일반호텔", "여관업", "여인숙업"})
TARGET_LODGING_HYGIENE_TYPES = (
    LIVING_LODGING_HYGIENE_TYPES | GENERAL_LODGING_HYGIENE_TYPES
)


def normalize_hygiene_type(value) -> str:
    """API 업태명을 비교 가능한 문자열로 정리한다."""
    return str(value or "").strip()


def is_target_lodging_hygiene(value) -> bool:
    """현재 수집 대상인 생활·일반숙박 업태인지 반환한다."""
    return normalize_hygiene_type(value) in TARGET_LODGING_HYGIENE_TYPES