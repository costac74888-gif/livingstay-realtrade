"""임시 확인용 스크립트 — 공공데이터포털 "행정안전부_문화_숙박업 조회서비스"
(data.go.kr 서비스ID 15155124) 를 실제로 호출해 응답 원본과 필드 구조를 확인한다.

DB 적재/앱 코드와 무관한 순수 테스트용. LOCALDATA_SERVICE_KEY(발급 인증키)를
환경변수에서 읽어 사용하며, 키 값 자체는 절대 출력하지 않는다.

LOCALDATA(localdata.go.kr)는 2026-04-16 폐쇄되어 data.go.kr로 이관됨. 정확한
엔드포인트/파라미터가 확실치 않아 후보를 순차 호출하며 무엇이 응답하는지 확인한다.
"""
import os
import sys
import json
import xml.etree.ElementTree as ET
from urllib.parse import urlencode, quote

import requests

KEY = os.environ.get("LOCALDATA_SERVICE_KEY", "").strip()
if not KEY:
    print("LOCALDATA_SERVICE_KEY 가 비어 있음 — 시크릿 확인 필요")
    sys.exit(1)

PYEONGTAEK = "3830000"  # 경기도 평택시 개방자치단체코드(opnSfTeamCode) 후보
NUM = 5

# (설명, 메서드, base_url, 파라미터dict, 키파라미터명, 키를 이미인코딩된값으로_raw붙일지)
CANDIDATES = [
    # 1) data.go.kr 표준(가장 유력): serviceKey + numOfRows/pageNo + type
    ("A. apis.data.go.kr/1741000/StayBusiness/getStayBusiness (json)",
     "https://apis.data.go.kr/1741000/StayBusiness/getStayBusiness",
     {"pageNo": 1, "numOfRows": NUM, "type": "json", "opnSfTeamCode": PYEONGTAEK},
     "serviceKey"),
    ("B. apis.data.go.kr/1741000/StayBusiness/getStayBusiness (xml)",
     "https://apis.data.go.kr/1741000/StayBusiness/getStayBusiness",
     {"pageNo": 1, "numOfRows": NUM, "opnSfTeamCode": PYEONGTAEK},
     "serviceKey"),
    # 2) 레거시 localdata openDataApi 형식(참고: 시스템 폐쇄됨)
    ("C. localdata openDataApi 03_11_03_P (json)",
     "http://www.localdata.go.kr/platform/rest/TO0/openDataApi",
     {"opnSvcId": "03_11_03_P", "pageIndex": 1, "pageSize": NUM,
      "resultType": "json", "localCode": PYEONGTAEK},
     "authKey"),
    ("D. localdata openDataApi 07_24_04_P (json)",
     "http://www.localdata.go.kr/platform/rest/TO0/openDataApi",
     {"opnSvcId": "07_24_04_P", "pageIndex": 1, "pageSize": NUM,
      "resultType": "json", "localCode": PYEONGTAEK},
     "authKey"),
]

LODGING_MARKERS = ["생활숙박", "생활 숙박", "분양형", "콘도"]


def try_call(label, url, params, key_param):
    print("\n" + "=" * 78)
    print(label)
    print("URL:", url)
    print("params:", {k: v for k, v in params.items()})
    # 키를 그대로(디코딩된 키로 가정) params 로 넘겨 requests가 인코딩하게 한다.
    p = dict(params)
    p[key_param] = KEY
    for tag, do_raw in [("키=params(자동인코딩)", False), ("키=raw(이미인코딩 가정)", True)]:
        try:
            if do_raw:
                qs = urlencode({k: v for k, v in params.items()})
                full = f"{url}?{key_param}={KEY}&{qs}"
                r = requests.get(full, timeout=20)
            else:
                r = requests.get(url, params=p, timeout=20)
            ct = r.headers.get("Content-Type", "")
            body = r.text
            print(f"\n  [{tag}] HTTP {r.status_code} | Content-Type: {ct} | len={len(body)}")
            snippet = body[:1200].replace("\n", " ")
            print("  RAW(앞 1200자):", snippet)
            if r.status_code == 200 and body.strip():
                return r
        except Exception as e:
            print(f"  [{tag}] 예외: {type(e).__name__}: {str(e)[:200]}")
    return None


def analyze(r):
    body = r.text.strip()
    print("\n  ---- 응답 분석 ----")
    data = None
    if body[:1] in "{[":
        try:
            data = json.loads(body)
            print("  형식: JSON")
        except Exception as e:
            print("  JSON 파싱 실패:", e)
    if data is None:
        try:
            root = ET.fromstring(body)
            print("  형식: XML, 루트 태그:", root.tag)
            # 첫 leaf row 후보 필드 수집
            fields = {}
            for el in root.iter():
                if list(el):  # 컨테이너면 스킵
                    continue
                if el.tag not in fields and el.text and el.text.strip():
                    fields[el.tag] = el.text.strip()
            print("  필드 예시(태그=값):")
            for k, v in list(fields.items())[:40]:
                print(f"    {k} = {v[:60]}")
        except Exception as e:
            print("  XML 파싱도 실패:", str(e)[:200])
        return
    # JSON row 찾기
    def find_rows(obj):
        if isinstance(obj, list) and obj and isinstance(obj[0], dict):
            return obj
        if isinstance(obj, dict):
            for v in obj.values():
                rows = find_rows(v)
                if rows:
                    return rows
        return None
    rows = find_rows(data)
    if not rows:
        print("  행 배열을 찾지 못함. 최상위 키:", list(data.keys()) if isinstance(data, dict) else type(data))
        print("  일부:", json.dumps(data, ensure_ascii=False)[:800])
        return
    print(f"  행 {len(rows)}개, 필드 {len(rows[0])}개")
    print("  필드 목록:", list(rows[0].keys()))
    # 생활숙박/분양형/콘도 값 탐색
    hits = []
    for row in rows:
        for k, v in row.items():
            if isinstance(v, str) and any(m in v for m in LODGING_MARKERS):
                hits.append((k, v, row))
                break
    if hits:
        print(f"\n  생활숙박/분양형/콘도 매칭 행 {len(hits)}개 — 예시:")
        for k, v, row in hits[:2]:
            print(f"    [매칭필드 {k}={v}]")
            print("    ", json.dumps(row, ensure_ascii=False)[:600])
    else:
        print("\n  이 페이지에는 생활숙박/분양형/콘도 값이 없음. 첫 행 원본:")
        print("   ", json.dumps(rows[0], ensure_ascii=False)[:600])


def main():
    for label, url, params, key_param in CANDIDATES:
        r = try_call(label, url, params, key_param)
        if r is not None:
            analyze(r)


if __name__ == "__main__":
    main()
