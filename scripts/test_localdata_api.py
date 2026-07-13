"""임시 확인용 스크립트 — 공공데이터포털 "행정안전부_문화_숙박업 조회서비스"
(data.go.kr 서비스ID 15155124) 를 실제로 호출해 응답 원본과 필드 구조를 확인한다.

DB 적재/앱 코드와 무관한 순수 테스트용. data.go.kr 계정 공용 인증키
RTMS_SERVICE_KEY 를 환경변수에서 읽어 sync_batch.py와 동일하게 params 로 넘긴다.
키 값 자체는 절대 출력하지 않는다.

Swagger(활용신청 상세페이지)에서 확인한 스펙:
  - 엔드포인트 : https://apis.data.go.kr/1741000/lodgings/info
  - 필수 파라미터: serviceKey, pageNo, numOfRows(max 100), returnType(json/xml)
  - 자치단체 필터: cond[OPN_ATMY_GRP_CD::EQ] = 개방자치단체코드 (예: 평택시 3830000)
  - 사업장명 필터: cond[BPLC_NM::LIKE]
  - 업태 구분 필드: 응답의 BZSTAT_SE_NM(업태구분명) — 요청 필터는 없음(클라이언트에서 판별)
"""
import os
import sys
import json

import requests

KEY = os.environ.get("RTMS_SERVICE_KEY", "").strip()
if not KEY:
    print("RTMS_SERVICE_KEY 가 비어 있음 — 시크릿 확인 필요")
    sys.exit(1)

URL = "https://apis.data.go.kr/1741000/lodgings/info"
PYEONGTAEK = "3830000"  # 경기도 평택시 개방자치단체코드(OPN_ATMY_GRP_CD)

# 생활숙박업 판별용 마커(업태구분명 BZSTAT_SE_NM 값에서 탐색)
# 실제 값은 "숙박업(생활)" 형태이므로 '생활' 포함 여부로 판별한다.
LIVING_MARKERS = ["생활"]


def call(num_rows=5, page=1):
    params = {
        "serviceKey": KEY,               # sync_batch.py와 동일: 디코딩 키를 params로 전달
        "pageNo": page,
        "numOfRows": num_rows,
        "returnType": "json",
        "cond[OPN_ATMY_GRP_CD::EQ]": PYEONGTAEK,
    }
    r = requests.get(URL, params=params, timeout=20)
    return r


def get_items(data):
    try:
        item = data["response"]["body"]["items"]["item"]
        if isinstance(item, dict):
            item = [item]
        return item or []
    except Exception:
        return []


def main():
    # (2) 평택시로 numOfRows=5 실제 호출 → 응답 원본 JSON 그대로 출력
    print("=" * 78)
    print("[호출] 경기도 평택시(OPN_ATMY_GRP_CD=3830000), numOfRows=5, returnType=json")
    print("URL:", URL)
    r = call(num_rows=5, page=1)
    print("HTTP", r.status_code, "| Content-Type:", r.headers.get("Content-Type", ""))
    try:
        data = r.json()
    except Exception:
        print("\n[JSON 파싱 실패] 원본(앞 1500자):")
        print(r.text[:1500])
        return
    print("\n----- 응답 원본 JSON (전체) -----")
    print(json.dumps(data, ensure_ascii=False, indent=2))

    items = get_items(data)
    if not items:
        print("\n[알림] item 배열이 비어 있음. header:",
              json.dumps(data.get("response", {}).get("header", {}), ensure_ascii=False))
        return

    # (4) 필드 목록 전체
    print("\n" + "=" * 78)
    print(f"[필드 목록] 총 {len(items[0])}개")
    for k in items[0].keys():
        print("  -", k)

    # (3) 업태구분명(BZSTAT_SE_NM)에 어떤 값들이 있는지 확인 + 생활숙박업 존재 여부
    print("\n" + "=" * 78)
    print("[업태 구분] BZSTAT_SE_NM 값 분포 조사 — 평택시 페이지를 넓게 훑어 수집")
    from collections import Counter
    counter = Counter()
    living_examples = []
    scanned = 0
    for page in range(1, 8):  # 최대 7페이지 x 100건
        rr = call(num_rows=100, page=page)
        try:
            dd = rr.json()
        except Exception:
            break
        its = get_items(dd)
        if not its:
            break
        scanned += len(its)
        for it in its:
            v = (it.get("BZSTAT_SE_NM") or "").strip()
            counter[v] += 1
            if any(m in v for m in LIVING_MARKERS) and len(living_examples) < 2:
                living_examples.append(it)
        total = dd.get("response", {}).get("body", {}).get("totalCount", 0)
        if scanned >= int(total or 0):
            break
    print(f"조사한 행 수: {scanned}")
    print("BZSTAT_SE_NM(업태구분명) 값별 건수:")
    for v, c in counter.most_common():
        mark = "  ← 생활숙박업 판별 대상" if any(m in v for m in LIVING_MARKERS) else ""
        print(f"  {c:5d}  {v!r}{mark}")

    # (4) 생활숙박업 실제 예시 행 1~2개
    print("\n" + "=" * 78)
    if living_examples:
        print(f"[생활숙박업 예시 행 {len(living_examples)}개]")
        for ex in living_examples:
            print("-" * 60)
            print(json.dumps(ex, ensure_ascii=False, indent=2))
    else:
        print("[생활숙박업 예시 없음] 평택시 표본에서 '생활숙박'을 포함한 BZSTAT_SE_NM 값을 찾지 못함.")
        print("위 값 분포를 참고. (다른 자치단체코드로도 확인 가능)")


if __name__ == "__main__":
    main()
