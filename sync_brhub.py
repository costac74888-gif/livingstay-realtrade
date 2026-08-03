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
import concurrent.futures
import json
import os
import sys
import threading
import time
from datetime import date, datetime

import requests

from db import get_conn
from addr_norm import normalize_road_prefix, normalize_jibun_prefix
from address_utils import normalize_umd_nm
from building_registry import _find_categories, _combine_labels
# 관리자 버튼용 상태 기록(run_id 펜싱 + 하트비트)은 sync_lodgings와 완전히 동일한 로직을 재사용
from sync_lodgings import _read_status, _write_status, _touch, _still_owner, HEARTBEAT_SEC
from geocode_buildings import geocode_buildings

API_URL = "https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo"
KEY_ENV = "DATA_GO_KR_BROKER_API_KEY"
CODES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bjdong_codes.json")
PROGRESS_KEY = "brhub_progress"
NUM_ROWS = 100


def _load_codes():
    with open(CODES_FILE, encoding="utf-8") as f:
        data = json.load(f)
    return data["sgg"], data["dongs"]  # sgg: {코드5: "시도 시군구"}, dongs: [[코드10, 법정동명], ...]


_SIBLING_PROGRESS_KEYS = ("brhub_progress", "brhub_rescan_progress")


def _combined_calls_today(cur):
    """메인 수집 + 과거구간 재수집의 오늘 호출량 합계.
    둘 중 하나가 8,000건을 다 써도 나머지가 또 8,000건을 쓸 수 없도록
    일일 캡을 두 실행이 공유하게 만든다."""
    today = date.today().isoformat()
    total = 0
    for key in _SIBLING_PROGRESS_KEYS:
        cur.execute("SELECT value FROM app_meta WHERE key=%s", (key,))
        row = cur.fetchone()
        if row and row["value"]:
            try:
                p = json.loads(row["value"])
                if p.get("calls_date") == today:
                    total += p.get("calls_today", 0)
            except (TypeError, ValueError):
                pass
    return total


def _get_progress(cur, progress_key=PROGRESS_KEY):
    cur.execute("SELECT value FROM app_meta WHERE key=%s", (progress_key,))
    row = cur.fetchone()
    if row and row["value"]:
        try:
            return json.loads(row["value"])
        except ValueError:
            pass
    return {"idx": 0, "calls_date": "", "calls_today": 0, "found_total": 0}


def _save_progress(conn, cur, prog, progress_key=PROGRESS_KEY):
    cur.execute("""
        INSERT INTO app_meta (key, value) VALUES (%s, %s)
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
    """, (progress_key, json.dumps(prog, ensure_ascii=False)))
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


def _is_429(exc):
    """HTTP 429(속도 제한) 오류인지 판별."""
    resp = getattr(exc, "response", None)
    return getattr(resp, "status_code", None) == 429


def _fetch_all_dong_pages(key, sgg_cd, bjd_cd, sleep_s):
    """한 법정동의 전체 페이지를 조회해 (items, pages_used, error_str|None, saw_429) 반환.
    pages_used = 성공한 API 호출 수. 재시도 실패 시 items=None.
    429(속도 제한): 60 → 120 → 180초 대기로 최대 3회 재시도.
    그 외 오류: 15초 대기 후 1회 재시도."""
    all_items, page, saw_429 = [], 1, False
    while True:
        last_exc = None
        for attempt in range(3):
            try:
                rows = _fetch_page(key, sgg_cd, bjd_cd, page)
                last_exc = None
                break
            except Exception as e:
                last_exc = e
                is_r429 = _is_429(e)
                if is_r429:
                    saw_429 = True
                if attempt < 2:
                    wait = 60 * (attempt + 1) if is_r429 else 15
                    print(f"    재시도 {attempt + 1}/2 — {'429 속도제한' if is_r429 else '오류'}, {wait}초 대기…")
                    time.sleep(wait)
        if last_exc is not None:
            return None, page - 1, repr(last_exc)[:160], saw_429
        all_items.extend(rows)
        if len(rows) < NUM_ROWS:
            return all_items, page, None, saw_429
        page += 1
        if sleep_s > 0:
            time.sleep(sleep_s)


