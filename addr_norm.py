"""
addr_norm.py — 도로명주소 정규화 유틸 (숙박업 영업신고 ↔ master_buildings 매칭용).

전략: 두 데이터의 주소 표기가 미세하게 다르다(공백, 특별자치도 개칭, 상세주소/괄호 표기).
'도로명 + 건물번호'까지만 잘라 정규화한 prefix 키(road_norm)로 매칭한다.
"""

import re

# 광역명 개칭/표기 차이 통일 (앞부분만 치환)
_REGION_ALIASES = [
    ("강원특별자치도", "강원도"),
    ("전북특별자치도", "전라북도"),
    ("제주특별자치도", "제주도"),
    ("제주도", "제주도"),
    ("서울특별시", "서울"),
    ("부산광역시", "부산"),
    ("대구광역시", "대구"),
    ("인천광역시", "인천"),
    ("광주광역시", "광주"),
    ("대전광역시", "대전"),
    ("울산광역시", "울산"),
    ("세종특별자치시", "세종"),
]

# 도로명주소에서 '도로명 + 건물번호'까지만 남기기 위한 패턴:
# 예) "서울특별시 강서구 마곡중앙6로 76-3(마곡동), 101동 202호" → "... 마곡중앙6로 76-3"
_ROAD_PREFIX_RE = re.compile(
    r"^(.*?[가-힣A-Za-z0-9·.]+(?:로|길|대로)\s*\d+(?:-\d+)?)"
)


def normalize_road_prefix(addr):
    """도로명주소 → 정규화 매칭 키. 실패 시 None.

    1) 괄호 이후/콤마 이후 상세 제거 전에 도로명+건물번호 prefix 추출
    2) 광역명 표기 통일
    3) 공백/특수문자 전부 제거
    """
    if not addr:
        return None
    s = str(addr).strip()
    m = _ROAD_PREFIX_RE.match(s)
    if not m:
        return None
    s = m.group(1)
    for old, new in _REGION_ALIASES:
        if s.startswith(old):
            s = new + s[len(old):]
            break
    # 공백·쉼표·점 등 제거 (숫자/한글/영문/하이픈만 유지)
    s = re.sub(r"[^0-9가-힣A-Za-z-]", "", s)
    return s.lower() or None


def normalize_name(name):
    """업체명/사업장명 정규화 — operators.company_name ↔ lodging_registry.biz_name 매칭용."""
    if not name:
        return None
    s = str(name).strip().lower()
    # 법인 표기/괄호부 제거
    s = re.sub(r"[(\[].*?[)\]]", "", s)
    for token in ("주식회사", "(주)", "㈜", "유한회사", "합자회사"):
        s = s.replace(token, "")
    s = re.sub(r"[^0-9가-힣a-z]", "", s)
    return s or None
