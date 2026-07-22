# -*- coding: utf-8 -*-
"""
sync_brhub.py — 건축HUB 표제부(getBrTitleInfo)로 전국 '집합건물 + 숙박시설'을
자동 발견하여 master_buildings에 반영하는 배치.

파이프라인 (사용자 지시 2026-07-22):
  1) 법정동코드(bjdong_codes.json, 읍면동+리 레벨 20,276개)를 순회하며
     시군구코드+법정동코드로 표제부 전체 건물 조회 (bun/ji 비움)
     ※ 총괄표제부(getBrRecapTitleInfo)는 누락이 심각해(해운대 우동: recap 89건·숙박 0건
       vs 표제부 3,099건·집합+숙박 21건) 표제부 전수 스캔으로 결정 (2026-07-22 실측)
  2) 1차 필터: 대장구분 '집합' + 주용도/기타용도에 '숙박' 포함이면 호실수 무관 전부 수집
  3) 텍스트 분류(building_registry._find_categories 재사용 — 관광숙박시설 함정 회피):
     '생활'/'호텔'/'콘도'/병기('생활·호텔' 등). 숙박이지만 판정불가 → lodging_type=NULL(미분류)
     + lodging_type_detail에 원문 저장 (이후 층별개요 2차 검증 대상)
  4) 중복 제외: 기존 master_buildings와 (sgg_cd,umd_nm,jibun) / 도로명 정규화 키 /
     지번 정규화 키 3중 비교 (메모리 셋, 실행 중 신규분도 누적)
  5) source='brhub_bulk'로 INSERT

운영 특성 (숙박업 API 교훈 반영):
  - 완료 판정은 요청 numOfRows가 아닌 '실제 응답 건수' 기준
  - 체크포인트: app_meta['brhub_progress'] = {"idx": 다음 처리할 dongs 인덱스, ...}
    → 재실행 시 이어서 진행
  - 일일 소프트캡(기본 8,000호출) 도달 시 스스로 중단 — 다음날 재실행
  - 페이지 간 딜레이 기본 0.2초

사용:
  python -u sync_brhub.py                    # 이어서 실행 (일일캡까지)
  python -u sync_brhub.py --limit 30         # 법정동 30개만 (파일럿)
  python -u sync_brhub.py --dry-run          # DB에 안 쓰고 발견 내역만 출력
  python -u sync_brhub.py --daily-cap 5000 --sleep 0.3
"""

import argparse
import json
import os
import sys
import time
from datetime import date

import requests

from db import get_conn
from addr_norm import normalize_road_prefix, normalize_jibun_prefix
from address_utils import normalize_umd_nm
from building_registry import _find_categories, _combine_labels

API_URL = "https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo"
KEY_ENV = "DATA_GO_KR_BROKER_API_KEY"
CODES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bjdong_codes.json")
PROGRESS_KEY = "brhub_progress"
NUM_ROWS = 100


def _load_codes():
    with open(CODES_FILE, encoding="utf-8") as f:
        data = json.load(f)
    return data["sgg"], data["dongs"]  # sgg: {코드5: "시도 시군구"}, dongs: [[코드10, 법정동명], ...]


def _get_progress(cur):
    cur.execute("SELECT value FROM app_meta WHERE key=%s", (PROGRESS_KEY,))
    row = cur.fetchone()
    if row and row["value"]:
        try:
            return json.loads(row["value"])
        except ValueError:
            pass
    return {"idx": 0, "calls_date": "", "calls_today": 0, "found_total": 0}


def _save_progress(conn, cur, prog):
    cur.execute("""
        INSERT INTO app_meta (key, value) VALUES (%s, %s)
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
    """, (PROGRESS_KEY, json.dumps(prog, ensure_ascii=False)))
    conn.commit()


def _jibun_from_bunji(bun, ji):
    """'0012','0003' → '12-3' / ji가 0이면 '12'."""
    try:
        b = int(str(bun or "0"))
        j = int(str(ji or "0"))
    except ValueError:
        return None
    if b <= 0:
        return None
    return f"{b}-{j}" if j > 0 else str(b)


