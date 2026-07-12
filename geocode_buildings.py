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
import time

import requests

from db import get_conn

# ------------------------------------------------------------------
# 설정값 — 카카오 REST API 키는 Replit Secrets(환경변수)에서 읽음
#   Secrets 에 KAKAO_REST_API_KEY 라는 이름으로 등록해야 한다. (README 2번 항목 참고)
# ------------------------------------------------------------------
KAKAO_REST_API_KEY = os.environ.get("KAKAO_REST_API_KEY", "")
KAKAO_ADDRESS_URL = "https://dapi.kakao.com/v2/local/search/address.json"

REQUEST_SLEEP = 0.1   # 카카오 API 과호출 방지용 딜레이(초)
REQUEST_TIMEOUT = 10  # 개별 호출 타임아웃(초)


def geocode_address(road_address: str):
    """
    도로명주소 한 건을 카카오 주소검색으로 조회해 (lat, lng) 튜플을 돌려준다.
    검색 결과가 없거나 오류가 나면 None 을 돌려준다(=이 건물은 건너뜀).
    """
    headers = {"Authorization": f"KakaoAK {KAKAO_REST_API_KEY}"}
    params = {"query": road_address}
    resp = requests.get(
        KAKAO_ADDRESS_URL, headers=headers, params=params, timeout=REQUEST_TIMEOUT
    )
    resp.raise_for_status()
    data = resp.json()

    docs = data.get("documents", [])
    if not docs:
        return None

    doc = docs[0]
    # 카카오는 x=경도(lng), y=위도(lat) 를 문자열로 준다.
    try:
        lng = float(doc["x"])
        lat = float(doc["y"])
    except (KeyError, TypeError, ValueError):
        return None
    return lat, lng


def geocode_buildings(limit: int | None = None):
    if not KAKAO_REST_API_KEY:
        print("[중단] 환경변수 KAKAO_REST_API_KEY 가 없습니다. "
              "Replit Secrets 에 카카오 REST API 키를 먼저 등록하세요. (README 2번 항목 참고)")
        return

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


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None,
                        help="앞에서 N건만 처리 (최초 테스트용, 생략 시 전체)")
    args = parser.parse_args()

    geocode_buildings(limit=args.limit)
