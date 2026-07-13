# -*- coding: utf-8 -*-
"""
address_utils.py — 주소 변환 유틸 2가지

1) road_to_jibun(): 도로명주소 → 지번주소 변환
   행정안전부 도로명주소 API(juso.go.kr) 사용. 무료, 승인키 필요.
   https://www.juso.go.kr/addrlink/openApi/searchApi.do 에서 발급.

2) BjdongMap: 법정동코드 매핑표 (code.go.kr '법정동코드 전체자료.txt/csv' 다운로드)
   umdNm(읍면동명 텍스트) → bjdongCd(법정동코드 5자리) 변환에 사용.
   시군구명 텍스트 → sggCd(시군구코드 5자리) 변환에도 사용.
"""

import os
import re
import zipfile
import requests
import pandas as pd

JUSO_API_KEY = os.environ.get("JUSO_API_KEY", "")
JUSO_URL = "https://business.juso.go.kr/addrlink/addrLinkApi.do"


def road_to_jibun(road_address: str) -> dict | None:
    """
    도로명주소 문자열을 넣으면 지번주소 관련 정보를 반환한다.
    반환 예: {"siNm":"경기도","sggNm":"가평군","emdNm":"청평면","lnbrMnnm":"123","lnbrSlno":"4", ...}
    """
    # 마스터 주소에는 도로명 뒤에 층수/동/법정동 꼬리표가 붙어있는 경우가 많다.
    # 예) "경기도 수원시 팔달구 갓매산로19번길 27-4, 2~9층 (매산로2가)"  ← 쉼표로 시작
    #     "서울 강서구 마곡중앙로 40(마곡동)"                          ← 쉼표 없이 괄호만
    # JUSO는 이런 꼬리표가 있으면 totalCount=0을 반환하므로 순수 도로명만 남긴다.
    keyword = road_address.split(",")[0]
    keyword = re.sub(r"\([^)]*\)\s*$", "", keyword).strip()  # 끝의 (법정동) 괄호 제거
    params = {
        "confmKey": JUSO_API_KEY,
        "currentPage": 1,
        "countPerPage": 1,
        "keyword": keyword,
        "resultType": "json",
    }
    resp = requests.get(JUSO_URL, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    juso_list = data.get("results", {}).get("juso", [])
    if not juso_list:
        return None
    return juso_list[0]  # rn(도로명), emdNm(법정읍면동), lnbrMnnm(지번본번), lnbrSlno(지번부번), admCd(행정동코드) 등


def normalize_umd_nm(s: str) -> str:
    """읍/면/동(+리) 이름을 매칭키로 정규화하는 **유일한** 표준 함수.

    RTMS·JUSO는 면/리 지역을 '봉평면 면온리'처럼 공백을 넣어 주지만, 마스터 저장·
    매칭은 공백 없는 '봉평면면온리'로 통일한다. sync_batch / discover_new_buildings /
    submit-building / request-correction / find_bjdong_cd — 동이름을 비교하거나 키로
    쓰는 모든 코드는 반드시 이 함수 하나만 써야 한다(각자 .replace(" ","") 하지 말 것).
    한쪽만 규칙이 어긋나면 면/리 지역에서 조용히 매칭 실패가 재발한다.
    """
    return "".join((s or "").split())


# 시도 표기 편차('서울' vs '서울특별시', '강원도' vs '강원특별자치도' 등)를 흡수하기 위한
# 공통 규칙. 지도(/api/buildings-geo)와 게시판(/api/transactions)이 반드시 이 한 쌍을
# 함께 써야 두 API의 지역 매칭이 어긋나지 않는다.
SIDO_SUFFIX_RE = r"(특별자치도|특별자치시|특별시|광역시|도|시)$"


def sido_core(si_do: str) -> str:
    """시도 이름에서 행정접미사를 떼어낸 '핵심 이름'을 반환한다(예: '서울특별시'→'서울').

    긴 접미사부터 매칭되도록 정규식 순서를 잡아 '서울특별시'에서 '시'만 잘리는 일을 막는다.
    """
    return re.sub(SIDO_SUFFIX_RE, "", (si_do or "").strip())


def sido_match_clause(column_expr: str) -> str:
    """주어진 시도 컬럼/식을 코어 이름으로 정규화해 %s 파라미터와 정확 비교하는 SQL 조건.

    파라미터에는 반드시 sido_core(si_do) 결과를 넣어야 한다. 정규식은 코드 상수라
    인젝션 위험이 없으며, 넘어오는 시도 값은 여전히 %s 로 바인딩된다.
    예) sido_match_clause("si_do")                       → 게시판(transactions.si_do)
        sido_match_clause("split_part(sgg_text,' ',1)")  → 지도(master_buildings.sgg_text 첫 토큰)
    """
    return f"regexp_replace({column_expr}, '{SIDO_SUFFIX_RE}', '') = %s"


class BjdongMap:
    """
    법정동코드 전체자료(code.go.kr) 로 만든 매핑 테이블.

    실제 파일 형식 (주의: CSV가 아니라 탭 구분 .txt, 컬럼 3개뿐)
    ------------------------------------------------------------
    법정동코드(10자리)   법정동명(시도+시군구+읍면동이 공백으로 합쳐진 한 컬럼)   폐지여부
    예) 4111000000   경기도 수원시            존재   ← 시군구 레벨(구 없는 상위 코드, 조회 대상 아님)
        4111100000   경기도 수원시 장안구      존재   ← 실제 조회 대상(구 단위)
        4111010100   경기도 수원시 장안구 파장동  존재   ← 읍면동 레벨

    세종특별자치시처럼 구 없이 시도=시군구가 같은 경우도 있어(코드가 '000'으로 안 끝남),
    단순히 토큰 개수로 구분하지 않고 "이 이름으로 시작하는 더 하위 항목이 있는가"로
    실제 조회 가능한 최말단 시군구만 골라낸다.
    """

    @staticmethod
    def _resolve_path(path: str) -> str:
        """code.go.kr에서 받은 파일이 .zip 그대로여도 자동으로 압축을 풀어서 .txt 경로를 반환한다."""
        if not path.lower().endswith(".zip"):
            return path
        extract_dir = path[:-4] + "_extracted"
        os.makedirs(extract_dir, exist_ok=True)
        with zipfile.ZipFile(path) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith((".txt", ".csv"))]
            if not names:
                raise FileNotFoundError(f"{path} 안에 .txt/.csv 파일이 없습니다")
            zf.extract(names[0], extract_dir)
            return os.path.join(extract_dir, names[0])

    def __init__(self, csv_path: str):
        csv_path = self._resolve_path(csv_path)
        df = pd.read_csv(csv_path, sep="\t", dtype=str, encoding="cp949")
        df = df[df["폐지여부"] == "존재"].copy()
        df["sggCd"] = df["법정동코드"].str[:5]
        df["bjdongCd"] = df["법정동코드"].str[5:10]
        self.df = df[["법정동코드", "법정동명", "sggCd", "bjdongCd"]]

        sgg_rows = self.df[self.df["bjdongCd"] == "00000"].copy()
        # 시도 전체를 가리키는 상위 placeholder(예: '서울특별시' 단독, sggCd가 '000'으로 끝남) 제외
        sgg_rows = sgg_rows[~sgg_rows["sggCd"].str.endswith("000")]

        names = sgg_rows["법정동명"].tolist()
        name_set = set(names)

        def has_child(name):
            # 이 이름 뒤에 공백+무언가가 붙은 더 하위 항목이 있으면 이건 상위(구가 있는 시) → 조회 대상 아님
            return any((n != name) and n.startswith(name + " ") for n in name_set)

        leaf_rows = sgg_rows[~sgg_rows["법정동명"].apply(has_child)]

        self._sgg_text_map = dict(zip(leaf_rows["sggCd"], leaf_rows["법정동명"]))
        self._all_sgg_rows = sgg_rows  # 상위코드 포함 전체 (find_sgg_cd에서 이름 매칭용)

    def find_sgg_cd(self, si_do: str, sgg_nm: str) -> str | None:
        """'경기도'+'수원시' 처럼 넘어와도, 실제로는 '경기도 수원시 장안구'급 leaf 코드가 필요할 수 있어
        일단 이름이 포함되는 leaf 항목을 우선 반환한다."""
        target_prefix = f"{si_do} {sgg_nm}".strip() if sgg_nm else si_do
        # leaf 중 정확히 일치
        for cd, name in self._sgg_text_map.items():
            if name == target_prefix:
                return cd
        # leaf 중 이 이름으로 시작하는 첫 항목 (구 단위까지 내려가야 하는 경우)
        for cd, name in self._sgg_text_map.items():
            if name.startswith(target_prefix):
                return cd
        return None

    def find_bjdong_cd(self, sgg_cd: str, umd_nm: str) -> str | None:
        """
        umd_nm은 '청운동'처럼 동 하나일 수도, '사천면 사천진리'처럼 면+리가
        합쳐진 형태일 수도 있다(RTMS가 면/리 지역에서 이렇게 줌 — 강릉 사례로 확인됨).
        게다가 호출자마다 표기가 다르다:
          - sync/discover 는 RTMS 원본('봉평면 면온리', 공백 있음)을 넘기고
          - cleanup/재검증 은 master에 저장된 정규화값('봉평면면온리', 공백 없음)을 넘긴다.
        그래서 **양쪽 다 공백을 제거**한 뒤, "법정동명의 뒤쪽 토큰들을 공백 없이 이어붙인
        후보(뒤에서 1·2·3토큰)"와 정확히 일치하는지 비교한다.
        - 마지막 토큰 하나만 비교하면 면+리 지역에서 실패 → 뒤쪽 여러 토큰 조합까지 본다.
        - 문자열 endswith 비교는 '교동'이 '서교동'에 걸리는 접미사 오매칭을 낸다 →
          토큰 경계를 지키는 '조합 == 질의' 정확일치라 오매칭을 막는다.
        """
        cand = self.df[(self.df["sggCd"] == sgg_cd) & (self.df["bjdongCd"] != "00000")]
        q = normalize_umd_nm(umd_nm)
        if not q:
            return None

        def tail_matches(name: str) -> bool:
            toks = name.split()
            for k in range(1, min(3, len(toks)) + 1):
                if "".join(toks[-k:]) == q:
                    return True
            return False

        match = cand[cand["법정동명"].apply(tail_matches)]
        if match.empty:
            return None
        return match.iloc[0]["bjdongCd"]

    def all_sgg_codes(self) -> list[str]:
        """전국 실제 조회 가능한(구가 있으면 구 단위까지 내려간) 시군구 코드 목록"""
        return sorted(self._sgg_text_map.keys())

    def sgg_text(self, sgg_cd: str) -> str | None:
        """시군구코드 → '경기도 수원시 장안구' 형태 텍스트"""
        return self._sgg_text_map.get(sgg_cd)


