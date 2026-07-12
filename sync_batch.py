# -*- coding: utf-8 -*-
"""
sync_batch.py — 매일/매주 스케줄러가 실행하는 배치 작업 본체

실행 흐름
------------------------------------------------------------
STEP 0. (최초 1회 또는 마스터파일 갱신 시) load_master.py 로 마스터 적재
STEP 1. prepare_master_addresses()
        마스터파일의 도로명주소 → 지번주소 변환 → sgg_cd/umd_nm/jibun 채우기
        (이미 채워진 행은 재호출하지 않음 → API 절약)
STEP 2. sync_transactions()
        마스터에 있는 시군구(57개)만 대상으로 RTMS 상업업무용 매매 조회
        유형='집합'만 필터 → 마스터와 법정동+지번 매칭 → 매칭 실패시 건축HUB 표제부 보완
        transactions 테이블에 중복 없이 적재

실행
------------------------------------------------------------
python sync_batch.py                # 최근 3개월 갱신 (기본, 매일 실행에 적합)
python sync_batch.py --months 36    # 최근 36개월 백필 (최초 1회 대량 적재용)
"""

import argparse
import os
import time
from datetime import datetime
from xml.etree import ElementTree as ET

import requests

from db import get_conn, init_db
from address_utils import road_to_jibun, BjdongMap, parse_jibun, normalize_umd_nm
from building_registry import classify_lodging_type

# ------------------------------------------------------------------
# 설정값 — API 키는 Replit Secrets(환경변수)에서 읽음
# ------------------------------------------------------------------
RTMS_SERVICE_KEY = os.environ.get("RTMS_SERVICE_KEY", "")
BLD_SERVICE_KEY = os.environ.get("BLD_SERVICE_KEY", "")
BJDONG_CODE_CSV = os.environ.get("BJDONG_CODE_CSV", "법정동코드 전체자료.csv")   # code.go.kr 다운로드 파일 경로

RTMS_URL = "https://apis.data.go.kr/1613000/RTMSDataSvcNrgTrade/getRTMSDataSvcNrgTrade"
BLD_TITLE_URL = "https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo"

REQUEST_SLEEP = 0.15  # STEP1 JUSO 주소변환용 딜레이(초)
# RTMS 요청 사이 기본 딜레이(초). 429(Too Many Requests) 방지용.
# CLI --sleep 로 조정 (권장 0.5~1.0). sync_transactions()가 실행 시 덮어쓴다.
RTMS_SLEEP = 0.5


class RateLimitError(Exception):
    """RTMS API가 429 Too Many Requests를 반환했을 때 발생. 재시도 대상."""
    pass


