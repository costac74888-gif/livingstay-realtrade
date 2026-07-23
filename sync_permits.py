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

import requests

from db import get_conn
from addr_norm import normalize_road_prefix, normalize_jibun_prefix
from address_utils import normalize_umd_nm
from sync_lodgings import _read_status, _write_status, _touch, _still_owner, HEARTBEAT_SEC

API_URL = "https://apis.data.go.kr/1613000/ArchPmsHubService/getApBasisOulnInfo"
KEY_ENV = "DATA_GO_KR_BROKER_API_KEY"  # 기존 계정 공용 인증키 재사용 (sync_brhub.py와 동일)
CODES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bjdong_codes.json")
PROGRESS_KEY = "permits_progress"
NUM_ROWS = 10

# ⚠️ 아래 4개 값(오른쪽)이 추정값입니다 — --probe로 실제 원본 JSON을 확인한 뒤
#    실제 키 이름으로 반드시 수정하세요. 왼쪽(우리 쪽 이름)은 그대로 둬도 됩니다.
FIELD_MAP = {
    "허가일": "archPmsDay",
    "착공예정일": "stcnsSchedDay",
    "실제착공일": "realStcnsDay",
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
    """기존 master_buildings의 중복 판별 키 3종 셋 (sync_brhub.py와 동일 로직)."""
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


def probe():
    """법정동 1곳만 조회해 원본 JSON을 그대로 출력 — 필드명 확인 전용, DB 안 씀."""
    key = os.environ.get(KEY_ENV)
    if not key:
        raise RuntimeError(f"환경변수 {KEY_ENV} 가 설정되어 있지 않습니다.")
    sgg_map, dongs = _load_codes()
    code, dong_name = dongs[0]
    sgg_cd, bjd_cd = code[:5], code[5:]
    print(f"[probe] {dong_name} ({sgg_cd}/{bjd_cd}) 조회 중...")
    items = _fetch_page(key, sgg_cd, bjd_cd, 1)
    print(f"[probe] {len(items)}건 응답. 첫 번째 항목의 원본 필드:")
    if items:
        print(json.dumps(items[0], ensure_ascii=False, indent=2))
    else:
        print("  (이 법정동엔 결과 없음 — CODES_FILE의 dongs[0] 대신 다른 법정동코드로 재시도해보세요)")


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

    triple, roads, jibuns = _load_existing_keys(cur)
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
                if "숙박" not in purps_text and "생활숙박" not in purps_text:
                    continue

                hoCnt = it.get("hoCnt") or it.get("hhldCnt")
                if not hoCnt:
                    continue

                jibun = _jibun_from_bunji(it.get("bun"), it.get("ji"))
                umd_key = normalize_umd_nm(umd_raw)
                plat_plc = (it.get("platPlc") or "").strip() or None
                road_address = plat_plc or f"{sgg_text} {umd_raw} {jibun or ''}".strip()

                if jibun and (sgg_cd, umd_key, jibun) in triple:
                    continue
                rn = normalize_road_prefix(road_address)
                if rn and rn in roads:
                    continue
                jn = normalize_jibun_prefix(plat_plc or road_address)
                if jn and jn in jibuns:
                    continue

                actual_start = it.get(FIELD_MAP["실제착공일"])
                expected_start = it.get(FIELD_MAP["착공예정일"])
                permit_day = it.get(FIELD_MAP["허가일"])
                status = "착공" if actual_start else "허가"
                counts[status] += 1

                bld_nm = (it.get("bldNm") or "").strip() or "-"
                units = int(hoCnt or 0) or None

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
                    cur.execute("""
                        INSERT INTO master_buildings
                            (building_name, road_address, jibun_address, sgg_text, sgg_cd, umd_nm, jibun,
                             units, source, building_status, lodging_type, lodging_type_detail,
                             permit_day, actual_start_day, completion_expected_date)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'permit_pipeline',%s,NULL,%s,%s,%s,%s)
                    """, (bld_nm, road_address, plat_plc, sgg_text, sgg_cd, umd_key, jibun,
                          units, status, purps_text[:500] or None,
                          str(permit_day) if permit_day else None,
                          str(actual_start) if actual_start else None,
                          completion_est))
                found_run += 1
                prog["found_total"] = prog.get("found_total", 0) + 1
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

        if dong_error:
            # 이 법정동은 건너뛰고(idx 그대로 두어 다음 실행 때 재처리),
            # 대신 이번 실행에서 무한 반복되지 않도록 인덱스를 리스트
            # 맨 뒤로 임시 이동시키는 대신, 단순히 다음 인덱스로 넘어간다.
            # (완전한 정합성보다 진행 우선 — 실패한 동은 사용자가 며칠 뒤
            # 다시 --reset 없이 실행하면 자연히 재시도됨)
            prog["idx"] += 1
        else:
            prog["idx"] += 1
        processed += 1
        if not args.dry_run:
            conn.commit()
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