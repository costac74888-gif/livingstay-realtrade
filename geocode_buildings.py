# -*- coding: utf-8 -*-
"""
geocode_buildings.py — master_buildings 도로명주소 → 위경도(lat/lng) 좌표 채우기

동작 흐름
------------------------------------------------------------
1. master_buildings 에서 lat/lng 가 아직 비어있는(NULL) 건물을 조회
2. 각 건물의 road_address(도로명주소)를 카카오맵 로컬 API(주소 검색)로 호출해 좌표를 받아온다
   - 엔드포인트: https://dapi.kakao.com/v2/local/search/address.json
   - 헤더: Authorization: KakaoAK {KAKAO_REST_API_KEY}
   - 응답 documents[0].x = 경도(lng), documents[0].y = 위도(lat)
3. 받아온 lat/lng 를 해당 건물 행에 UPDATE (건물 단위로 즉시 커밋 → 중간에 멈춰도 안전)
4. API 실패/미검색 건물은 건너뛰고 계속 진행 (전체가 멈추지 않게)
5. 끝나면 전체 건물 수 대비 좌표가 확보된 건물 수를 요약 출력

실행 (※ 카카오 키 등록 후)
------------------------------------------------------------
python geocode_buildings.py            # lat/lng 가 비어있는 모든 건물 처리
python geocode_buildings.py --limit 20 # 앞의 20건만 (최초 테스트용)
"""

import argparse
import os
import sys
import threading
import time
from datetime import datetime

import requests

from db import get_conn
# 관리자 버튼용 상태 기록(run_id 펜싱 + 하트비트)은 sync_lodgings와 동일한 로직 재사용
from sync_lodgings import _read_status, _write_status, _touch, _still_owner, HEARTBEAT_SEC

# ------------------------------------------------------------------
# 설정값 — 카카오 REST API 키는 Replit Secrets(환경변수)에서 읽음
#   Secrets 에 KAKAO_REST_API_KEY 라는 이름으로 등록해야 한다. (README 2번 항목 참고)
# ------------------------------------------------------------------
KAKAO_REST_API_KEY = os.environ.get("KAKAO_REST_API_KEY", "")
KAKAO_ADDRESS_URL = "https://dapi.kakao.com/v2/local/search/address.json"

REQUEST_SLEEP = 0.1   # 카카오 API 과호출 방지용 딜레이(초)
REQUEST_TIMEOUT = 10  # 개별 호출 타임아웃(초)


def _clean_road_address(road_address: str) -> str:
    """
    마스터 주소는 도로명주소 뒤에 층/동/호/법정동 정보가 쉼표로 붙어 있다.
      예) '경기도 수원시 팔달구 갓매산로19번길 27-4, 2~9층 (매산로2가)'
    카카오 주소검색은 이런 꼬리표가 붙으면 '검색결과 없음'을 돌려주므로,
    첫 쉼표 앞부분(순수 도로명주소)만 잘라서 보낸다.
    """
    return road_address.split(",")[0].strip()