# ─────────────────────────────────────────────────────────────────────────────
# 지자체 담당부서·연락처 매칭
#   lodging_authority_contacts.region_name_raw(엑셀 원본, 예: "경기도광주시",
#   "광주시남구", "강릉시", "진주시(중복)", "경기도")
#     ↔ master_buildings.sgg_text(예: "경기도 평택시", "광주광역시 남구",
#        "경기도 수원시 장안구", "대구광역시 동구")
#
# 정확도가 최우선. 매칭이 모호하면(후보 2개 이상 & 값이 서로 다름) 추측하지 않고
# None 을 돌려준다("확인중"이 틀린 연락처보다 낫다).
# ─────────────────────────────────────────────────────────────────────────────

# 시도 이름의 모든 표기를 하나의 '캐논(핵심 이름)'으로 통일한다. 양쪽(엑셀 원본 /
# 마스터 sgg_text)을 같은 캐논으로 환산해야 "충남"(엑셀)과 "충청남도"(마스터)가,
# "대구시"(엑셀)와 "대구광역시"(마스터)가 같은 시도로 매칭된다.
SIDO_CANON = {
    "서울": "서울", "서울시": "서울", "서울특별시": "서울",
    "부산": "부산", "부산시": "부산", "부산광역시": "부산",
    "대구": "대구", "대구시": "대구", "대구광역시": "대구",
    "인천": "인천", "인천시": "인천", "인천광역시": "인천",
    "광주": "광주", "광주시": "광주", "광주광역시": "광주",
    "대전": "대전", "대전시": "대전", "대전광역시": "대전",
    "울산": "울산", "울산시": "울산", "울산광역시": "울산",
    "세종": "세종", "세종시": "세종", "세종특별자치시": "세종",
    "경기": "경기", "경기도": "경기",
    "강원": "강원", "강원도": "강원", "강원특별자치도": "강원",
    "충북": "충북", "충청북도": "충북",
    "충남": "충남", "충청남도": "충남",
    "전북": "전북", "전라북도": "전북", "전북특별자치도": "전북",
    "전남": "전남", "전라남도": "전남",
    "경북": "경북", "경상북도": "경북",
    "경남": "경남", "경상남도": "경남",
    "제주": "제주", "제주도": "제주", "제주특별자치도": "제주",
}

