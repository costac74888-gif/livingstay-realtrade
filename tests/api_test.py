# -*- coding: utf-8 -*-
"""
api_test.py — 데이터 JSON API가 조용히 깨지는 것을 배포 전에 잡아내는 체크.

홈페이지 스모크 체크(smoke_test.py)는 정적 파일(HTML/CSS/JS)만 검증한다.
하지만 화면에 실제로 뜨는 데이터는 전부 JSON API에서 온다:
  - /api/health        (배치 상태)
  - /api/regions       (지역 트리)
  - /api/years         (연도 목록)
  - /api/transactions  (실거래 목록)
쿼리 오류/스키마 드리프트 등으로 이 중 하나라도 깨지면, 페이지는 정상적으로
뜨지만 데이터가 하나도 안 보이는 "조용한 실패"가 발생한다.

이 체크는 Flask 테스트 클라이언트로 각 엔드포인트가
  1) HTTP 200
  2) JSON content-type
  3) 기대하는 형태(shape)의 JSON
을 돌려주는지 검증한다. 하나라도 어긋나면 즉시 실패(exit 1)한다.

실행: python tests/api_test.py
"""

import os
import sys

# app.py를 import할 수 있도록 프로젝트 루트를 경로에 추가
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import app  # noqa: E402


def check_health(payload):
    """/api/health: 항상 total_transactions(정수)를 포함하는 객체여야 한다."""
    if not isinstance(payload, dict):
        return "응답이 JSON 객체가 아님"
    if "total_transactions" not in payload:
        return "'total_transactions' 키 없음"
    if not isinstance(payload["total_transactions"], int):
        return "'total_transactions'가 정수가 아님"
    return None


def check_regions(payload):
    """/api/regions: 시도>시군구>읍면동 계층 트리(객체). 비어 있을 수 있음."""
    if not isinstance(payload, dict):
        return "응답이 JSON 객체(트리)가 아님"
    # 값이 있으면 각 시도 노드는 count와 sgg를 가진 객체여야 한다.
    for sido, node in payload.items():
        if not isinstance(node, dict) or "count" not in node or "sgg" not in node:
            return f"'{sido}' 노드 형태가 잘못됨 (count/sgg 필요)"
        break
    return None


def check_years(payload):
    """/api/years: {"years": [...], "current_year": "YYYY"}"""
    if not isinstance(payload, dict):
        return "응답이 JSON 객체가 아님"
    if not isinstance(payload.get("years"), list):
        return "'years'가 배열이 아님"
    if not payload.get("current_year"):
        return "'current_year' 없음"
    return None


def check_transactions(payload):
    """/api/transactions: {"total", "page", "size", "items": [...]}"""
    if not isinstance(payload, dict):
        return "응답이 JSON 객체가 아님"
    for key in ("total", "page", "size"):
        if not isinstance(payload.get(key), int):
            return f"'{key}'가 정수가 아님"
    if not isinstance(payload.get("items"), list):
        return "'items'가 배열이 아님"
    return None


def check_buildings_geo(payload):
    """/api/buildings-geo: {"total": int, "items": [...]}"""
    if not isinstance(payload, dict):
        return "응답이 JSON 객체가 아님"
    if not isinstance(payload.get("total"), int):
        return "'total'이 정수가 아님"
    if not isinstance(payload.get("items"), list):
        return "'items'가 배열이 아님"
    # 좌표가 있는 항목은 lat/lng가 숫자여야 한다
    for item in payload["items"][:10]:
        if item.get("lat") is not None and not isinstance(item["lat"], (int, float)):
            return "items[].lat이 숫자가 아님"
        if item.get("lng") is not None and not isinstance(item["lng"], (int, float)):
            return "items[].lng이 숫자가 아님"
    return None


# (경로, shape 검증 함수)
CHECKS = [
    ("/api/health", check_health),
    ("/api/regions", check_regions),
    ("/api/years", check_years),
    ("/api/transactions?with_total=1", check_transactions),
    ("/api/buildings-geo", check_buildings_geo),
]