def _query_kakao(query: str):
    """카카오 주소검색 1회 호출 → (lat, lng) 또는 결과 없으면 None."""
    headers = {"Authorization": f"KakaoAK {KAKAO_REST_API_KEY}"}
    resp = requests.get(
        KAKAO_ADDRESS_URL, headers=headers, params={"query": query},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    docs = resp.json().get("documents", [])
    if not docs:
        return None
    doc = docs[0]
    # 카카오는 x=경도(lng), y=위도(lat) 를 문자열로 준다.
    try:
        return float(doc["y"]), float(doc["x"])  # (lat, lng)
    except (KeyError, TypeError, ValueError):
        return None


def geocode_address(road_address: str):
    """
    도로명주소 한 건을 카카오 주소검색으로 조회해 (lat, lng) 튜플을 돌려준다.
    검색 결과가 없거나 오류가 나면 None 을 돌려준다(=이 건물은 건너뜀).
    1차: 층/동/호 꼬리표를 제거한 순수 도로명주소로 검색(성공률 대폭 향상)
    2차: 그래도 없으면 원본 주소로 한 번 더 시도(폴백)
    """
    cleaned = _clean_road_address(road_address)
    result = _query_kakao(cleaned)
    if result is None and cleaned != road_address:
        result = _query_kakao(road_address)
    return result


def geocode_buildings(limit: int | None = None, status_key=None, run_id=None):
    if not KAKAO_REST_API_KEY:
        raise RuntimeError("환경변수 KAKAO_REST_API_KEY 가 없습니다. "
                           "Replit Secrets 에 카카오 REST API 키를 먼저 등록하세요.")

    conn = get_conn()
    cur = conn.cursor()

    # 좌표가 아직 없는(그리고 도로명주소가 있는) 건물만 대상으로
    sql = """
        SELECT id, building_name, road_address
        FROM master_buildings
        WHERE lat IS NULL
          AND road_address IS NOT NULL
          AND road_address <> ''
        ORDER BY id
    """
    params = []
    if limit and limit > 0:
        sql += " LIMIT %s"
        params.append(int(limit))
    cur.execute(sql, params)
    targets = cur.fetchall()

    total_targets = len(targets)
    print(f"[START] 좌표 미확보 건물 {total_targets}건 지오코딩 시작"
          + (f" (--limit {limit})" if limit else ""))

    updated = skipped = 0
    for i, row in enumerate(targets, start=1):
        # run_id 펜싱: 다른 실행이 상태를 가져갔으면 즉시 중단 (split-brain 방지)
        if status_key and run_id and i % 20 == 0 and not _still_owner(cur, status_key, run_id):
            print("[중단] 상태 소유권을 잃었습니다(다른 실행 감지). 종료합니다.")
            break
        bld_id = row["id"]
        name = row["building_name"]
        addr = row["road_address"]

        try:
            result = geocode_address(addr)
        except Exception as e:
            # API 오류(타임아웃/키오류/한도초과 등) → 이 건물만 건너뛰고 계속
            print(f"  [{i}/{total_targets}] 조회 실패({name} / {addr}): {e}")
            skipped += 1
            time.sleep(REQUEST_SLEEP)
            continue

        if result is None:
            print(f"  [{i}/{total_targets}] 검색결과 없음({name} / {addr}) → 건너뜀")
            skipped += 1
            time.sleep(REQUEST_SLEEP)
            continue

        lat, lng = result
        cur.execute(
            "UPDATE master_buildings SET lat=%s, lng=%s WHERE id=%s",
            (lat, lng, bld_id),
        )
        conn.commit()  # 건물 단위 커밋 → 중간에 멈춰도 여기까지는 보존
        updated += 1
        if i % 50 == 0 or i == total_targets:
            print(f"  [진행] {i}/{total_targets} 처리 — 성공 {updated} / 건너뜀 {skipped}", flush=True)

        time.sleep(REQUEST_SLEEP)

    # 최종 요약 — 전체 건물 수 대비 좌표 확보 현황
    cur.execute("""
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE lat IS NOT NULL AND lng IS NOT NULL) AS with_coord
        FROM master_buildings
    """)
    summary = cur.fetchone()
    total_all = summary["total"]
    with_coord = summary["with_coord"]
    pct = (with_coord / total_all * 100) if total_all else 0

    print("\n[DONE] 지오코딩 완료")
    print(f"  이번 실행: 성공 {updated}건 / 건너뜀 {skipped}건 (대상 {total_targets}건)")
    print(f"  전체 현황: {total_all}건 중 {with_coord}건 좌표 확보 ({pct:.1f}%)")

    cur.close()
    conn.close()
    return updated, skipped, total_targets, with_coord, total_all


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None,
                        help="앞에서 N건만 처리 (최초 테스트용, 생략 시 전체)")
    parser.add_argument("--status-key", default=None,
                        help="관리자 버튼 실행용 app_meta 상태 키")
    args = parser.parse_args()

    run_id = None
    stop_beat = threading.Event()
    if args.status_key:
        status = _read_status(args.status_key)
        if not status or status.get("state") != "running":
            print("[geocode] running 상태가 아니므로 종료합니다.")
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
    updated = skipped = targets = with_coord = total_all = None
    try:
        updated, skipped, targets, with_coord, total_all = geocode_buildings(
            limit=args.limit, status_key=args.status_key, run_id=run_id)
    except Exception as e:
        error = (str(e).replace(KAKAO_REST_API_KEY, "***")
                 if KAKAO_REST_API_KEY else str(e))[:500]
        print(f"[geocode] 실패: {error}")

    if args.status_key and run_id is not None:
        stop_beat.set()
        status = _read_status(args.status_key) or {}
        status.update({
            "state": "failed" if error else "done",
            "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "updated": updated,
            "skipped": skipped,
            "targets": targets,
            "with_geo": with_coord,
            "total": total_all,
            "error": error,
        })
        for attempt in range(3):
            try:
                _write_status(args.status_key, status, run_id)
                break
            except Exception as e:
                print(f"[geocode] 상태 저장 실패({attempt + 1}/3): {e}")
                time.sleep(5)
    if error and not args.status_key:
        sys.exit(1)


if __name__ == "__main__":
    main()
