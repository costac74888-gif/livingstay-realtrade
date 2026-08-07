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

    if failures:
        print("\nAPI 체크 실패:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    print(
        "\n모든 API 체크 통과 (/api/health, /api/regions, /api/years,"
        " /api/transactions, /api/buildings-geo)"
    )
    return 0


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
