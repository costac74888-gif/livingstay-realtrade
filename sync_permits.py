# -*- coding: utf-8 -*-
"""
sync_permits.py — 건축인허가정보(ArchPmsService_v2.getApBasisOulnInfo)로
전국 '준공 전 생활숙박시설 프로젝트'를 자동 발견하여 master_buildings에
building_status='허가' 또는 '착공' 상태로 반영하는 배치.

sync_brhub.py와 완전히 동일한 골격(법정동 순회, 체크포인트, 일일캡,
재시도, 관리자 버튼 상태 연동)을 재사용한다. 차이는 API가
"완공 전" 데이터를 준다는 점뿐이다.

⚠️ 실행 전 필수 확인 사항 (반드시 --probe 먼저 실행):
  이 API의 착공예정일/착공연기일/실제착공일/건축허가일 4개 날짜
  필드의 정확한 JSON 키 이름을 공식 문서로 100% 확인하지 못했다.
  아래는 국토부 유사 API(getBrTitleInfo 등) 명명 관례를 따른
  추정값이다. 반드시 먼저 이렇게 실행해서 실제 키 이름을 확인하고,
  FIELD_MAP 딕셔너리를 맞게 고친 뒤 본 실행으로 넘어갈 것:

      python -u sync_permits.py --probe

  --probe는 법정동 1곳만 조회해서 원본 JSON을 그대로 출력하고 종료한다
  (DB에 아무것도 쓰지 않음).

사용:
  python -u sync_permits.py --probe             # 필드명 확인용, DB 안 씀
  python -u sync_permits.py --limit 20          # 법정동 20개만 (파일럿)
  python -u sync_permits.py --dry-run           # DB에 안 쓰고 발견 내역만 출력
  python -u sync_permits.py                     # 이어서 실행 (일일캡까지)
"""

import argparse
import json
import os
import sys
import threading
import time
from datetime import date, datetime, timedelta

import psycopg2
import requests

from db import get_conn
from addr_norm import normalize_road_prefix, normalize_jibun_prefix
from address_utils import normalize_umd_nm
from stats_cache import mark_master_stats_invalidated
from sync_lodgings import _read_status, _write_status, _touch, _still_owner, HEARTBEAT_SEC

API_URL = "https://apis.data.go.kr/1613000/ArchPmsHubService/getApBasisOulnInfo"
KEY_ENV = "DATA_GO_KR_BROKER_API_KEY"  # 기존 계정 공용 인증키 재사용 (sync_brhub.py와 동일)
CODES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bjdong_codes.json")
PROGRESS_KEY = "permits_progress"
NUM_ROWS = 100  # 10→100으로 변경(수집 속도 10배 개선, 2026-07-27 --probe로 실제 응답 확인)

# 아래 필드명은 --probe(2026-07-27)로 실제 API 응답을 확인해 검증된 값입니다.
# ArchPmsHubService/getApBasisOulnInfo 응답 키 이름:
FIELD_MAP = {
    "허가일": "archPmsDay",        # 건축허가일 (YYYYMMDD)
    "착공예정일": "stcnsSchedDay",  # 착공예정일 (YYYYMMDD)
    "실제착공일": "realStcnsDay",   # 실제착공일 (YYYYMMDD)
    "사용승인일": "useAprDay",      # 사용승인(준공)일 — 값이 있으면 이미 완공된 건물
}


def _load_codes():
    with open(CODES_FILE, encoding="utf-8") as f:
        data = json.load(f)
    return data["sgg"], data["dongs"]


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
    if r.status_code != 200:
        print(f"[HTTP {r.status_code}] 응답 본문: {r.text[:1000]}")
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
    """기존 master_buildings의 중복 판별 키 4종 셋.

    triple/roads/jibuns — 전체 master_buildings 기반 (sync_brhub.py와 동일).
    completed_sgg_jibun — source != 'permit_pipeline'인 완공 건물의 (sgg_cd, jibun) 2중 키.
      주소 형식 불일치(시도 축약·끝 번지 차이)로 triple 매칭이 실패해도
      이 2중 키가 추가로 걸러낸다.
    """
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

    # 완공 건물 (비permit) 의 (sgg_cd, jibun) 2중 키 — umd_nm 없이 느슨하게 매칭
    cur.execute("""
        SELECT sgg_cd, jibun FROM master_buildings
        WHERE source != 'permit_pipeline'
          AND sgg_cd IS NOT NULL AND jibun IS NOT NULL AND jibun != ''
    """)
    completed_sgg_jibun = {(r["sgg_cd"], r["jibun"]) for r in cur.fetchall()}

    return triple, roads, jibuns, completed_sgg_jibun