def run():
    failures = []
    client = app.test_client()
    for path, validate in CHECKS:
        resp = client.get(path)
        content_type = resp.headers.get("Content-Type", "")

        if resp.status_code != 200:
            failures.append(f"{path}: HTTP {resp.status_code} (기대: 200)")
            continue
        if "application/json" not in content_type:
            failures.append(
                f"{path}: content-type '{content_type}' 에 'application/json' 없음"
            )
            continue

        try:
            payload = resp.get_json()
        except Exception as e:
            failures.append(f"{path}: JSON 파싱 실패 ({e})")
            continue

        shape_error = validate(payload)
        if shape_error:
            failures.append(f"{path}: {shape_error}")
            continue

        print(f"OK  {path}  ({resp.status_code}, {content_type})")

    # /api/buildings-geo bounds 필터 추가 테스트
    failures += _check_buildings_geo_bounds(client)

    # 수정 요청 → 승인 → 지도 노출 end-to-end 테스트
    failures += _check_building_request_e2e(client)

    if failures:
        print("\nAPI 체크 실패:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    print(
        "\n모든 API 체크 통과 (/api/health, /api/regions, /api/years,"
        " /api/transactions, /api/buildings-geo, e2e 건물요청→지도노출)"
    )
    return 0


def _check_building_request_e2e(client):
    """내 건물 수정 요청 → 승인 → 지도 노출 end-to-end 회귀 점검.

    /api/submit-building의 "신규 마스터 INSERT 경로"를 검증한다.
    외부 API 의존성(건축물대장, 지오코더)은 unittest.mock으로 대체해
    data.go.kr 쿼터를 소모하지 않는다:

      1. baseline: 의정부동 cluster 배지 카운트 기록
      2. /api/submit-building (jibun_address_input 경로) 호출
           classify_lodging_type → ('생활', ...) 으로 고정 반환 (data.go.kr 대체)
           resolve_api_building_name → 고유 TEST_NAME 반환
           _fill_master_coords → lat/lng 직접 UPDATE (geocoder 대체)
         → submit_building이 master_buildings에 새 행을 INSERT하고
           building_requests를 'verified'로 완결시키는 경로 전체가 실행됨
      3. building_requests 행이 생성되고 status='verified'인지 DB 직접 확인
         → 이때 이번 호출에서 생성된 req_id · mb_id를 캡처 (cleanup 전용)
      4. master_buildings 행에 lat/lng가 채워졌는지 확인
      5. 캐시 전체 초기화
      6. /api/buildings-geo?q={이름}     — 정확 이름 검색에서 해당 건물 확인
      7. /api/buildings-geo?q={붙여쓰기} — 공백제거 ILIKE 검색에서도 확인
                                           (더 그레이스 경희 버그 회귀 방지)
      8. /api/buildings-cluster?level=umd — umd 배지 카운트가 baseline+1인지 확인
      9. 롤백: 이번 호출에서 생성된 req_id · mb_id만 삭제
               (다른 행·다른 실행 결과를 건드리지 않음)

    모든 fixture 식별자(이름·지번·도로명주소)는 ms 타임스탬프 기반으로 실행마다 고유.
    BjdongMap 전제조건 (dev 환경 확인 완료):
      extract_sgg_from_address('경기도 의정부시 ...') → sgg_cd='41150'
      find_bjdong_cd('41150', '의정부동')             → bjdong_cd='10100'
    """
    import time as _time
    from unittest import mock
    import app as _app_module
    from db import get_conn

    failures = []

    # 모든 fixture 식별자를 ms 타임스탬프로 고유화 — 같은 jibun/이름 중복 방지
    _run_ms = str(int(_time.time() * 1000))
    TEST_NAME         = f"자동검증빌딩 {_run_ms[-7:]}"   # 공백 포함 → ILIKE nospace 버그 재현
    TEST_NAME_NOSPACE = TEST_NAME.replace(" ", "")
    # 9xxx-9 범위: 9000+로 실제 지번 충돌 가능성 최소, -9 suffix로 test 전용 구별
    TEST_JIBUN        = f"9{_run_ms[-3:]}-9"             # e.g., "9328-9" — 매 실행 고유
    TEST_ROAD_ADDR    = f"경기도 의정부시 테스트로 {_run_ms[-5:]}"   # 매 실행 고유

    REAL_SGG_CD   = "41150"
    REAL_UMD_NM   = "의정부동"
    REAL_SGG_TEXT = "경기도 의정부시"
    TEST_LAT      = 37.7339
    TEST_LNG      = 127.0471
    TEST_LODGING  = "생활"

    def _clear_caches():
        """in-process 테스트 클라이언트 전용 — 전체 초기화가 부작용 없이 안전."""
        _app_module._geo_cache.clear()
        _app_module._cluster_cache.clear()

    conn = get_conn()
    cur  = conn.cursor()
    # 이번 호출에서 생성된 ID만 추적 — cleanup은 이 ID만 삭제
    captured_req_id = None
    captured_mb_id  = None

    try:
        # ── ① Baseline: 삽입 전 의정부동 클러스터 배지 카운트 ─────────────────
        _clear_caches()
        r_base = client.get(
            f"/api/buildings-cluster?level=umd&sgg_nm={REAL_SGG_TEXT}"
        )
        base_items   = (r_base.get_json() or {}).get("items", [])
        expected_umd = f"{REAL_SGG_TEXT} {REAL_UMD_NM}".strip()
        base_badge   = next((it for it in base_items if it.get("name") == expected_umd), None)
        base_count   = base_badge["total"] if base_badge else 0

        # ── ② /api/submit-building — 외부 API mock으로 NEW INSERT 경로 실행 ──
        mock_title = {"new_plat_plc": TEST_ROAD_ADDR, "plat_plc": None, "ho_cnt": 50}

        def _mock_fill_coords(inner_cur, master_id, road_address):
            """geocode_buildings 호출 없이 lat/lng를 직접 설정.
            submit_building이 열어 둔 cursor를 그대로 받아 같은 트랜잭션 내에서 UPDATE."""
            inner_cur.execute(
                "UPDATE master_buildings SET lat=%s, lng=%s WHERE id=%s",
                (TEST_LAT, TEST_LNG, master_id),
            )

        with (
            mock.patch(
                "building_registry.classify_lodging_type",
                return_value=(TEST_LODGING, "생활숙박시설", "", mock_title, "검증완료"),
            ),
            mock.patch(
                "building_registry.resolve_api_building_name",
                return_value=TEST_NAME,   # 고유 이름 → name_pending=False
            ),
            mock.patch("app._fill_master_coords", side_effect=_mock_fill_coords),
        ):
            r_sub = client.post(
                "/api/submit-building",
                json={
                    "road_address":           TEST_ROAD_ADDR,
                    "jibun_address_input":    f"{REAL_UMD_NM} {TEST_JIBUN}",
                    "suggested_lodging_type": TEST_LODGING,
                },
                headers={"X-Forwarded-For": "203.0.113.42"},  # 레이트리밋 전용 테스트 IP
            )

        if r_sub.status_code != 200:
            failures.append(
                f"submit-building: HTTP {r_sub.status_code} (기대: 200)"
            )
        else:
            sub_pl = r_sub.get_json() or {}
            if sub_pl.get("status") != "verified":
                failures.append(
                    f"submit-building: status='{sub_pl.get('status')}' (기대: 'verified') "
                    f"— {sub_pl.get('message')}"
                )
            else:
                print(f"OK  /api/submit-building  (status=verified, 건물={TEST_NAME})")

        # ── ③ 이번 호출이 생성한 행 ID 캡처 + DB 연결 확인 ──────────────────
        # 고유한 (TEST_NAME, TEST_JIBUN) 조합으로 이번 호출 결과만 특정함
        cur.execute("""
            SELECT br.id AS req_id, br.status,
                   mb.id AS mb_id, mb.lat, mb.lng
            FROM building_requests br
            JOIN master_buildings mb ON mb.id = br.master_building_id
            WHERE mb.building_name = %s
              AND mb.jibun         = %s
              AND br.request_type  = 'new'
            ORDER BY br.id DESC LIMIT 1
        """, (TEST_NAME, TEST_JIBUN))
        linked = cur.fetchone()

        if not linked:
            failures.append(
                f"building_requests: '{TEST_NAME}' (jibun={TEST_JIBUN}) 연결 행 없음 "
                f"— submit-building이 master_buildings INSERT를 하지 않은 것으로 의심"
            )
            # 고아 building_request 캡처 (master 생성 전 실패 대비) — 고유 road_address 기준
            cur.execute(
                "SELECT id FROM building_requests"
                " WHERE road_address=%s ORDER BY id DESC LIMIT 1",
                (TEST_ROAD_ADDR,),
            )
            br_row = cur.fetchone()
            if br_row:
                captured_req_id = br_row["id"]
        else:
            captured_req_id = linked["req_id"]
            captured_mb_id  = linked["mb_id"]
            if linked["status"] != "verified":
                failures.append(
                    f"building_requests id={captured_req_id}: "
                    f"status='{linked['status']}' (기대: 'verified')"
                )
            else:
                print(
                    f"OK  building_requests id={captured_req_id} status=verified "
                    f"→ master_building_id={captured_mb_id}"
                )
            if linked["lat"] is None or linked["lng"] is None:
                failures.append(
                    f"master_buildings id={captured_mb_id}: lat/lng NULL — 지도 노출 불가 "
                    f"(_fill_master_coords mock이 lat/lng를 설정하지 못함)"
                )
            else:
                print(
                    f"OK  master_buildings id={captured_mb_id} "
                    f"lat={float(linked['lat']):.4f} lng={float(linked['lng']):.4f}"
                )

        # ── ④ 캐시 초기화 — baseline 조회가 채운 stale 항목 제거 ──────────────
        _clear_caches()

        # ── ⑤ /api/buildings-geo — 정확 이름 검색 ───────────────────────────
        if captured_mb_id is not None:
            r = client.get(f"/api/buildings-geo?q={TEST_NAME}")
            if r.status_code != 200:
                failures.append(f"geo(정확 이름): HTTP {r.status_code} (기대: 200)")
            else:
                payload = r.get_json() or {}
                found = [it for it in payload.get("items", [])
                         if it.get("id") == captured_mb_id]
                if not found:
                    failures.append(
                        f"geo(정확 이름): id={captured_mb_id}가 검색 결과에 없음 "
                        f"(total={payload.get('total')})"
                    )
                else:
                    print(
                        f"OK  /api/buildings-geo?q={TEST_NAME}"
                        f"  (id={captured_mb_id} 확인)"
                    )

            # ── ⑥ /api/buildings-geo — 붙여쓰기 검색 (ILIKE nospace 회귀 방지) ──
            r = client.get(f"/api/buildings-geo?q={TEST_NAME_NOSPACE}")
            if r.status_code != 200:
                failures.append(f"geo(붙여쓰기): HTTP {r.status_code} (기대: 200)")
            else:
                payload = r.get_json() or {}
                found = [it for it in payload.get("items", [])
                         if it.get("id") == captured_mb_id]
                if not found:
                    failures.append(
                        f"geo(붙여쓰기): REPLACE(building_name,' ','') ILIKE 검색에서 "
                        f"id={captured_mb_id} 없음 — nospace ILIKE 조건 확인 필요"
                    )
                else:
                    print(
                        f"OK  /api/buildings-geo?q={TEST_NAME_NOSPACE}"
                        f"  (붙여쓰기 id={captured_mb_id} 확인)"
                    )

        # ── ⑦ /api/buildings-cluster — umd 배지 baseline+1 확인 ─────────────
        _clear_caches()
        r = client.get(
            f"/api/buildings-cluster?level=umd&sgg_nm={REAL_SGG_TEXT}"
        )
        if r.status_code != 200:
            failures.append(f"cluster(umd): HTTP {r.status_code} (기대: 200)")
        else:
            payload     = r.get_json() or {}
            items       = payload.get("items", [])
            badge       = next((it for it in items if it.get("name") == expected_umd), None)
            if badge is None:
                failures.append(
                    f"cluster(umd): '{expected_umd}' 배지 없음 "
                    f"(반환 배지 수={len(items)})"
                )
            else:
                after_count = badge.get("total", 0)
                if after_count < base_count + 1:
                    failures.append(
                        f"cluster(umd): '{expected_umd}' total={after_count}, "
                        f"기대≥{base_count + 1} (baseline={base_count}+1) "
                        f"— 신규 건물이 집계에 포함되지 않음"
                    )
                else:
                    print(
                        f"OK  /api/buildings-cluster?level=umd&sgg_nm={REAL_SGG_TEXT}"
                        f"  ('{expected_umd}' {base_count}→{after_count})"
                    )

    except Exception as e:
        failures.append(f"e2e 테스트 오류: {e}")

    finally:
        # ── ⑧ 롤백: 이번 호출에서 캡처한 ID만 삭제 ─────────────────────────
        # → 다른 실행·다른 사용자 행을 절대 건드리지 않음
        try:
            if captured_req_id:
                cur.execute(
                    "DELETE FROM building_requests WHERE id=%s", (captured_req_id,)
                )
            if captured_mb_id:
                cur.execute(
                    "DELETE FROM master_buildings WHERE id=%s", (captured_mb_id,)
                )
            conn.commit()
        except Exception as cleanup_err:
            failures.append(f"롤백 실패: {cleanup_err}")
        finally:
            cur.close()
            conn.close()
        # 사후 캐시 제거 — 다음 실행이 stale 값을 보지 않게
        try:
            _clear_caches()
        except Exception:
            pass

    return failures