# ------------------------------------------------------------------
# 실패 큐(sync_failures) — 429 등으로 실패한 (시군구, 거래년월)을 기록해두고
# 나중에 --retry-failures 로 그 실패분만 골라 exponential backoff 재시도한다.
# db.py를 건드리지 않도록 이 배치가 자체적으로 테이블을 보장한다(CREATE IF NOT EXISTS).
# ------------------------------------------------------------------
def _ensure_failures_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sync_failures (
            id SERIAL PRIMARY KEY,
            sgg_cd TEXT NOT NULL,
            deal_ymd TEXT NOT NULL,
            reason TEXT,
            attempts INTEGER DEFAULT 0,
            last_attempt_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE (sgg_cd, deal_ymd)
        )
    """)


def _record_failure(cur, sgg_cd, deal_ymd, reason):
    cur.execute("""
        INSERT INTO sync_failures (sgg_cd, deal_ymd, reason, attempts, last_attempt_at)
        VALUES (%s, %s, %s, 1, NOW())
        ON CONFLICT (sgg_cd, deal_ymd) DO UPDATE
            SET attempts = sync_failures.attempts + 1,
                reason = EXCLUDED.reason,
                last_attempt_at = NOW()
    """, (sgg_cd, deal_ymd, (reason or "")[:200]))


def _clear_failure(cur, sgg_cd, deal_ymd):
    cur.execute("DELETE FROM sync_failures WHERE sgg_cd=%s AND deal_ymd=%s", (sgg_cd, deal_ymd))


# ------------------------------------------------------------------
# 매칭키 정규화 — RTMS umdNm은 면/리 지역에서 '설악면 방일리'처럼 공백이 있으므로
# 마스터/실거래 양쪽 모두 공백을 제거해 비교한다.
# 정규화 규칙은 address_utils.normalize_umd_nm 하나로 통일한다(로컬 재구현 금지).
# ------------------------------------------------------------------
_norm_umd = normalize_umd_nm


# ------------------------------------------------------------------
# STEP 1. 마스터파일 주소 보강 (도로명 → 지번/시군구코드)
#   * JUSO 행정동코드(admCd) 앞 5자리 = 시군구코드(=RTMS sggCd) → 법정동코드 CSV 불필요.
#   * umd_nm 은 emdNm+liNm 을 공백제거해 저장(면/리 지역 매칭률 향상).
# ------------------------------------------------------------------
def prepare_master_addresses(region_kw: str | None = None):
    conn = get_conn()
    cur = conn.cursor()
    if region_kw:
        cur.execute(
            "SELECT id, road_address, sgg_text FROM master_buildings "
            "WHERE jibun IS NULL AND road_address LIKE %s",
            (f"%{region_kw}%",),
        )
    else:
        cur.execute("SELECT id, road_address, sgg_text FROM master_buildings WHERE jibun IS NULL")
    targets = cur.fetchall()
    print(f"[STEP1] 주소 변환 대상 {len(targets)}건" + (f" (지역='{region_kw}')" if region_kw else ""))

    updated = 0
    for row in targets:
        try:
            juso = road_to_jibun(row["road_address"])
            if not juso:
                continue
            si_do = juso.get("siNm", "")
            sgg_nm = juso.get("sggNm", "")
            sgg_cd = (juso.get("admCd", "") or "")[:5] or None
            umd_nm = _norm_umd(juso.get("emdNm", "") + juso.get("liNm", ""))
            bun = juso.get("lnbrMnnm", "0")
            ji = juso.get("lnbrSlno", "0")
            jibun_str = f"{bun}-{ji}" if ji not in ("0", "", None) else bun

            if not sgg_cd:
                continue

            cur.execute("""
                UPDATE master_buildings
                SET jibun_address = %s, sgg_cd = %s, umd_nm = %s, jibun = %s
                WHERE id = %s
            """, (f"{si_do} {sgg_nm} {umd_nm} {jibun_str}", sgg_cd, umd_nm, jibun_str, row["id"]))
            updated += 1
        except Exception as e:
            print(f"  주소변환 실패 (id={row['id']}): {e}")
        time.sleep(REQUEST_SLEEP)

    conn.commit()
    cur.close()
    conn.close()
    print(f"[STEP1] 주소 보강 완료: {updated}/{len(targets)}건")


# ------------------------------------------------------------------
# STEP 2. RTMS 수집 + 매칭 + 적재
# ------------------------------------------------------------------
def fetch_nrg_trade(sgg_cd: str, deal_ymd: str) -> list[dict]:
    params = {
        "serviceKey": RTMS_SERVICE_KEY,
        "LAWD_CD": sgg_cd,
        "DEAL_YMD": deal_ymd,
        "numOfRows": 999,
        "pageNo": 1,
    }
    resp = requests.get(RTMS_URL, params=params, timeout=15)
    if resp.status_code == 429:
        # 과호출 차단 — 재시도 큐로 넘기기 위해 전용 예외로 구분한다.
        raise RateLimitError(f"429 Too Many Requests ({sgg_cd}, {deal_ymd})")
    resp.raise_for_status()
    root = ET.fromstring(resp.content)

    items = []
    for item in root.iter("item"):
        row = {child.tag: (child.text or "").strip() for child in item}
        items.append(row)

    # 실제 RTMS(NrgTrade) 응답을 raw로 확인한 결과:
    #  - 유형 필드는 buildingType 이며 값은 '일반' / '집합' → 생숙은 집합건물이므로 '집합'.
    #  - 용도 필드는 buildingUse 이며 값 예: 판매/제1종근린생활/제2종근린생활/기타/숙박 → 생숙은 '숙박'.
    # 1차: buildingType == '집합', 2차: buildingUse에 '숙박' 포함.
    # buildingUse 필드가 비어있는 응답 케이스는 일단 통과시켜(매칭 단계에서 걸러짐)
    # 필드 누락 때문에 데이터가 전부 사라지는 사고를 방지한다.
    def _is_saengsuk(r):
        if r.get("buildingType", "") != "집합":
            return False
        use = r.get("buildingUse", "")
        return (not use) or ("숙박" in use)

    return [r for r in items if _is_saengsuk(r)]


def _process_trades(cur, sgg_cd, deal_ymd, trades, bjdong, stats):
    """한 (시군구, 거래년월)의 거래 목록을 매칭·적재한다.
    stats(dict, 키: inserted/matched_master/matched_bld/unmatched)를 갱신한다.
    본 루프/재시도 루프가 공유하는 핵심 로직 — 여기 한 곳에서만 유지보수한다.
    """
    # 같은 지번·같은 날·같은 가격으로 여러 호실이 동시에 거래되는 경우가 실제로 흔함
    # (소형 원룸형 생숙에서 자주 발생) → 층 + 발생순번까지 키에 포함해야
    # 서로 다른 실거래가 "중복"으로 오인되어 1건만 남는 사고를 막는다.
    occurrence_counter = {}

    for t in trades:
        umd_nm = t.get("umdNm", "")
        jibun = t.get("jibun", "")
        if not umd_nm or not jibun:
            continue
        umd_key = _norm_umd(umd_nm)  # 마스터 umd_nm(공백제거)과 맞추기 위한 매칭키

        deal_date = f"{t.get('dealYear','')}-{t.get('dealMonth','').zfill(2)}-{t.get('dealDay','').zfill(2)}"
        price = t.get("dealAmount", "0").replace(",", "")
        area = t.get("buildingAr", t.get("totalFloorAr", "0"))
        deal_type = t.get("dealingGbn", "")
        floor_val = (t.get("floor") or t.get("flrNo") or "").strip()
        base_key = f"{sgg_cd}|{umd_key}|{jibun}|{deal_date}|{price}|{floor_val}"
        occurrence_counter[base_key] = occurrence_counter.get(base_key, 0) + 1
        raw_key = f"{base_key}|{occurrence_counter[base_key]}"

        # 1) 마스터파일과 매칭 시도 (건물명 확정)
        cur.execute("""
            SELECT building_name, sgg_text, lodging_type, lodging_type_detail
            FROM master_buildings
            WHERE sgg_cd=%s AND umd_nm=%s AND jibun=%s
        """, (sgg_cd, umd_key, jibun))
        m_row = cur.fetchone()

        building_name = None
        match_source = "unmatched"
        si_do_val, sgg_nm_val = None, None  # 시/군구 계층 검색용
        lodging_type_val, lodging_type_detail_val = None, None  # 용도(생활/호텔/콘도) 라벨

        if m_row:
            building_name = m_row["building_name"]
            match_source = "master"
            stats["matched_master"] += 1
            lodging_type_val = m_row["lodging_type"]
            lodging_type_detail_val = m_row["lodging_type_detail"]
            if m_row["sgg_text"]:
                parts = m_row["sgg_text"].split(" ", 1)
                si_do_val = parts[0] if len(parts) > 0 else None
                sgg_nm_val = parts[1] if len(parts) > 1 else None
        elif bjdong is None:
            # 법정동코드 CSV 미제공 → 건축HUB 보완 생략, 미매칭으로 처리
            stats["unmatched"] += 1
            continue
        else:
            # 2) 마스터에 없는 지번 → 표제부/층별개요로 "진짜 생활숙박시설인지" 검증부터 한다.
            #    검증 통과 못 하면(호텔/콘도 등) 이 거래는 아예 저장하지 않는다 —
            #    예전처럼 "건축물대장 보완" 배지로 어정쩡하게 노출시키지 않는다.
            bjdong_cd = bjdong.find_bjdong_cd(sgg_cd, umd_nm)
            if not bjdong_cd:
                stats["unmatched"] += 1
                continue

            plat_gb, bun, ji = parse_jibun(jibun)
            try:
                label, detail, title, reason = classify_lodging_type(sgg_cd, bjdong_cd, plat_gb, bun, ji)
            except Exception as e:
                print(f"  생숙 검증 실패({umd_nm} {jibun}): {e}")
                stats["unmatched"] += 1
                continue

            if label != "생활":
                # 호텔/콘도/판정불가/조회실패 모두 신규 저장 안 함 (기존 '생숙만 신규 편입' 정책 유지)
                stats["unmatched"] += 1
                continue

            building_name = title["bld_nm"]
            match_source = "verified_new"
            stats["matched_bld"] += 1
            lodging_type_val, lodging_type_detail_val = label, detail

            # 검증된 신규 건물은 마스터에도 바로 편입(source='sync_verified') →
            # 다음부턴 'master' 경로로 즉시 매칭됨. umd는 마스터 규칙대로 공백 제거해서 저장.
            sgg_text_val = bjdong.sgg_text(sgg_cd) or ""
            road_addr = title["new_plat_plc"] or title["plat_plc"] or f"{sgg_text_val} {umd_nm} {jibun}"
            cur.execute("""
                INSERT INTO master_buildings
                    (building_name, road_address, sgg_text, sgg_cd, umd_nm, jibun, units,
                     source, verified_at, lodging_type, lodging_type_detail)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'sync_verified', NOW(), %s, %s)
            """, (building_name, road_addr, sgg_text_val, sgg_cd, umd_key, jibun, title["ho_cnt"],
                  label, detail))

            if sgg_text_val:
                parts = sgg_text_val.split(" ", 1)
                si_do_val = parts[0] if len(parts) > 0 else None
                sgg_nm_val = parts[1] if len(parts) > 1 else None

        try:
            cur.execute("""
                INSERT INTO transactions
                (building_name, address, si_do, sgg_nm, area, price, deal_date, deal_type,
                 floor, sgg_cd, umd_nm, jibun, lodging_type, lodging_type_detail, match_source, raw_key)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (raw_key) DO NOTHING
            """, (building_name, f"{umd_nm} {jibun}", si_do_val, sgg_nm_val,
                  float(area or 0), int(price or 0),
                  deal_date, deal_type, floor_val,
                  sgg_cd, umd_nm, jibun, lodging_type_val, lodging_type_detail_val, match_source, raw_key))
            if cur.rowcount:
                stats["inserted"] += 1
        except Exception as e:
            print(f"  적재 실패: {e}")


def sync_transactions(months: int, bjdong=None, sgg_filter=None):
    conn = get_conn()
    cur = conn.cursor()
    _ensure_failures_table(cur)
    conn.commit()

    # 마스터에 존재하는 (매칭 준비 완료된) 시군구만 대상으로.
    # 마스터 건물이 많은 지역(=거래 데이터가 몰린 곳)부터 처리해 초반에 대부분의 데이터를 확보한다.
    cur.execute("""
        SELECT sgg_cd FROM master_buildings
        WHERE sgg_cd IS NOT NULL
        GROUP BY sgg_cd
        ORDER BY COUNT(*) DESC
    """)
    sgg_list = [r["sgg_cd"] for r in cur.fetchall()]
    if sgg_filter:
        sgg_list = [s for s in sgg_list if s in sgg_filter]
    print(f"[STEP2] 배치 대상 시군구 {len(sgg_list)}개, 최근 {months}개월"
          + (f" (sgg 한정: {sorted(sgg_filter)})" if sgg_filter else "")
          + f" — 요청간격 {RTMS_SLEEP:.2f}s")

    deal_ymds = []
    today = datetime.today()
    y, m = today.year, today.month
    for _ in range(months):
        deal_ymds.append(f"{y}{m:02d}")
        m -= 1
        if m == 0:
            m = 12
            y -= 1

    stats = {"inserted": 0, "matched_master": 0, "matched_bld": 0, "unmatched": 0}
    rate_limited = 0

    for sgg_cd in sgg_list:
        for deal_ymd in deal_ymds:
            try:
                trades = fetch_nrg_trade(sgg_cd, deal_ymd)
            except RateLimitError as e:
                # 429 → 실패 큐에 남겨두고 계속 진행. 나중에 --retry-failures 가 backoff로 재시도.
                print(f"  RTMS 429 과호출 → 실패큐 등록 ({sgg_cd}, {deal_ymd})")
                _record_failure(cur, sgg_cd, deal_ymd, "429")
                conn.commit()
                rate_limited += 1
                time.sleep(RTMS_SLEEP)
                continue
            except Exception as e:
                print(f"  RTMS 조회 실패 ({sgg_cd}, {deal_ymd}): {e}")
                time.sleep(RTMS_SLEEP)
                continue

            _process_trades(cur, sgg_cd, deal_ymd, trades, bjdong, stats)
            _clear_failure(cur, sgg_cd, deal_ymd)  # 성공 시 실패큐에서 제거
            time.sleep(RTMS_SLEEP)

        # 지역별 커밋: 장시간 백필 중 진행 상황을 즉시 반영하고,
        # 중간에 중단되어도 직전 지역까지는 안전하게 보존한다.
        conn.commit()
        print(f"  [진행] {sgg_cd} 완료 — 누적 신규 {stats['inserted']}건 "
              f"(마스터매칭 {stats['matched_master']})", flush=True)

    conn.commit()

    note = f"rate_limited={rate_limited}" if rate_limited else None
    cur.execute("""
        INSERT INTO sync_log (started_at, finished_at, regions_processed, rows_inserted,
                               rows_matched_master, rows_matched_buildinghub, rows_unmatched, status, note)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (datetime.now(), datetime.now(), len(sgg_list), stats["inserted"],
          stats["matched_master"], stats["matched_bld"], stats["unmatched"], "success", note))
    conn.commit()
    cur.close()
    conn.close()

    print(f"[STEP2] 완료 — 신규 {stats['inserted']}건 "
          f"(마스터매칭 {stats['matched_master']} / 건축HUB보완 {stats['matched_bld']} / "
          f"미매칭제외 {stats['unmatched']} / 429실패 {rate_limited})")