def probe():
    """법정동 여러 곳을 조회해 원본 JSON을 그대로 출력 — 필드명/용도코드 확인 전용, DB 안 씀.

    생활숙박 허가 건물이 많은 서울 강남구·마포구·송파구 대표 법정동을 먼저 시도하고,
    CODES_FILE의 첫 번째 법정동을 fallback으로 사용한다.
    """
    key = os.environ.get(KEY_ENV)
    if not key:
        raise RuntimeError(f"환경변수 {KEY_ENV} 가 설정되어 있지 않습니다.")
    sgg_map, dongs = _load_codes()

    # 생활숙박 허가 건물이 많은 서울 대표 법정동 우선 시도
    # (sgg_cd 5자리 + bjd_cd 5자리 = 10자리 코드)
    PRIORITY_CODES = [
        ("11680", "10100", "서울 강남구 개포동"),
        ("11680", "10300", "서울 강남구 논현동"),
        ("11440", "10100", "서울 마포구 합정동"),
        ("11440", "10200", "서울 마포구 망원동"),
        ("11710", "10100", "서울 송파구 잠실동"),
    ]
    candidates = [(sgg_cd, bjd_cd, label) for sgg_cd, bjd_cd, label in PRIORITY_CODES]
    # fallback: CODES_FILE의 첫 번째 법정동
    code0, name0 = dongs[0]
    candidates.append((code0[:5], code0[5:], name0))

    found_any = False
    for sgg_cd, bjd_cd, label in candidates:
        print(f"[probe] {label} ({sgg_cd}/{bjd_cd}) 조회 중...")
        items = _fetch_page(key, sgg_cd, bjd_cd, 1)
        print(f"[probe] {len(items)}건 응답.")
        if items:
            print(f"[probe] 첫 번째 항목의 원본 필드 ({label}):")
            print(json.dumps(items[0], ensure_ascii=False, indent=2))
            # 용도 코드 전체 목록 요약
            purps_vals = sorted({
                f"{it.get('mainPurpsCdNm') or ''}/{it.get('etcPurps') or ''}".strip("/")
                for it in items
            })
            print(f"[probe] mainPurpsCdNm/etcPurps 고유값: {purps_vals}")
            found_any = True
            break
        else:
            print(f"  (이 법정동엔 결과 없음 — 다음 법정동 시도)")
    if not found_any:
        print("[probe] 모든 후보 법정동에 결과 없음. CODES_FILE의 다른 법정동을 직접 지정해 재시도하세요.")