def _check_buildings_geo_bounds(client):
    """bounds 파라미터 동작 검증 — 범위 필터링·잘못된 값 안전 처리."""
    failures = []

    # 전국 전체 건수 확인
    r_all = client.get("/api/buildings-geo")
    if r_all.status_code != 200:
        failures.append(f"/api/buildings-geo (전체): HTTP {r_all.status_code}")
        return failures
    total_all = (r_all.get_json() or {}).get("total", -1)

    # 서울 부근 좁은 viewport 요청 — 전체보다 적어야 한다
    bounds_qs = "sw_lat=37.4&sw_lng=126.8&ne_lat=37.7&ne_lng=127.2"
    r_bounds = client.get(f"/api/buildings-geo?{bounds_qs}")
    if r_bounds.status_code != 200:
        failures.append(f"/api/buildings-geo (bounds): HTTP {r_bounds.status_code}")
        return failures
    payload_b = r_bounds.get_json() or {}
    shape_err = check_buildings_geo(payload_b)
    if shape_err:
        failures.append(f"/api/buildings-geo (bounds): {shape_err}")
        return failures
    total_bounds = payload_b.get("total", -1)
    if total_all > 0 and total_bounds >= total_all:
        failures.append(
            f"/api/buildings-geo (bounds): 범위 필터 효과 없음"
            f" (bounds={total_bounds} >= 전체={total_all})"
        )
    else:
        print(f"OK  /api/buildings-geo?{bounds_qs}  (전체 {total_all}건 → 범위내 {total_bounds}건)")

    # 잘못된 bounds — 서버가 500 없이 응답해야 한다 (bounds 무시하고 200 반환)
    r_bad = client.get("/api/buildings-geo?sw_lat=abc&sw_lng=xyz&ne_lat=!!&ne_lng=@@")
    if r_bad.status_code != 200:
        failures.append(
            f"/api/buildings-geo (잘못된 bounds): HTTP {r_bad.status_code} (기대: 200)"
        )
    else:
        print(f"OK  /api/buildings-geo (잘못된 bounds 무시)  ({r_bad.status_code})")

    return failures


if __name__ == "__main__":
    sys.exit(run())