RETRY_ABORT_AFTER = 15     # 연속 429가 이만큼 쌓이면 '쿼터 소진'으로 보고 라운드 조기 종료
RETRY_ROUND_BACKOFF0 = 60.0    # 조기 종료 후 다음 라운드까지 대기 시작값(초)
RETRY_ROUND_BACKOFF_MAX = 3600.0  # 라운드간 대기 상한(초, 1시간)


def _retry_round(cur, conn, bjdong, stats, item_sleep):
    """실패 큐를 1회 훑는다(항목당 1회 시도). 성공 시 큐에서 제거.
    연속 429가 RETRY_ABORT_AFTER회를 넘으면 일일 쿼터 소진으로 보고 라운드를 조기 종료한다.
    반환: (resolved, quota_exhausted).
    시도 횟수가 적은 항목부터 처리해, 매번 같은 곳에서 막혀도 골고루 기회를 준다.
    """
    cur.execute("SELECT sgg_cd, deal_ymd FROM sync_failures ORDER BY attempts ASC, created_at ASC")
    items = cur.fetchall()
    resolved = 0
    consecutive_429 = 0

    for it in items:
        sgg_cd, deal_ymd = it["sgg_cd"], it["deal_ymd"]
        try:
            trades = fetch_nrg_trade(sgg_cd, deal_ymd)
        except RateLimitError:
            _record_failure(cur, sgg_cd, deal_ymd, "429")
            conn.commit()
            consecutive_429 += 1
            if consecutive_429 >= RETRY_ABORT_AFTER:
                print(f"  [RETRY] 연속 429 {consecutive_429}회 → 쿼터 소진 판단, 라운드 조기 종료", flush=True)
                return resolved, True
            time.sleep(item_sleep)
            continue
        except Exception as e:
            print(f"  [RETRY] 기타 오류 ({sgg_cd} {deal_ymd}): {e}")
            _record_failure(cur, sgg_cd, deal_ymd, str(e))
            conn.commit()
            consecutive_429 = 0
            time.sleep(item_sleep)
            continue

        _process_trades(cur, sgg_cd, deal_ymd, trades, bjdong, stats)
        _clear_failure(cur, sgg_cd, deal_ymd)
        conn.commit()
        resolved += 1
        consecutive_429 = 0
        time.sleep(item_sleep)

    return resolved, False