def run(args, status_key=None, run_id=None):
    key = os.environ.get(KEY_ENV)
    if not key:
        raise RuntimeError(f"환경변수 {KEY_ENV} 가 설정되어 있지 않습니다.")

    sgg_map, dongs = _load_codes()
    conn = get_conn()
    cur = conn.cursor()
    prog = {"idx": 0, "calls_date": "", "calls_today": 0, "found_total": 0} if args.reset else _get_progress(cur, args.progress_key)
    if args.start_idx >= 0:
        prog["idx"] = args.start_idx

    today = date.today().isoformat()
    if prog.get("calls_date") != today:
        prog["calls_date"] = today
        prog["calls_today"] = 0
    if _combined_calls_today(cur) >= args.daily_cap:
        print(f"오늘 호출 {_combined_calls_today(cur)}회(메인+재수집 합산) — 일일캡({args.daily_cap}) 도달, 내일 재실행하세요.")
        cur.close()
        conn.close()
        return False, 0, 0, prog["calls_today"]

    triple, roads, jibuns = _load_existing_keys(cur)
    print(f"[시작] 법정동 {prog['idx']}/{len(dongs)}부터, 오늘 호출 {prog['calls_today']}/{args.daily_cap}, "
          f"기존 건물 키 {len(triple)}개")

    processed = 0
    found_run = 0
    counts = {"생활": 0, "관광": 0, "일반": 0, "복합": 0, "미분류": 0, "복합제외": 0}

    def _process_items(items, sgg_cd, sgg_text, umd_raw, dong_name):
        """items 리스트를 필터·분류·INSERT. found_run·counts는 클로저로 접근."""
        nonlocal found_run
        for it in items:
            if (it.get("regstrGbCdNm") or "").strip() not in ("집합", "일반"):
                continue
            purps_text = f"{it.get('mainPurpsCdNm') or ''} {it.get('etcPurps') or ''}".strip()
            if not any(k in purps_text for k in ("숙박", "호텔", "콘도")):
                continue

            jibun = _jibun_from_bunji(it.get("bun"), it.get("ji"))
            umd_key = normalize_umd_nm(umd_raw)
            plat_plc = (it.get("platPlc") or "").strip() or None
            new_plat = (it.get("newPlatPlc") or "").strip() or None
            road_address = new_plat or plat_plc or f"{sgg_text} {umd_raw} {jibun or ''}".strip()

            if jibun and (sgg_cd, umd_key, jibun) in triple:
                continue
            rn = normalize_road_prefix(road_address)
            if rn and rn in roads:
                continue
            jn = normalize_jibun_prefix(plat_plc or road_address)
            if jn and jn in jibuns:
                continue

            main_purps = (it.get("mainPurpsCdNm") or "").strip()
            gate_ok = any(k in main_purps for k in ("숙박", "호텔", "콘도")) or (
                not main_purps and ("생활숙박" in purps_text or "생활형숙박" in purps_text))

            if not gate_ok:
                label = "복합"
                detail_text = ("[복합용도] " + purps_text)[:500]
                counts["복합"] += 1
            else:
                detail_text = purps_text[:500] or None
                cats = _find_categories(purps_text)
                if "생활형숙박" in purps_text or "생활숙박" in purps_text:
                    cats = set(cats) | {"생활"}
                if cats:
                    label = _combine_labels(cats)
                    counts["복합" if label == "복합" else label] += 1
                else:
                    # gate 통과(숙박/호텔/콘도)했지만 생활·관광 세부유형 없음
                    # → 일반숙박시설(여관·모텔·펜션 등)로 분류
                    label = "일반"
                    counts["일반"] += 1

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
                      label, detail_text))
            found_run += 1
            prog["found_total"] = prog.get("found_total", 0) + 1
            if jibun:
                triple.add((sgg_cd, umd_key, jibun))
            if rn:
                roads.add(rn)
            if jn:
                jibuns.add(jn)

    workers = getattr(args, "workers", 1)
    stop_reason = None
    consecutive_fails = 0
    FAIL_STREAK_LIMIT = 5
    current_sleep = args.sleep  # 429 감지 시 adaptive하게 늘어남
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        end_bound = args.end_idx if args.end_idx >= 0 else len(dongs)
        while prog["idx"] < min(len(dongs), end_bound):
            if args.limit and processed >= args.limit:
                stop_reason = "limit"
                break
            if _combined_calls_today(cur) >= args.daily_cap:
                print(f"일일캡({args.daily_cap}) 도달(메인+재수집 합산) — 체크포인트 저장 후 중단. 내일 이어서 실행하세요.")
                stop_reason = "daily_cap"
                break
            if status_key and run_id and not _still_owner(cur, status_key, run_id):
                print("[brhub] 다른 실행이 상태를 가져갔습니다 — 이 실행을 중단합니다.")
                raise RuntimeError("동기화 소유권 상실(다른 실행이 시작됨)")

            # 배치 크기: WORKERS개 동을 동시 조회
            batch_size = min(workers, len(dongs) - prog["idx"])
            if args.limit:
                batch_size = min(batch_size, args.limit - processed)
            if batch_size <= 0:
                break
            batch = dongs[prog["idx"] : prog["idx"] + batch_size]

            # 병렬 fetch (페이지 조회는 스레드풀, 처리는 순서대로 메인 스레드)
            fetch_jobs = []
            for code, dong_name in batch:
                sgg_cd_b, bjd_cd_b = code[:5], code[5:]
                f = pool.submit(_fetch_all_dong_pages, key, sgg_cd_b, bjd_cd_b, current_sleep)
                fetch_jobs.append((f, code, dong_name, sgg_cd_b, bjd_cd_b))

            for f, code, dong_name, sgg_cd, bjd_cd in fetch_jobs:
                items, pages_used, error, saw_429 = f.result()
                prog["calls_today"] += pages_used + (1 if error and pages_used == 0 else 0)

                # 429 감지 시 이후 동 간 딜레이를 adaptive하게 늘린다
                if saw_429:
                    current_sleep = min(max(current_sleep, 0.5) * 2, 10.0)
                    print(f"  [429 감지] 이후 동 간 딜레이를 {current_sleep:.1f}초로 늘립니다")

                sgg_text = sgg_map.get(sgg_cd, "")
                umd_raw = (dong_name[len(sgg_text):].strip()
                           if sgg_text and dong_name.startswith(sgg_text)
                           else dong_name.split()[-1])

                if error or items is None:
                    print(f"  [{dong_name}] 오류: {error} — 이 법정동은 건너뛰고 계속 진행합니다")
                    failed = prog.setdefault("failed_dongs", [])
                    failed.append({"code": code, "name": dong_name,
                                   "error": (error or "")[:200],
                                   "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
                    prog["failed_dongs"] = failed[-50:]  # 최근 50건만 보관(무한 증가 방지)
                    prog["idx"] += 1  # 건너뛰고 다음 법정동으로 — 전체 중단하지 않는다
                    processed += 1
                    consecutive_fails += 1
                    if not args.dry_run:
                        conn.commit()
                        _save_progress(conn, cur, prog, args.progress_key)
                    if consecutive_fails >= FAIL_STREAK_LIMIT:
                        cooldowns = prog.setdefault("cooldowns", [])
                        cooldowns.append({"idx": prog["idx"],
                                          "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
                        prog["cooldowns"] = cooldowns[-20:]  # 최근 20건만 보관
                        print(f"[brhub] 연속 {FAIL_STREAK_LIMIT}개 법정동 실패 — "
                              f"프로세스는 종료하지 않고 5분 쉬었다가 이어서 진행합니다.")
                        time.sleep(300)  # 5분 대기
                        consecutive_fails = 0
                        current_sleep = args.sleep  # 딜레이도 기본값으로 리셋 (5분이면 순간제한이 풀렸을 가능성이 높음)
                        continue
                    # 동 간 딜레이 적용 (오류 동 포함 — 다음 동 요청 전 숨 고르기)
                    if current_sleep > 0:
                        time.sleep(current_sleep)
                    continue

                consecutive_fails = 0
                _process_items(items, sgg_cd, sgg_text, umd_raw, dong_name)
                prog["idx"] += 1
                processed += 1
                if not args.dry_run:
                    conn.commit()
                    _save_progress(conn, cur, prog, args.progress_key)
                # 동 간 딜레이 적용 — 페이지 간 sleep과 별개로, 동과 동 사이에 쉰다
                if current_sleep > 0:
                    time.sleep(current_sleep)

            if processed % 50 == 0:
                print(f"  진행 {prog['idx']}/{len(dongs)} 법정동, 오늘 호출 {prog['calls_today']}, 이번 실행 발견 {found_run}")
        else:
            stop_reason = "completed"

    print(f"\n[종료] 법정동 {prog['idx']}/{len(dongs)} 처리, 오늘 호출 {prog['calls_today']}, "
          f"이번 실행 발견 {found_run}건 (누적 {prog.get('found_total', 0)}건), 중단사유={stop_reason}")
    print("  분류:", counts)
    completed = prog["idx"] >= len(dongs)
    calls_today = prog["calls_today"]
    cur.close()
    conn.close()
    return completed, processed, found_run, calls_today, stop_reason


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="이번 실행에서 처리할 법정동 수 (0=일일캡까지)")
    ap.add_argument("--daily-cap", type=int, default=8000)
    ap.add_argument("--workers", type=int, default=1,
                    help="동시 법정동 조회 스레드 수 (기본 4)")
    ap.add_argument("--sleep", type=float, default=1.0,
                        help="동 간 기본 딜레이(초). 429 감지 시 자동으로 늘어남. (기본: 1.0)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--reset", action="store_true", help="체크포인트 초기화 후 처음부터")
    ap.add_argument("--start-idx", type=int, default=-1, help="(테스트용) 이번 실행만 이 인덱스부터")
    ap.add_argument("--end-idx", type=int, default=-1, help="이 인덱스 전까지만 처리 (재수집 구간 한정용, -1=끝까지)")
    ap.add_argument("--progress-key", default=PROGRESS_KEY, help="체크포인트 저장용 app_meta 키 (기본: 메인 진행상태와 공유)")
    ap.add_argument("--status-key", default=None, help="관리자 버튼 실행용 app_meta 상태 키")
    args = ap.parse_args()

    run_id = None
    stop_beat = threading.Event()
    if args.status_key:
        status = _read_status(args.status_key)
        if not status or status.get("state") != "running":
            print("[brhub] running 상태가 아니므로 종료합니다.")
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
    completed, processed, found_run, calls_today, stop_reason = False, 0, 0, None, None
    try:
        completed, processed, found_run, calls_today, stop_reason = run(
            args, status_key=args.status_key, run_id=run_id)
    except Exception as e:
        key = os.environ.get(KEY_ENV, "")
        error = (str(e).replace(key, "***") if key else str(e))[:500]
        print(f"[brhub] 실패: {error}")

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
            "stop_reason": (None if error else stop_reason),
            "error": error,
        })
        for attempt in range(3):
            try:
                _write_status(args.status_key, status, run_id)
                break
            except Exception as e:
                print(f"[brhub] 상태 저장 실패({attempt + 1}/3): {e}")
                time.sleep(5)
    if error and not args.status_key:
        sys.exit(1)

    # 이번 실행에서 새 건물을 발견했으면(dry-run 제외), 좌표 채우기를
    # 이어서 자동 실행 — 사람이 매번 버튼을 따로 안 눌러도 되게 함.
    # 실패해도 건물수집 자체의 성공/실패 상태에는 영향 안 주도록 별도 예외처리.
    if not error and not args.dry_run and found_run > 0:
        print(f"\n[brhub] 신규 건물 {found_run}건 발견 — 좌표 채우기 이어서 실행합니다.")
        try:
            geocode_buildings(limit=None, status_key=None, run_id=None)
        except Exception as e:
            print(f"[brhub] 좌표 채우기 자동 실행 실패(건물수집 자체는 정상 완료됨): "
                  f"{repr(e)[:200]}")


if __name__ == "__main__":
    main()
