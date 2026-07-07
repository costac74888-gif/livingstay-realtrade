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


class BjdongMap:
    """법정동코드 전체자료(code.go.kr) 로 만든 매핑 테이블"""

    def __init__(self, csv_path: str):
        df = pd.read_csv(csv_path, dtype=str, encoding="cp949")
        df = df[df["폐지여부"] == "존재"].copy()
        df["sggCd"] = df["법정동코드"].str[:5]
        df["bjdongCd"] = df["법정동코드"].str[5:10]
        self.df = df[["sggCd", "bjdongCd", "시도명", "시군구명", "읍면동명"]]

    def find_sgg_cd(self, si_do: str, sgg_nm: str) -> str | None:
        cand = self.df[(self.df["시도명"] == si_do) & (self.df["시군구명"] == sgg_nm)]
        if cand.empty:
            return None
        return cand.iloc[0]["sggCd"]

    def find_bjdong_cd(self, sgg_cd: str, umd_nm: str) -> str | None:
        cand = self.df[(self.df["sggCd"] == sgg_cd) & (self.df["읍면동명"] == umd_nm)]
        if cand.empty:
            cand = self.df[(self.df["sggCd"] == sgg_cd) & (self.df["읍면동명"].str.startswith(umd_nm[:2]))]
        if cand.empty:
            return None
        return cand.iloc[0]["bjdongCd"]


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