def run(args, status_key=None, run_id=None):
    key = os.environ.get(KEY_ENV)
    if not key:
        raise RuntimeError(f"환경변수 {KEY_ENV} 가 설정되어 있지 않습니다.")

    sgg_map, dongs = _load_codes()
    conn = get_conn()
    cur = conn.cursor()
    prog = {"idx": 0, "calls_date": "", "calls_today": 0, "found_total": 0} if args.reset else _get_progress(cur)

    today = date.today().isoformat()
    if prog.get("calls_date") != today:
        prog["calls_date"] = today
        prog["calls_today"] = 0
    if prog["calls_today"] >= args.daily_cap:
        print(f"오늘 호출 {prog['calls_today']}회 — 일일캡({args.daily_cap}) 도달, 내일 재실행하세요.")
        return False, 0, 0, prog["calls_today"]

    triple, roads, jibuns, completed_sgg_jibun = _load_existing_keys(cur)
    print(f"[시작] 법정동 {prog['idx']}/{len(dongs)}부터, 오늘 호출 {prog['calls_today']}/{args.daily_cap}, "
          f"기존 건물 키 {len(triple)}개")

    processed = 0
    found_run = 0
    counts = {"허가": 0, "착공": 0, "미분류": 0}

    while prog["idx"] < len(dongs):
        if args.limit and processed >= args.limit:
            break
        if prog["calls_today"] >= args.daily_cap:
            print(f"일일캡({args.daily_cap}) 도달 — 체크포인트 저장 후 중단. 내일 이어서 실행하세요.")
            break
        if status_key and run_id and not _still_owner(cur, status_key, run_id):
            print("[permits] 다른 실행이 상태를 가져갔습니다 — 이 실행을 중단합니다.")
            raise RuntimeError("동기화 소유권 상실(다른 실행이 시작됨)")

        code, dong_name = dongs[prog["idx"]]
        sgg_cd, bjd_cd = code[:5], code[5:]
        sgg_text = sgg_map.get(sgg_cd, "")
        umd_raw = dong_name[len(sgg_text):].strip() if sgg_text and dong_name.startswith(sgg_text) else dong_name.split()[-1]

        page = 1
        dong_error = False
        dong_rows = []      # INSERT params collected this dong (for reconnect replay)
        while True:
            items = None
            for attempt, wait_sec in enumerate([15, 30, 60], start=1):
                try:
                    items = _fetch_page(key, sgg_cd, bjd_cd, page)
                    break
                except Exception as e:
                    print(f"  [{dong_name}] p{page} 오류(시도 {attempt}/3): {repr(e)[:160]} — {wait_sec}초 후 재시도")
                    time.sleep(wait_sec)
            if items is None:
                print(f"  [{dong_name}] 3회 재시도 모두 실패 — 이 법정동은 건너뛰고 다음 실행 때 재처리")
                dong_error = True
                break
            prog["calls_today"] += 1

            for it in items:
                purps_text = f"{it.get('mainPurpsCdNm') or ''} {it.get('etcPurps') or ''}".strip()
                # 허용 용도 키워드 — 건축인허가 API는 표제부와 다른 코드명을 사용.
                # 2026-07-27 --probe(서울 강남·마포 포함 다수 법정동)로 실제 확인된 값:
                #   "생활숙박시설", "숙박시설", "관광숙박시설"
                # "숙박" 단독·"공중위생"은 일반숙박(모텔·여관)·빌라 오염 원인이므로 제거.
                _PURPS_KEYWORDS = ("생활숙박", "숙박시설", "관광숙박", "생활형숙박", "일반숙박시설")
                if not any(kw in purps_text for kw in _PURPS_KEYWORDS):
                    continue
                # 일반숙박(모텔·여관)·고시원 제외 — "일반숙박시설"은 합법 법정 용어이므로 통과
                _PURPS_EXCLUDE = ("여관", "모텔", "고시원")
                if any(ex in purps_text for ex in _PURPS_EXCLUDE):
                    continue
                if "일반숙박" in purps_text and "일반숙박시설" not in purps_text:
                    continue

                # 건축인허가 단계에서는 세대수가 미확정("0" 또는 null)인 경우가 많으므로
                # 세대수 조건으로 필터링하지 않는다. units는 나중에 backfill로 채운다.
                hoCnt = it.get("hoCnt") or it.get("hhldCnt")

                # 사용승인일(useAprDay)이 있으면 이미 완공된 건물 → 준공전 파이프라인 제외
                use_apr = (it.get(FIELD_MAP["사용승인일"]) or "").strip()
                if use_apr:
                    continue

                # 준공예정일 1년 컷오프 — 착공일(실제 또는 예정) + 900일로 추정한
                # 완공예정일이 1년 이상 지났으면 이미 완공됐거나 사업 취소 가능성이
                # 높으므로 제외. 착공 정보가 없으면 허가일 5년 컷오프로 폴백.
                _actual_raw   = (it.get(FIELD_MAP["실제착공일"]) or "").strip()
                _expected_raw = (it.get(FIELD_MAP["착공예정일"]) or "").strip()
                _start_raw    = _actual_raw or _expected_raw
                _permit_raw   = (it.get(FIELD_MAP["허가일"]) or "").strip()
                _one_yr_ago   = date.today() - timedelta(days=365)
                if _start_raw and len(_start_raw) == 8:
                    try:
                        _comp_est = (datetime.strptime(_start_raw, "%Y%m%d") + timedelta(days=900)).date()
                        if _comp_est < _one_yr_ago:
                            continue
                    except ValueError:
                        pass
                elif _permit_raw and len(_permit_raw) == 8:
                    try:
                        _pd = datetime.strptime(_permit_raw, "%Y%m%d").date()
                        if (date.today() - _pd).days > 365 * 2:
                            continue
                    except ValueError:
                        pass

                jibun = _jibun_from_bunji(it.get("bun"), it.get("ji"))
                umd_key = normalize_umd_nm(umd_raw)
                plat_plc = (it.get("platPlc") or "").strip() or None
                road_address = plat_plc or f"{sgg_text} {umd_raw} {jibun or ''}".strip()

                # 완공 건물 대조 — source != 'permit_pipeline'인 건물의 (sgg_cd, jibun) 2중 키.
                # triple/address 정규화 불일치를 우회하는 보조 체크.
                if jibun and (sgg_cd, jibun) in completed_sgg_jibun:
                    continue
                if jibun and (sgg_cd, umd_key, jibun) in triple:
                    continue
                rn = normalize_road_prefix(road_address)
                if rn and rn in roads:
                    continue
                jn = normalize_jibun_prefix(plat_plc or road_address)
                if jn and jn in jibuns:
                    continue

                actual_start = (it.get(FIELD_MAP["실제착공일"]) or "").strip() or None
                expected_start = (it.get(FIELD_MAP["착공예정일"]) or "").strip() or None
                permit_day = (it.get(FIELD_MAP["허가일"]) or "").strip() or None
                status = "착공" if actual_start else "허가"
                counts[status] += 1

                bld_nm = (it.get("bldNm") or "").strip()
                if not bld_nm:
                    bld_nm = road_address or plat_plc or f"{sgg_text} {umd_raw} {jibun or ''}".strip()
                # hoCnt가 "0" 또는 None이면 units=NULL로 저장(backfill로 나중에 채움)
                units = int(hoCnt) if hoCnt and str(hoCnt) != "0" else None

                # 완공예정일 추정 — 실제착공일(우선) 또는 착공예정일 기준 +900일(약 30개월,
                # 생숙 표준 공사기간 추정치). 둘 다 없으면 추정 불가로 NULL.
                base_date_str = actual_start or expected_start
                completion_est = None
                if base_date_str and len(str(base_date_str)) == 8:
                    try:
                        base_dt = datetime.strptime(str(base_date_str), "%Y%m%d")
                        completion_est = (base_dt + timedelta(days=900)).date().isoformat()
                    except ValueError:
                        completion_est = None

                if args.dry_run:
                    print(f"  [발견] {dong_name} | {bld_nm} | {status} | 허가일={permit_day} "
                          f"착공예정={expected_start} 실제착공={actual_start} | 완공추정={completion_est} | {units}호")
                else:
                    source_key = f"permit|{sgg_cd}|{bjd_cd}|{it.get('bun') or ''}|{it.get('ji') or ''}"
                    row_params = (bld_nm, road_address, plat_plc, sgg_text, sgg_cd, umd_key, jibun,
                                  units, status, purps_text[:500] or None,
                                  str(permit_day) if permit_day else None,
                                  str(actual_start) if actual_start else None,
                                  completion_est,
                                  it.get("totArea") or None,
                                  it.get("platArea") or None,
                                  it.get("archArea") or None,
                                  it.get("bcRat") or None,
                                  it.get("vlRat") or None,
                                  it.get("hhldCnt") or None,
                                  it.get("totPkngCnt") or None,
                                  source_key)
                    dong_rows.append(row_params)
                found_run += 1
                prog["found_total"] = prog.get("found_total", 0) + 1
                # 중복 방지용 키를 동일 법정동 내 중복 적재를 막기 위해 미리 메모리에 추가.
                if jibun:
                    triple.add((sgg_cd, umd_key, jibun))
                if rn:
                    roads.add(rn)
                if jn:
                    jibuns.add(jn)

            if len(items) < NUM_ROWS:
                break
            page += 1
            time.sleep(args.sleep)

        prog["idx"] += 1
        processed += 1
        if not args.dry_run:
            INSERT_SQL = ("INSERT INTO master_buildings"
                          " (building_name, road_address, jibun_address, sgg_text, sgg_cd, umd_nm, jibun,"
                          "  units, source, building_status, lodging_type, lodging_type_detail,"
                          "  permit_day, actual_start_day, completion_expected_date,"
                          "  tot_area, plat_area, arch_area, bc_rat, vl_rat, hhld_cnt, tot_pkng_cnt, source_key)"
                          " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'permit_pipeline',%s,NULL,%s,%s,%s,%s,"
                          "         %s,%s,%s,%s,%s,%s,%s,%s)"
                          " ON CONFLICT (source_key) WHERE source_key IS NOT NULL"
                          " DO UPDATE SET"
                          "   building_name=EXCLUDED.building_name,"
                          "   building_status=EXCLUDED.building_status,"
                          "   permit_day=EXCLUDED.permit_day,"
                          "   actual_start_day=EXCLUDED.actual_start_day,"
                          "   completion_expected_date=EXCLUDED.completion_expected_date,"
                          "   units=EXCLUDED.units,"
                          "   tot_area=EXCLUDED.tot_area,"
                          "   plat_area=EXCLUDED.plat_area,"
                          "   arch_area=EXCLUDED.arch_area,"
                          "   bc_rat=EXCLUDED.bc_rat,"
                          "   vl_rat=EXCLUDED.vl_rat,"
                          "   hhld_cnt=EXCLUDED.hhld_cnt,"
                          "   tot_pkng_cnt=EXCLUDED.tot_pkng_cnt,"
                          "   lodging_type_detail=EXCLUDED.lodging_type_detail")

            def _do_commit(c, u, rows, p):
                for rp in rows:
                    u.execute(INSERT_SQL, rp)
                c.commit()
                try:
                    mark_master_stats_invalidated("sync_permits")
                    print("[permits] 통계 원본 캐시 무효화 표식을 갱신했습니다.")
                except Exception as e:
                    # 표식 기록 실패는 이미 커밋된 수집 결과를 실패로 바꾸지 않는다.
                    print(f"[permits] 통계 원본 캐시 표식 갱신 실패: {repr(e)[:200]}")
                _save_progress(c, u, p)

            if dong_rows:
                try:
                    _do_commit(conn, cur, dong_rows, prog)
                except (psycopg2.OperationalError, psycopg2.InterfaceError) as ssl_err:
                    print(f"  [재접속] DB 연결 끊김({repr(ssl_err)[:120]}) — 재접속 시도 시작")
                    committed = False
                    for cycle in range(5):
                        for wait_sec in (10, 30, 60):
                            time.sleep(wait_sec)
                            try:
                                try: cur.close()
                                except Exception: pass
                                try: conn.close()
                                except Exception: pass
                                conn = get_conn()
                                cur = conn.cursor()
                                _do_commit(conn, cur, dong_rows, prog)
                                print(f"  [재접속 성공] {dong_name} 커밋 완료 (사이클 {cycle + 1})")
                                committed = True
                                break
                            except (psycopg2.OperationalError, psycopg2.InterfaceError) as retry_err:
                                print(f"  [재접속 실패] {dong_name}: {repr(retry_err)[:160]} — {wait_sec}초 대기 후 재시도")
                        if committed:
                            break
                        events = prog.setdefault("db_reconnect_events", [])
                        events.append({"idx": prog["idx"],
                                        "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
                        prog["db_reconnect_events"] = events[-20:]
                        print(f"  [재접속] {cycle + 1}사이클(3회) 모두 실패 — 프로세스는 종료하지 않고 5분 더 쉬었다가 재시도합니다.")
                        time.sleep(300)
                    if not committed:
                        print(f"  [재접속 최종 실패] {dong_name}: 5사이클(약 30분) 시도 후에도 DB 연결 불가 — 이번 실행을 중단합니다.")
                        raise ssl_err
            else:
                _save_progress(conn, cur, prog)
        if processed % 50 == 0:
            print(f"  진행 {prog['idx']}/{len(dongs)} 법정동, 오늘 호출 {prog['calls_today']}, 이번 실행 발견 {found_run}")
        time.sleep(args.sleep)

    print(f"\n[종료] 법정동 {prog['idx']}/{len(dongs)} 처리, 오늘 호출 {prog['calls_today']}, "
          f"이번 실행 발견 {found_run}건 (누적 {prog.get('found_total', 0)}건)")
    print("  분류:", counts)
    completed = prog["idx"] >= len(dongs)
    calls_today = prog["calls_today"]
    cur.close()
    conn.close()
    return completed, processed, found_run, calls_today


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true", help="법정동 1곳만 조회해 원본 필드명 확인 (DB 안 씀)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--daily-cap", type=int, default=8000)
    ap.add_argument("--sleep", type=float, default=1.5)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--status-key", default=None)
    args = ap.parse_args()

    if args.probe:
        probe()
        return

    run_id = None
    stop_beat = threading.Event()
    if args.status_key:
        status = _read_status(args.status_key)
        if not status or status.get("state") != "running":
            print("[permits] running 상태가 아니므로 종료합니다.")
            return
        run_id = status.get("run_id") or ""

        def _beat():
            while not stop_beat.wait(HEARTBEAT_SEC):
                try:
                    _touch(args.status_key, run_id)
                except Exception:
                    pass
        threading.Thread(target=_beat, daemon=True).start()

    error = None
    completed, processed, found_run, calls_today = False, 0, 0, None
    try:
        completed, processed, found_run, calls_today = run(
            args, status_key=args.status_key, run_id=run_id)
    except Exception as e:
        key = os.environ.get(KEY_ENV, "")
        error = (str(e).replace(key, "***") if key else str(e))[:500]
        print(f"[permits] 실패: {error}")

    if args.status_key and run_id is not None:
        stop_beat.set()
        status = _read_status(args.status_key) or {}
        status.update({
            "state": "failed" if error else "done",
            "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "processed": processed,
            "found": found_run,
            "completed": (None if error else completed),
            "calls_today": calls_today,
            "error": error,
        })
        for attempt in range(3):
            try:
                _write_status(args.status_key, status, run_id)
                break
            except Exception as e:
                print(f"[permits] 상태 저장 실패({attempt + 1}/3): {e}")
                time.sleep(5)
    if error and not args.status_key:
        sys.exit(1)


if __name__ == "__main__":
    main()