def retry_failed_requests(bjdong=None, base_sleep=1.0, loop=True):
    """실패 큐(sync_failures)의 (시군구, 거래년월)만 골라 재시도한다.

    라운드 단위로 동작한다: 한 라운드는 큐를 한 번 훑으며 성공분을 채운다.
    API 일일 쿼터가 소진돼 연속 429가 몰리면 라운드를 조기 종료하고, 다음 라운드까지
    대기시간을 2배씩 늘리는 exponential backoff(최대 1시간)로 기다렸다 다시 시도한다.
    큐가 빌 때까지 반복 → 쿼터가 회복되는 대로 '천천히' 채워지는 저우선순위 백그라운드용.
    loop=False면 한 라운드만 돌고 끝낸다(테스트/수동용).
    """
    conn = get_conn()
    cur = conn.cursor()
    _ensure_failures_table(cur)
    conn.commit()

    stats = {"inserted": 0, "matched_master": 0, "matched_bld": 0, "unmatched": 0}
    round_backoff = RETRY_ROUND_BACKOFF0
    round_no = 0

    while True:
        cur.execute("SELECT COUNT(*) AS c FROM sync_failures")
        remaining = cur.fetchone()["c"]
        if remaining == 0:
            print("[RETRY] 실패 큐가 비었음 — 모두 처리 완료 🎉", flush=True)
            break

        round_no += 1
        print(f"[RETRY] 라운드 {round_no} 시작 — 남은 실패큐 {remaining}건 "
              f"(요청간격 {base_sleep:.1f}s)", flush=True)
        resolved, quota_exhausted = _retry_round(cur, conn, bjdong, stats, base_sleep)
        print(f"[RETRY] 라운드 {round_no} 종료 — 이번 라운드 해결 {resolved}건 "
              f"(누적 신규 {stats['inserted']}건)", flush=True)

        if not loop:
            break

        if quota_exhausted or resolved == 0:
            # 쿼터가 회복될 때까지 점점 더 오래 대기(지수 증가)
            print(f"[RETRY] {round_backoff/60:.1f}분 후 다음 라운드 재개", flush=True)
            time.sleep(round_backoff)
            round_backoff = min(round_backoff * 2, RETRY_ROUND_BACKOFF_MAX)
        else:
            # 정상 진행 중이면 대기값을 리셋하고 곧바로 다음 라운드
            round_backoff = RETRY_ROUND_BACKOFF0

    cur.execute("SELECT COUNT(*) AS c FROM sync_failures")
    remaining = cur.fetchone()["c"]
    conn.commit()
    cur.close()
    conn.close()

    print(f"[RETRY] 종료 — 남은 실패큐 {remaining}건 "
          f"(누적 신규 {stats['inserted']}건, 마스터매칭 {stats['matched_master']})", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--months", type=int, default=3, help="최근 N개월 수집 (기본 3, 최초 백필 시 --months 36 권장)")
    parser.add_argument("--region", default=None, help="STEP1 주소보강을 특정 지역(도로명주소 키워드)만 수행 (예: 서귀포시)")
    parser.add_argument("--sgg", default=None, help="STEP2를 특정 시군구코드만 수행, 콤마구분 (예: 50130,41220)")
    parser.add_argument("--master-only", action="store_true",
                        help="마스터에 이미 있는 건물만 매칭(건축HUB 검증 생략) — 빠른 백필용")
    parser.add_argument("--sleep", type=float, default=None,
                        help="RTMS 요청간 딜레이(초). 429 방지용, 권장 0.5~1.0 (기본 0.5)")
    parser.add_argument("--retry-failures", action="store_true",
                        help="실패 큐(sync_failures)에 쌓인 429 실패분만 골라 backoff 재시도 (저우선순위 백그라운드용)")
    args = parser.parse_args()

    # __main__ 블록은 모듈 스코프이므로 아래 대입은 전역 RTMS_SLEEP을 갱신한다.
    # sync_transactions/retry_failed_requests가 이 전역값을 읽어 요청간격에 반영한다.
    if args.sleep is not None:
        RTMS_SLEEP = args.sleep

    init_db()

    # 법정동코드 CSV는 '건축HUB 보완'(마스터에 없는 신축 건물명 확정)에만 필요.
    # 파일이 없으면 마스터 매칭만 수행한다 (JUSO admCd로 시군구코드를 얻으므로 CSV 없이도 동작).
    bjdong_map = None
    if args.master_only:
        print("[SETUP] --master-only → 마스터 매칭만 수행(건축HUB 검증 생략, 빠른 모드)")
    elif os.path.exists(BJDONG_CODE_CSV):
        bjdong_map = BjdongMap(BJDONG_CODE_CSV)
        print(f"[SETUP] 법정동코드 CSV 로드 → 건축HUB 보완 활성화 ({BJDONG_CODE_CSV})")
    else:
        print("[SETUP] 법정동코드 CSV 없음 → 마스터 매칭만 수행(건축HUB 보완 생략)")

    sgg_filter = set(s.strip() for s in args.sgg.split(",")) if args.sgg else None

    if args.retry_failures:
        # 실패 큐만 재시도 — 신규 수집 없이 429로 놓친 (시군구, 거래년월)만 backoff로 채운다.
        retry_failed_requests(bjdong=bjdong_map, base_sleep=(args.sleep or 1.0))
    else:
        prepare_master_addresses(region_kw=args.region)
        sync_transactions(months=args.months, bjdong=bjdong_map, sgg_filter=sgg_filter)