# 엑셀 원본 앞부분에서 떼어낼 시도 표기(긴 것부터). 붙여쓰기('경기도광주시')·
# 광역시 축약('대구시')·풀네임('인천광역시') 모두 커버한다.
_SIDO_PREFIXES = sorted(SIDO_CANON.keys(), key=len, reverse=True)


def _strip_region_parens(s: str) -> str:
    """'진주시(중복)' → '진주시' 처럼 괄호 주석(반각/전각)을 제거한다."""
    return re.sub(r"[\(（][^)）]*[\)）]", "", s or "")


def _looks_like_sgg(rest: str) -> bool:
    """시도를 떼어낸 나머지가 시군구/구로 보이는지(=시/군/구로 끝나고 2글자 이상).

    '제주시'에서 '제주'를 떼면 '시'만 남는데 이건 시군구가 아니므로 시도 분리를
    거부해야 한다(제주시는 '제주도'가 아니라 제주도 안의 '제주시' 시군구다)."""
    return len(rest) >= 2 and rest[-1] in ("시", "군", "구")


def parse_authority_region(raw: str):
    """엑셀 지자체 원본 → (시도캐논 or None, 시군구핵심 문자열).

    - 시도가 안 붙은 행('강릉시')        → (None, '강릉시')
    - 시도+시군구('경기도광주시')        → ('경기', '광주시')
    - 광역시+구('대구시동구','광주시남구') → ('대구','동구'), ('광주','남구')
    - 시도 전용 행('경기도','부산시')    → ('경기',''), ('부산','')  ← 폴백용
    """
    s = _strip_region_parens(raw)
    s = "".join(s.split())  # 모든 공백 제거
    for pref in _SIDO_PREFIXES:
        if s.startswith(pref):
            rest = s[len(pref):]
            # 나머지가 비었으면(시도 전용 폴백행) 또는 시군구로 보이면 시도 분리 확정.
            # 아니면(예: '제주시'→'시') 이 접두어는 오분리이므로 건너뛴다.
            if rest == "" or _looks_like_sgg(rest):
                return SIDO_CANON[pref], rest
    return None, s


