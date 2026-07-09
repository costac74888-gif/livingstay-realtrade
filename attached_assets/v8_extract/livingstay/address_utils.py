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

JUSO_API_KEY = os.environ["JUSO_API_KEY"]
JUSO_URL = "https://business.juso.go.kr/addrlink/addrLinkApi.do"


def road_to_jibun(road_address: str) -> dict | None:
    """
    도로명주소 문자열을 넣으면 지번주소 관련 정보를 반환한다.
    반환 예: {"siNm":"경기도","sggNm":"가평군","emdNm":"청평면","lnbrMnnm":"123","lnbrSlno":"4", ...}
    """
    params = {
        "confmKey": JUSO_API_KEY,
        "currentPage": 1,
        "countPerPage": 1,
        "keyword": road_address,
        "resultType": "json",
    }
    resp = requests.get(JUSO_URL, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    juso_list = data.get("results", {}).get("juso", [])
    if not juso_list:
        return None
    return juso_list[0]  # rn(도로명), emdNm(법정읍면동), lnbrMnnm(지번본번), lnbrSlno(지번부번), admCd(행정동코드) 등


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
        마지막 토큰 하나만 비교하면 면+리 지역에서 매칭 실패하므로,
        "법정동명이 umd_nm으로 끝나는가"로 비교해 두 경우 다 정확히 잡는다.
        """
        cand = self.df[(self.df["sggCd"] == sgg_cd) & (self.df["bjdongCd"] != "00000")]
        umd_nm = umd_nm.strip()

        match = cand[cand["법정동명"].str.endswith(umd_nm)]
        if match.empty:
            # 공백 유무 등 미세한 표기 차이 대비 — 마지막 토큰만이라도 일치하는지 완화 매칭
            last_token = umd_nm.split()[-1] if " " in umd_nm else umd_nm
            match = cand[cand["법정동명"].str.split().str[-1] == last_token]
        if match.empty:
            match = cand[cand["법정동명"].str.split().str[-1].str.startswith(umd_nm[:2], na=False)]
        if match.empty:
            return None
        return match.iloc[0]["bjdongCd"]

    def all_sgg_codes(self) -> list[str]:
        """전국 실제 조회 가능한(구가 있으면 구 단위까지 내려간) 시군구 코드 목록"""
        return sorted(self._sgg_text_map.keys())

    def sgg_text(self, sgg_cd: str) -> str | None:
        """시군구코드 → '경기도 수원시 장안구' 형태 텍스트"""
        return self._sgg_text_map.get(sgg_cd)


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
