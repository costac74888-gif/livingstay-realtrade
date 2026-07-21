# -*- coding: utf-8 -*-
"""
vworld_broker_fetch.py — 브이월드 부동산중개업사무소정보조회(getEBOfficeInfo) 수집 스크립트.

★ 이 스크립트는 반드시 '한국 IP'인 PC에서 실행해야 합니다.
  (브이월드가 해외 IP를 차단해 Replit 서버에서는 호출이 불가능합니다.)

사용 방법 (Windows 기준)
  1) 파이썬 설치: https://www.python.org/downloads/ → "Add python.exe to PATH" 체크 후 설치
  2) 명령 프롬프트(cmd) 열고:  pip install requests
  3) 이 파일이 있는 폴더에서:  python vworld_broker_fetch.py --key 발급받은키
  4) 완료되면 같은 폴더에 생기는 vworld_brokers.jsonl 파일을 Replit 채팅에 업로드

특징
  - 요청 사이 최소 1초 간격, 순차 호출(동시 요청 없음) — 서버에 부담을 주지 않기 위함.
  - 중간에 끊겨도 재실행하면 이어서 수집 (체크포인트: vworld_progress.json)
  - 응답의 모든 필드를 그대로 JSONL로 저장 (필드명 확정 전이므로 가공하지 않음)

주의
  - 현재 키는 '개발키'(발급일로부터 6개월 유효). 만료되거나 대량 수집이 막히면
    브이월드에서 '운영키'로 전환 신청 후 --key 값만 바꿔 재실행하면 됩니다.
"""

import argparse
import json
import os
import sys
import time

try:
    import requests
except ImportError:
    print("requests 패키지가 없습니다. 먼저 실행하세요:  pip install requests")
    sys.exit(1)

API_URL = "https://api.vworld.kr/ned/data/getEBOfficeInfo"
OUT_FILE = "vworld_brokers.jsonl"
PROGRESS_FILE = "vworld_progress.json"
NUM_ROWS = 100          # 페이지당 행 수 (서버가 무시할 수 있어 응답 실제 개수로 판단)
SLEEP_SEC = 1.0         # 요청 간 최소 간격(초) — 1초 미만으로 줄이지 마세요

# livingstay가 다루는 건물이 있는 시군구(법정동 앞 5자리) 목록.
# 51830 = 강원 양양군(휘닉스 등) 포함. 필요 시 여기에 코드를 추가하면 됩니다.
SGG_CODES = [
    "11140", "11440", "11500", "11560", "11650", "11680",
    "26110", "26140", "26170", "26200", "26230", "26350", "26470", "26500", "26530", "26710",
    "27110", "27140", "28177", "28185", "28237",
    "30110", "30170", "30200",
    "41115", "41117", "41150", "41173", "41220", "41273", "41287", "41310", "41360", "41370",
    "41390", "41463", "41480", "41500", "41570", "41591", "41595", "41597", "41670",
    "43114", "44131", "44200",
    "47150", "47770", "48170", "48240", "48310",
    "50110", "50130",
    "51110", "51130", "51150", "51170", "51230", "51720", "51760", "51770", "51830",
]


def load_progress():
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, encoding="utf-8") as f:
                return json.load(f)
        except (ValueError, OSError):
            pass
    return {"done_codes": [], "current": None, "next_page": 1}


def save_progress(p):
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(p, f, ensure_ascii=False)


def extract_items(data):
    """응답 구조가 문서와 다를 수 있어 유연하게 항목 리스트를 찾는다."""
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    for key in ("EBOfficeInfos", "eBOfficeInfos", "field", "items", "list"):
        v = data.get(key)
        if isinstance(v, list):
            return v
        if isinstance(v, dict):
            inner = extract_items(v)
            if inner:
                return inner
    for v in data.values():
        if isinstance(v, (dict, list)):
            inner = extract_items(v)
            if inner:
                return inner
    return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", required=True, help="브이월드 인증키")
    ap.add_argument("--sleep", type=float, default=SLEEP_SEC)
    args = ap.parse_args()
    sleep_sec = max(args.sleep, 1.0)  # 1초 미만 금지

    prog = load_progress()
    done = set(prog.get("done_codes", []))
    total_saved = 0
    sess = requests.Session()
    sess.headers.update({"User-Agent": "livingstay-broker-fetch/1.0"})

    out = open(OUT_FILE, "a", encoding="utf-8")
    try:
        for code in SGG_CODES:
            if code in done:
                continue
            page = prog["next_page"] if prog.get("current") == code else 1
            saved_in_code = 0
            while True:
                params = {
                    "key": args.key, "format": "json", "domain": "localhost",
                    "ldCode": code, "numOfRows": str(NUM_ROWS), "pageNo": str(page),
                }
                try:
                    r = sess.get(API_URL, params=params, timeout=30)
                except requests.RequestException as e:
                    print(f"[{code}] p{page} 네트워크 오류: {e} — 10초 후 재시도")
                    time.sleep(10)
                    continue
                if r.status_code != 200:
                    print(f"[{code}] p{page} HTTP {r.status_code}: {r.text[:200]}")
                    if r.status_code in (429, 500, 502, 503):
                        time.sleep(15)
                        continue
                    break  # 그 외 오류는 이 시군구 건너뜀
                try:
                    data = r.json()
                except ValueError:
                    print(f"[{code}] p{page} JSON 아님: {r.text[:200]}")
                    break
                items = extract_items(data)
                if page == 1 and items:
                    print(f"[{code}] 첫 행 필드: {sorted(items[0].keys())}")
                if not items:
                    break
                for it in items:
                    it["_ldCode"] = code
                    out.write(json.dumps(it, ensure_ascii=False) + "\n")
                out.flush()
                saved_in_code += len(items)
                total_saved += len(items)
                print(f"[{code}] p{page} {len(items)}건 (누적 {total_saved}건)")
                prog.update({"current": code, "next_page": page + 1})
                save_progress(prog)
                if len(items) < NUM_ROWS:
                    break
                page += 1
                time.sleep(sleep_sec)
            done.add(code)
            prog.update({"done_codes": sorted(done), "current": None, "next_page": 1})
            save_progress(prog)
            print(f"[{code}] 완료 — {saved_in_code}건")
            time.sleep(sleep_sec)
    finally:
        out.close()
    print(f"\n전체 완료! 총 {total_saved}건 → {OUT_FILE}")
    print("이 파일(vworld_brokers.jsonl)을 Replit 채팅에 업로드해 주세요.")


if __name__ == "__main__":
    main()