def parse_master_region(sgg_text: str):
    """마스터 sgg_text → (시도캐논, [로컬후보...] 구체→상위 순).

    - '경기도 평택시'        → ('경기', ['평택시'])
    - '대구광역시 동구'      → ('대구', ['동구'])
    - '경기도 수원시 장안구' → ('경기', ['수원시장안구', '수원시'])   ← 구 전용 없으면 시로 폴백
    - '서울 강남구'          → ('서울', ['강남구'])
    """
    toks = (sgg_text or "").split()
    if not toks:
        return None, []
    sido = SIDO_CANON.get(toks[0]) or sido_core(toks[0])
    rest = toks[1:]
    if not rest:
        return sido, []
    if len(rest) >= 2:
        return sido, ["".join(rest), rest[0]]
    return sido, [rest[0]]


def build_authority_index(rows):
    """담당부서 매칭용 인덱스를 만든다.

    rows: [{'region_name_raw','dept','phone'}, ...] (DB lodging_authority_contacts 또는 엑셀)
    반환: dict(specific / nosido / fallback)
      - specific[(sido, local)] = set of (dept, phone)   시도+시군구가 명시된 행
      - nosido[local]           = set of (sido or None, dept, phone)  시도 없는 행
      - fallback[sido]          = set of (dept, phone)   시도 전용 대표행
    값이 set 이라 완전히 동일한 중복행('진주시' vs '진주시(중복)')은 자동으로 1개로 합쳐진다.
    """
    specific, nosido, fallback = {}, {}, {}
    for r in rows:
        sido, local = parse_authority_region(r.get("region_name_raw"))
        dept = r.get("dept")
        phone = r.get("phone")
        if local == "":
            if sido:
                fallback.setdefault(sido, set()).add((dept, phone))
        elif sido:
            specific.setdefault((sido, local), set()).add((dept, phone))
        else:
            nosido.setdefault(local, set()).add((sido, dept, phone))
    return {"specific": specific, "nosido": nosido, "fallback": fallback}