def _fetch_page(key, sgg, bjd, page):
    params = {"serviceKey": key, "sigunguCd": sgg, "bjdongCd": bjd,
              "numOfRows": str(NUM_ROWS), "pageNo": str(page), "_type": "json"}
    r = requests.get(API_URL, params=params, timeout=30)
    r.raise_for_status()
    d = r.json()
    header = d.get("response", {}).get("header", {})
    if header.get("resultCode") not in ("00", None):
        raise RuntimeError(f"API 오류 {header.get('resultCode')}: {header.get('resultMsg')}")
    body = d.get("response", {}).get("body", {}) or {}
    items = body.get("items") or {}
    item = items.get("item") if isinstance(items, dict) else None
    if item is None:
        return []
    return item if isinstance(item, list) else [item]


def _load_existing_keys(cur):
    """기존 master_buildings의 중복 판별 키 3종 셋."""
    cur.execute("SELECT sgg_cd, umd_nm, jibun, road_address, jibun_address FROM master_buildings")
    triple, roads, jibuns = set(), set(), set()
    for r in cur.fetchall():
        if r["sgg_cd"] and r["umd_nm"] and r["jibun"]:
            triple.add((r["sgg_cd"], normalize_umd_nm(r["umd_nm"]), r["jibun"]))
        rn = normalize_road_prefix(r["road_address"])
        if rn:
            roads.add(rn)
        jn = normalize_jibun_prefix(r["jibun_address"] or r["road_address"])
        if jn:
            jibuns.add(jn)
    return triple, roads, jibuns


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="이번 실행에서 처리할 법정동 수 (0=일일캡까지)")
    ap.add_argument("--daily-cap", type=int, default=8000)
    ap.add_argument("--sleep", type=float, default=0.2)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--reset", action="store_true", help="체크포인트 초기화 후 처음부터")
    ap.add_argument("--start-idx", type=int, default=-1, help="(테스트용) 이번 실행만 이 인덱스부터")
    args = ap.parse_args()

    key = os.environ.get(KEY_ENV)
    if not key:
        print(f"환경변수 {KEY_ENV} 없음"); sys.exit(1)

    sgg_map, dongs = _load_codes()
    conn = get_conn()
    cur = conn.cursor()
    prog = {"idx": 0, "calls_date": "", "calls_today": 0, "found_total": 0} if args.reset else _get_progress(cur)
    if args.start_idx >= 0:
        prog["idx"] = args.start_idx

    today = date.today().isoformat()
    if prog.get("calls_date") != today:
        prog["calls_date"] = today
        prog["calls_today"] = 0
    if prog["calls_today"] >= args.daily_cap:
        print(f"오늘 호출 {prog['calls_today']}회 — 일일캡({args.daily_cap}) 도달, 내일 재실행하세요.")
        return

    triple, roads, jibuns = _load_existing_keys(cur)
    print(f"[시작] 법정동 {prog['idx']}/{len(dongs)}부터, 오늘 호출 {prog['calls_today']}/{args.daily_cap}, "
          f"기존 건물 키 {len(triple)}개")

    processed = 0
    found_run = 0
    counts = {"생활": 0, "호텔": 0, "콘도": 0, "병기": 0, "미분류": 0}

    while prog["idx"] < len(dongs):
        if args.limit and processed >= args.limit:
            break
        if prog["calls_today"] >= args.daily_cap:
            print(f"일일캡({args.daily_cap}) 도달 — 체크포인트 저장 후 중단. 내일 이어서 실행하세요.")
            break

        code, dong_name = dongs[prog["idx"]]
        sgg_cd, bjd_cd = code[:5], code[5:]
        sgg_text = sgg_map.get(sgg_cd, "")
        umd_raw = dong_name[len(sgg_text):].strip() if sgg_text and dong_name.startswith(sgg_text) else dong_name.split()[-1]

        page = 1
        dong_error = False
        while True:
            try:
                items = _fetch_page(key, sgg_cd, bjd_cd, page)
            except Exception as e:
                print(f"  [{dong_name}] p{page} 오류: {repr(e)[:160]} — 15초 후 1회 재시도")
                time.sleep(15)
                try:
                    items = _fetch_page(key, sgg_cd, bjd_cd, page)
                except Exception as e2:
                    print(f"  [{dong_name}] 재시도 실패({repr(e2)[:120]}) — 이 법정동은 다음 실행 때 재처리")
                    dong_error = True
                    break
            prog["calls_today"] += 1

            for it in items:
                if (it.get("regstrGbCdNm") or "").strip() != "집합":
                    continue
                purps_text = f"{it.get('mainPurpsCdNm') or ''} {it.get('etcPurps') or ''}".strip()
                if "숙박" not in purps_text:
                    continue

                jibun = _jibun_from_bunji(it.get("bun"), it.get("ji"))
                umd_key = normalize_umd_nm(umd_raw)
                plat_plc = (it.get("platPlc") or "").strip() or None
                new_plat = (it.get("newPlatPlc") or "").strip() or None
                road_address = new_plat or plat_plc or f"{sgg_text} {umd_raw} {jibun or ''}".strip()

                # 중복 3중 체크
                if jibun and (sgg_cd, umd_key, jibun) in triple:
                    continue
                rn = normalize_road_prefix(road_address)
                if rn and rn in roads:
                    continue
                jn = normalize_jibun_prefix(plat_plc or road_address)  # 기존 키 로딩과 동일한 폴백(대칭성)
                if jn and jn in jibuns:
                    continue

                cats = _find_categories(purps_text)
                # '생활형숙박시설'(메종드리치190 등) 변형 표기 보강
                if "생활형숙박" in purps_text or "생활숙박" in purps_text:
                    cats = set(cats) | {"생활"}
                if cats:
                    label = _combine_labels(cats)
                    counts["병기" if "·" in label else label] += 1
                else:
                    label = None  # 미분류 — 층별개요 2차 검증 대상
                    counts["미분류"] += 1

                bld_nm = (it.get("bldNm") or "").strip() or "-"
                units = int(it.get("hoCnt") or 0) or None

                if args.dry_run:
                    print(f"  [발견] {dong_name} | {bld_nm} | {label or '미분류'} | {purps_text[:60]} | {units}호")
                else:
                    cur.execute("""
                        INSERT INTO master_buildings
                            (building_name, road_address, jibun_address, sgg_text, sgg_cd, umd_nm, jibun,
                             units, hhld_cnt, use_apr_day, tot_area, plat_area,
                             grnd_flr_cnt, ugrnd_flr_cnt, source, lodging_type, lodging_type_detail)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'brhub_bulk',%s,%s)
                    """, (bld_nm, road_address, plat_plc, sgg_text, sgg_cd, umd_key, jibun,
                          units, int(it.get("hhldCnt") or 0) or None,
                          (str(it.get("useAprDay") or "").strip() or None),
                          float(it.get("totArea") or 0) or None, float(it.get("platArea") or 0) or None,
                          int(it.get("grndFlrCnt") or 0) or None, int(it.get("ugrndFlrCnt") or 0) or None,
                          label, purps_text[:500] or None))
                found_run += 1
                prog["found_total"] = prog.get("found_total", 0) + 1
                # 신규분도 중복 셋에 추가 (같은 실행 내 재발견 방지)
                if jibun:
                    triple.add((sgg_cd, umd_key, jibun))
                if rn:
                    roads.add(rn)
                if jn:
                    jibuns.add(jn)

            if len(items) < NUM_ROWS:  # 실제 응답 건수 기준 완료 판정
                break
            page += 1
            time.sleep(args.sleep)

        if not dong_error:
            prog["idx"] += 1
        processed += 1
        if not args.dry_run:
            conn.commit()
            _save_progress(conn, cur, prog)
        if processed % 50 == 0:
            print(f"  진행 {prog['idx']}/{len(dongs)} 법정동, 오늘 호출 {prog['calls_today']}, 이번 실행 발견 {found_run}")
        if dong_error:
            break
        time.sleep(args.sleep)

    print(f"\n[종료] 법정동 {prog['idx']}/{len(dongs)} 처리, 오늘 호출 {prog['calls_today']}, "
          f"이번 실행 발견 {found_run}건 (누적 {prog.get('found_total', 0)}건)")
    print("  분류:", counts)
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
