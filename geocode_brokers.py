# -*- coding: utf-8 -*-
"""
geocode_brokers.py — broker_registry 도로명주소 → 위경도(lat/lng) 좌표 채우기

동작 흐름
------------------------------------------------------------
1. broker_registry 에서 lat 가 아직 NULL 인 행을 조회
   (도로명주소가 없는 행은 지오코딩 불가 → 자동 제외)
2. 각 행의 road_address 를 카카오맵 로컬 API(주소 검색)로 조회해 좌표를 받아온다
   - 엔드포인트: https://dapi.kakao.com/v2/local/search/address.json
   - 헤더: Authorization: KakaoAK {KAKAO_REST_API_KEY}
   - 응답 documents[0].x = 경도(lng), documents[0].y = 위도(lat)
3. 받아온 lat/lng 를 해당 행에 UPDATE (행 단위 즉시 커밋 → 중간에 멈춰도 안전)
4. API 실패/미검색 건은 건너뛰고 계속 진행
5. 끝나면 전체 행 수 대비 좌표 확보 건수를 요약 출력

실행
------------------------------------------------------------
python geocode_brokers.py            # lat 가 NULL 인 모든 행 처리
python geocode_brokers.py --limit 100 # 앞의 100건만 (파일럿용)
"""

import argparse
import os
import sys
import threading
import time
from datetime import datetime

import requests

from db import get_conn
from sync_lodgings import _read_status, _write_status, _touch, _still_owner, HEARTBEAT_SEC

# ------------------------------------------------------------------
KAKAO_REST_API_KEY = os.environ.get("KAKAO_REST_API_KEY", "")
KAKAO_ADDRESS_URL = "https://dapi.kakao.com/v2/local/search/address.json"

REQUEST_SLEEP = 0.1   # 카카오 API 과호출 방지용 딜레이(초)
REQUEST_TIMEOUT = 10  # 개별 호출 타임아웃(초)
# ------------------------------------------------------------------


def _clean_road_address(road_address: str) -> str:
    """첫 쉼표 앞의 순수 도로명주소만 잘라서 반환. 카카오 주소검색 성공률 향상."""
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
    try:
        return float(doc["y"]), float(doc["x"])  # (lat, lng)
    except (KeyError, TypeError, ValueError):
        return None


def geocode_address(road_address: str):
    """도로명주소 한 건 → (lat, lng) 또는 None.
    1차: 꼬리표 제거 후 검색 / 2차(폴백): 원본 주소로 재시도."""
    cleaned = _clean_road_address(road_address)
    result = _query_kakao(cleaned)
    if result is None and cleaned != road_address:
        result = _query_kakao(road_address)
    return result


def geocode_brokers(limit: int | None = None, status_key=None, run_id=None):
    if not KAKAO_REST_API_KEY:
        raise RuntimeError("환경변수 KAKAO_REST_API_KEY 가 없습니다. "
                           "Replit Secrets 에 카카오 REST API 키를 먼저 등록하세요.")

    conn = get_conn()
    cur = conn.cursor()

    sql = """
        SELECT id, office_name, road_address
        FROM broker_registry
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
    print(f"[START] 좌표 미확보 중개업소 {total_targets}건 지오코딩 시작"
          + (f" (--limit {limit})" if limit else ""), flush=True)

    updated = skipped = 0
    for i, row in enumerate(targets, start=1):
        # run_id 펜싱: split-brain 방지
        if status_key and run_id and i % 50 == 0 and not _still_owner(cur, status_key, run_id):
            print("[중단] 상태 소유권을 잃었습니다(다른 실행 감지). 종료합니다.", flush=True)
            break

        broker_id = row["id"]
        name = row["office_name"]
        addr = row["road_address"]

        try:
            result = geocode_address(addr)
        except Exception as e:
            print(f"  [{i}/{total_targets}] 조회 실패({name} / {addr}): {e}", flush=True)
            skipped += 1
            time.sleep(REQUEST_SLEEP)
            continue

        if result is None:
            skipped += 1
            time.sleep(REQUEST_SLEEP)
            continue

        lat, lng = result
        cur.execute(
            "UPDATE broker_registry SET lat=%s, lng=%s WHERE id=%s",
            (lat, lng, broker_id),
        )
        conn.commit()
        updated += 1

        if i % 200 == 0 or i == total_targets:
            print(f"  [진행] {i}/{total_targets} — 성공 {updated} / 건너뜀 {skipped}", flush=True)

        time.sleep(REQUEST_SLEEP)

    # 최종 요약
    cur.execute("""
        SELECT COUNT(*) AS total,
               COUNT(lat) AS with_coord
        FROM broker_registry
    """)
    summary = cur.fetchone()
    total_all = summary["total"]
    with_coord = summary["with_coord"]
    pct = (with_coord / total_all * 100) if total_all else 0

    print("\n[DONE] 중개업소 지오코딩 완료", flush=True)
    print(f"  이번 실행: 성공 {updated}건 / 건너뜀 {skipped}건 (대상 {total_targets}건)", flush=True)
    print(f"  전체 현황: {total_all}건 중 {with_coord}건 좌표 확보 ({pct:.1f}%)", flush=True)

    cur.close()
    conn.close()
    return updated, skipped, total_targets, with_coord, total_all


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None,
                        help="앞에서 N건만 처리 (파일럿 테스트용, 생략 시 전체)")
    parser.add_argument("--status-key", default=None,
                        help="관리자 버튼 실행용 app_meta 상태 키")
    args = parser.parse_args()

    run_id = None
    stop_beat = threading.Event()
    if args.status_key:
        status = _read_status(args.status_key)
        if not status or status.get("state") != "running":
            print("[geocode_brokers] running 상태가 아니므로 종료합니다.")
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
        updated, skipped, targets, with_coord, total_all = geocode_brokers(
            limit=args.limit, status_key=args.status_key, run_id=run_id)
    except Exception as e:
        error = (str(e).replace(KAKAO_REST_API_KEY, "***")
                 if KAKAO_REST_API_KEY else str(e))[:500]
        print(f"[geocode_brokers] 실패: {error}", flush=True)

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
                print(f"[geocode_brokers] 상태 저장 실패({attempt + 1}/3): {e}", flush=True)
                time.sleep(5)
    if error and not args.status_key:
        sys.exit(1)


if __name__ == "__main__":
    main()