def match_authority_contact(sgg_text: str, index: dict):
    """master_buildings.sgg_text 하나를 담당부서 인덱스와 매칭.

    반환: (dept, phone, source)
      매칭 성공: source = 'exact'    → 시군구 전용 행에서 온 정확 매칭
                 source = 'fallback' → 해당 시군구 전용 행이 없어 시/도 대표행으로 채운 값
      매칭 실패: dept=phone=None,  source = 'no_master' | 'no_match' | 'ambiguous'

    화면(B화면 행정운영 표)은 source=='fallback'일 때만 "(시/도 대표)" 꼬리표를 붙인다.
    구체(시군구) 매칭을 먼저 시도하고, 없을 때만 시도 전용(fallback)으로 내려간다.
    후보가 서로 다른 값 2개 이상이면 추측하지 않고 None(=확인중).
    """
    sido, cands = parse_master_region(sgg_text)
    if not cands and not sido:
        return (None, None, "no_master")

    specific = index["specific"]
    nosido = index["nosido"]
    fallback = index["fallback"]

    for local in cands:
        # (a) 시도+시군구 정확 매칭
        vals = specific.get((sido, local)) if sido else None
        if vals:
            if len(vals) == 1:
                dept, phone = next(iter(vals))
                return (dept, phone, "exact")
            return (None, None, "ambiguous")
        # (b) 시도가 생략된 엑셀행(시군구명만)과 매칭
        vals = nosido.get(local)
        if vals:
            distinct = {(d, p) for (_s, d, p) in vals}
            if len(distinct) == 1:
                dept, phone = next(iter(distinct))
                return (dept, phone, "exact")
            return (None, None, "ambiguous")

    # (c) 시군구 전용 행이 없을 때만 시도 대표(폴백) 사용
    if sido and sido in fallback:
        vals = fallback[sido]
        if len(vals) == 1:
            dept, phone = next(iter(vals))
            return (dept, phone, "fallback")
        return (None, None, "ambiguous")

    return (None, None, "no_match")


def parse_jibun(jibun: str):
    """'751-3' → ('0','751','3')  /  '산 12-1' → ('1','12','1')"""
    jibun = jibun.strip()
    plat_gb = "1" if jibun.startswith("산") else "0"
    jibun = jibun.replace("산", "").strip()
    if "-" in jibun:
        bun, ji = jibun.split("-", 1)
    else:
        bun, ji = jibun, "0"
    bun = re.sub(r"[^0-9]", "", bun) or "0"
    ji = re.sub(r"[^0-9]", "", ji) or "0"
    return plat_gb, bun, ji
