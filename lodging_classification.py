"""숙박업의 법정 영업분류와 건축물 용도를 분리하는 공통 규칙."""

ACTIVE_STATUS = "영업/정상"

PRIMARY_LODGING_TYPES = (
    "일반",
    "생활",
    "관광",
    "에어비앤비",
    "농어촌민박",
    "캠핑",
    "한옥",
)

GENERAL_LODGING_SUBTYPE_ORDER = ("일반호텔", "여관업", "여인숙업")

HYGIENE_TYPE_TO_LODGING_TYPE = {
    "숙박업(일반)": "일반",
    "일반숙박업": "일반",
    "일반호텔": "일반",
    "여관업": "일반",
    "여인숙업": "일반",
    "숙박업(생활)": "생활",
    "생활숙박업": "생활",
    "생활숙박시설": "생활",
    "관광숙박업": "관광",
    "관광호텔업": "관광",
    "휴양콘도미니엄업": "관광",
    "한국전통호텔업": "관광",
    "가족호텔업": "관광",
    "소형호텔업": "관광",
    "의료관광호텔업": "관광",
    "외국인관광도시민박업": "에어비앤비",
    "농어촌민박업": "농어촌민박",
    "야영장업": "캠핑",
    "한옥체험업": "한옥",
}

_SPECIFIC_LAW_TYPES = frozenset(
    {"에어비앤비", "농어촌민박", "캠핑", "한옥"}
)


def normalize_hygiene_type(value) -> str:
    return str(value or "").strip()


def lodging_type_for_hygiene(value):
    """공식 신고·등록 업태를 서비스의 법정 영업분류로 변환한다."""
    return HYGIENE_TYPE_TO_LODGING_TYPE.get(normalize_hygiene_type(value))


def choose_primary_lodging_type(hygiene_types):
    """한 건물의 활성 신고들에서 중복 의제를 제거한 주 영업분류를 고른다.

    관광진흥법·농어촌정비법상 구체적 등록은 공중위생 신고보다 우선한다.
    서로 다른 별도법령 유형이 실제로 함께 있으면 임의 선택하지 않고 복합으로 둔다.
    """
    categories = {
        lodging_type_for_hygiene(value)
        for value in hygiene_types
    }
    categories.discard(None)
    if not categories:
        return None

    specific = categories & _SPECIFIC_LAW_TYPES
    if len(specific) > 1:
        return "복합"
    if specific:
        return next(iter(specific))
    if "관광" in categories:
        return "관광"
    if "생활" in categories:
        return "생활"
    if "일반" in categories:
        return "일반"
    return None


def classify_building_use(raw_value):
    """건축물 용도 원문을 독립된 표준 용도로 축약한다."""
    text = normalize_hygiene_type(raw_value)
    if not text:
        return "확인불가"

    found = set()
    if any(token in text for token in ("주택", "아파트", "다가구", "다세대")):
        found.add("주택")
    if any(token in text for token in ("수련시설", "야영장", "캠핑장")):
        found.add("수련시설")
    if any(
        token in text
        for token in (
            "숙박시설",
            "생활숙박",
            "관광숙박",
            "호텔",
            "여관",
            "여인숙",
            "콘도미니엄",
        )
    ):
        found.add("숙박시설")

    if len(found) > 1:
        return "복합"
    if found:
        return next(iter(found))
    return "기타"


def is_active_status(value) -> bool:
    """현재 영업으로 인정하는 상태는 정확히 영업/정상뿐이다."""
    return normalize_hygiene_type(value) == ACTIVE_STATUS


def iter_chunks(items, size=100):
    """대량 SQL 작업을 예측 가능한 크기로 나눈다."""
    if size < 1:
        raise ValueError("chunk size must be positive")
    for offset in range(0, len(items), size):
        yield items[offset:offset + size]