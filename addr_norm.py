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
    ("전라남도", "전남"),
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

# 일부 숙박업 원본에는 광주와 전남이 합쳐진 과거/통합 표기(전남광주통합특별시)가
# 남아 있다. 뒤의 시군구가 광주 5개 자치구이면 광주, 나머지는 전남으로 복원한다.
_GWANGJU_JACHIGU = frozenset({"동구", "서구", "남구", "북구", "광산구"})
_MERGED_GWANGJU_JEONNAM = "전남광주통합특별시"


def _normalize_region_prefix(value: str) -> str:
    """주소 선두의 광역명 표기 편차를 매칭용 짧은 이름으로 통일한다."""
    s = value or ""
    if s.startswith(_MERGED_GWANGJU_JEONNAM):
        rest = s[len(_MERGED_GWANGJU_JEONNAM):].lstrip()
        first_locality = rest.split(None, 1)[0] if rest else ""
        s = ("광주" if first_locality in _GWANGJU_JACHIGU else "전남") + (
            f" {rest}" if rest else ""
        )
    for old, new in _REGION_ALIASES:
        if s.startswith(old):
            return new + s[len(old):]
    return s

# 도로명주소에서 '도로명 + 건물번호'까지만 남기기 위한 패턴:
# 예) "서울특별시 강서구 마곡중앙6로 76-3(마곡동), 101동 202호" → "... 마곡중앙6로 76-3"
_ROAD_PREFIX_RE = re.compile(
    r"^(.*?[가-힣A-Za-z0-9·.]+(?:로|길|대로)\s*\d+(?:-\d+)?)"
)
_ROAD_TAIL_RE = re.compile(
    r"[가-힣A-Za-z0-9·.]+(?:로|길|대로)\s*\d+(?:-\d+)?$"
)
# 괄호 안 일반 법정동은 도로명주소의 참고 표기일 뿐이고, broker_registry 같은
# 표준 도로명주소에는 포함되지 않는다. 도로명 본문에 실제로 필요한 읍·면만 복원한다.
_PAREN_LOCALITY_RE = re.compile(r"[가-힣][가-힣0-9]*(?:읍|면)")


def _restore_parenthetical_locality(road_prefix, original):
    """도로명 본문에서 생략된 괄호 안 읍·면 표기를 보완한다.

    건축물대장은 ``경상북도 칠곡군 팔공산로2길 8 (동명면 기성리)``처럼
    행정구역을 괄호에 두는 반면, 신고 데이터는 ``경상북도 칠곡군 동명면
    팔공산로2길 8``처럼 도로명 앞에 둔다. 도로명 자체는 바꾸지 않고,
    괄호에서 읍·면 토큰 하나만 도로명 앞에 삽입해 두 형식을 맞춘다.
    """
    if not road_prefix or not original:
        return road_prefix
    locality = None
    for content in re.findall(r"[(\[]([^)\]]*)[)\]]", original):
        match = _PAREN_LOCALITY_RE.search(content)
        if match:
            locality = match.group(0)
            break
    if not locality or locality in road_prefix:
        return road_prefix
    road_match = _ROAD_TAIL_RE.search(road_prefix)
    if not road_match:
        return road_prefix
    head = road_prefix[:road_match.start()].rstrip()
    road = road_prefix[road_match.start():].lstrip()
    return f"{head} {locality} {road}".strip()


def normalize_road_prefix(addr):
    """도로명주소 → 정규화 매칭 키. 실패 시 None.

    1) 괄호 이후/콤마 이후 상세 제거 전에 도로명+건물번호 prefix 추출
    2) 괄호 안 읍·면 표기가 도로명 본문에서 생략된 경우 보완
    3) 광역명 표기 통일
    4) 공백/특수문자 전부 제거
    """
    if not addr:
        return None
    original = str(addr).strip()
    m = _ROAD_PREFIX_RE.match(original)
    if not m:
        return None
    s = _normalize_region_prefix(_restore_parenthetical_locality(m.group(1), original))
    # 공백·쉼표·점 등 제거 (숫자/한글/영문/하이픈만 유지)
    s = re.sub(r"[^0-9가-힣A-Za-z-]", "", s)
    return s.lower() or None


# 지번주소에서 '동/읍/면/리/가 + 번지'까지만 남기기 위한 패턴:
# 예) "부산광역시 동구 초량동 1213-5 3층" → "... 초량동 1213-5"
_JIBUN_PREFIX_RE = re.compile(
    r"^(.*?[가-힣0-9]+(?:동|읍|면|리|가)\s*(?:산\s*)?\d+(?:-\d+)?)"
)

# road_address가 실제로는 지번 형식인지 판별용:
# 도로명(로/길/대로+번호)이 없고 '동/읍/면/리/가 + 숫자(-숫자)?'로 끝나는 경우
_JIBUN_LIKE_RE = re.compile(
    r"[가-힣0-9]+(?:동|읍|면|리|가)\s*(?:산\s*)?\d+(?:-\d+)?(?:번지)?\s*$"
)


def normalize_jibun_prefix(addr):
    """지번주소 → 정규화 매칭 키(jibun_norm). 실패 시 None.

    1) 괄호부 제거 → '동/읍/면/리/가 + 번지' prefix 추출
    2) 광역명 표기 통일 (도로명과 동일한 _REGION_ALIASES 재사용)
    3) 공백/특수문자 제거, 소문자 반환
    """
    if not addr:
        return None
    s = str(addr).strip()
    s = re.sub(r"[(\[].*?[)\]]", "", s)  # 괄호부(법정동 병기 등) 제거
    s = re.sub(r"번지", "", s)
    m = _JIBUN_PREFIX_RE.match(s)
    if not m:
        return None
    s = _normalize_region_prefix(m.group(1))
    s = re.sub(r"[^0-9가-힣A-Za-z-]", "", s)
    return s.lower() or None


def is_jibun_like(addr):
    """road_address가 도로명 없이 지번 형식인지 판별."""
    if not addr:
        return False
    s = str(addr).strip()
    if _ROAD_PREFIX_RE.match(s):
        return False
    return bool(_JIBUN_LIKE_RE.search(re.sub(r"[(\[].*?[)\]]", "", s)))


def get_building_jibun_key(row):
    """건물(master_buildings) 행에서 지번 매칭 키 결정.

    1순위: jibun_address → normalize_jibun_prefix
    2순위: jibun_address 없고 road_address가 지번 형식이면 road_address 사용
    3순위: None
    """
    jibun = row.get("jibun_address") if hasattr(row, "get") else row["jibun_address"]
    if jibun:
        key = normalize_jibun_prefix(jibun)
        if key:
            return key
    road = row.get("road_address") if hasattr(row, "get") else row["road_address"]
    if road and is_jibun_like(road):
        return normalize_jibun_prefix(road)
    return None


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
