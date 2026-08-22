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
        for key in ("txn_count", "listing_count", "total_count"):
            if not isinstance(item.get(key), int) or item[key] < 0:
                return f"items[].{key}가 0 이상의 정수가 아님"
        if item["total_count"] != item["txn_count"] + item["listing_count"]:
            return "items[].total_count가 txn_count + listing_count와 다름"
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
    # 채팅 시작은 휴대폰 인증된 사용자만 가능한지 확인
    failures += _check_chat_phone_verification(client)
    # 방 재고의 만기일 저장·공실 초기화·소유자 권한을 확인
    failures += _check_room_inventory_contract_dates(client)
    # 새 등록자유형과 과거 agent 값의 저장 호환성을 확인
    failures += _check_listing_registrant_types(client)
    # 괄호 안 읍·면·동 표기와 신고 주소의 행정구역 표기가 같은 키가 되는지 확인
    failures += _check_lodging_address_normalization()
    # 일반숙박은 객실수 절대값, 비일반 유형은 신고율을 사용하는지 확인
    failures += _check_lodging_metric_contract(client)
    # 명칭 미확정 일반숙박은 영업신고 대표 사업장명으로 자동 표시되는지 확인
    failures += _check_lodging_auto_naming(client)
    # 일일 캡으로 중간 종료되어도 당일 처리분 자동명명이 반영되는지 확인
    failures += _check_lodging_cap_auto_naming()
    # 관리자 통계표의 일반숙박 호실수 신뢰불가 표시와 비일반 회귀를 확인
    failures += _check_general_units_table_markup(client)

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


def _check_lodging_address_normalization():
    """건축물대장 괄호 표기와 영업신고 도로명주소 정규화를 검증."""
    import addr_norm

    failures = []
    matching_cases = [
        (
            "경상북도 칠곡군 팔공산로2길 8 (동명면 기성리)",
            "경상북도 칠곡군 동명면 팔공산로2길 8",
        ),
        (
            "경상북도 칠곡군 한티로 708-29 (동명면 기성리)",
            "경상북도 칠곡군 동명면 한티로 708-29",
        ),
        (
            "경상북도 칠곡군 팔공산로4길 11-12 (동명면 기성리)",
            "경상북도 칠곡군 동명면 팔공산로4길 11-12",
        ),
    ]
    for master_address, lodging_address in matching_cases:
        master_key = addr_norm.normalize_road_prefix(master_address)
        lodging_key = addr_norm.normalize_road_prefix(lodging_address)
        if not master_key or master_key != lodging_key:
            failures.append(
                "lodging address normalization: 괄호 안 행정리 표기와 신고 도로명이 "
                f"같은 키가 되지 않음 ({master_key} != {lodging_key})"
            )

    # 한티로와 한티로1길처럼 도로명 자체가 다른 주소는 계속 분리한다.
    different_master = addr_norm.normalize_road_prefix(
        "경상북도 칠곡군 한티로1길 708-13 (동명면 기성리)"
    )
    different_lodging = addr_norm.normalize_road_prefix(
        "경상북도 칠곡군 동명면 한티로 708-13"
    )
    if different_master == different_lodging:
        failures.append(
            "lodging address normalization: 서로 다른 도로명을 같은 키로 합침"
        )
    if not failures:
        print("OK  괄호 안 읍·면·동 표기 도로명 정규화 및 오매칭 방지")
    return failures

def _check_lodging_auto_naming(client):
    """미확정 일반숙박의 영업신고 대표명 자동 반영 계약을 검증한다."""
    import time as _time
    import addr_norm
    from db import get_conn
    from lodging_matching import refresh_auto_building_names

    failures = []
    run_id = str(int(_time.time() * 1000))
    road_base = f"테스트특별시 자동명명구 검증로 {run_id[-4:]}"
    inserted_buildings = []
    inserted_permits = []
    conn = get_conn()
    cur = conn.cursor()

    def add_building(label, suffix, pending=True, source="pending", with_metadata=True):
        road = f"{road_base}-{suffix}"
        if with_metadata:
            cur.execute(
                """
                INSERT INTO master_buildings
                    (building_name, road_address, jibun_address, sgg_text, sgg_cd, umd_nm, jibun,
                     source, lodging_type, name_pending, building_name_source, building_name_pending_base)
                VALUES (%s, %s, %s, '테스트특별시 자동명명구', '99999', %s, %s,
                        'api_test', '일반', %s, %s, %s)
                RETURNING id
                """,
                (label, road, f"테스트특별시 자동동 {suffix}", "자동동", suffix, pending, source, label),
            )
        else:
            cur.execute(
                """
                INSERT INTO master_buildings
                    (building_name, road_address, source, lodging_type, name_pending,
                     building_name_source, building_name_pending_base)
                VALUES (%s, %s, 'api_test', '일반', TRUE, 'pending', %s)
                RETURNING id
                """,
                (label, road, label),
            )
        building_id = cur.fetchone()["id"]
        inserted_buildings.append(building_id)
        return building_id, road, f"테스트특별시 자동동 {suffix}"

    def add_lodging(name, road, jibun, permit_suffix, rooms, date, status="영업/정상"):
        permit = f"TEST-AUTO-NAME-{run_id}-{permit_suffix}"
        cur.execute(
            """
            INSERT INTO lodging_registry
                (biz_name, permit_number, road_address, jibun_address, permit_date,
                 biz_status_name, room_count, hygiene_type, road_norm, jibun_norm)
            VALUES (%s, %s, %s, %s, %s, %s, %s, '여관업', %s, %s)
            """,
            (
                name, permit, road, jibun, date, status, rooms,
                addr_norm.normalize_road_prefix(road),
                addr_norm.normalize_jibun_prefix(jibun),
            ),
        )
        inserted_permits.append(permit)

    try:
        single_id, single_road, single_jibun = add_building("자동동 1", "1")
        add_lodging("아이리스모텔", single_road, single_jibun, "single", 8, "20220101")

        largest_id, largest_road, largest_jibun = add_building("자동동 2", "2")
        add_lodging("객실최대모텔", largest_road, largest_jibun, "largest", 31, "20200101")
        add_lodging("객실작은호텔", largest_road, largest_jibun, "small", 10, "20250101")

        tie_id, tie_road, tie_jibun = add_building("자동동 3", "3")
        add_lodging("동률기존모텔", tie_road, tie_jibun, "tie-old", 20, "20200101")
        add_lodging("동률신규호텔", tie_road, tie_jibun, "tie-new", 20, "20250101")
        add_lodging("폐업대형모텔", tie_road, tie_jibun, "closed", 999, "20260101", "폐업")

        closed_id, closed_road, closed_jibun = add_building("자동동 4", "4")
        add_lodging("폐업전용모텔", closed_road, closed_jibun, "closed-only", 99, "20260101", "폐업")

        fixed_id, fixed_road, fixed_jibun = add_building("사용자 확정명", "5", pending=False, source="user")
        add_lodging("자동으로바뀌면안됨", fixed_road, fixed_jibun, "fixed", 100, "20260101")

        unmatched_id, _, _ = add_building("자동동 6", "6")
        road_only_id, road_only_road, road_only_jibun = add_building(
            "도로명 임시명", "7", with_metadata=False
        )
        add_lodging("도로명자동모텔", road_only_road, road_only_jibun, "road-only", 7, "20260101")
        manual_id, manual_road, manual_jibun = add_building("자동동 8", "8")
        add_lodging("수동수정전모텔", manual_road, manual_jibun, "manual", 7, "20260101")
        official_pending_id, official_road, official_jibun = add_building(
            "건축HUB 정식명칭", "9", pending=True, source="official"
        )
        add_lodging("정식명칭을바꾸면안됨", official_road, official_jibun, "official-pending", 100, "20260101")
        conn.commit()
        refresh_auto_building_names(conn, inserted_buildings)

        cur.execute(
            """
            SELECT id, building_name, name_pending, building_name_source,
                   building_name_candidate_count
            FROM master_buildings WHERE id = ANY(%s)
            """,
            (inserted_buildings,),
        )
        rows = {row["id"]: row for row in cur.fetchall()}

        expected = {
            single_id: ("아이리스모텔", "lodging_report", 1),
            largest_id: ("객실최대모텔", "lodging_report", 2),
            tie_id: ("동률신규호텔", "lodging_report", 2),
            closed_id: ("자동동 4", "pending", 0),
            fixed_id: ("사용자 확정명", "user", 0),
            unmatched_id: ("자동동 6", "pending", 0),
            road_only_id: ("도로명자동모텔", "lodging_report", 1),
            manual_id: ("수동수정전모텔", "lodging_report", 1),
            official_pending_id: ("건축HUB 정식명칭", "official", 0),
        }
        for building_id, (name, source, candidate_count) in expected.items():
            row = rows.get(building_id) or {}
            if (
                row.get("building_name") != name
                or row.get("building_name_source") != source
                or int(row.get("building_name_candidate_count") or 0) != candidate_count
                or (building_id != fixed_id and row.get("name_pending") is not True)
            ):
                failures.append(
                    f"lodging auto name: id={building_id} 결과 불일치 "
                    f"({row.get('building_name')}, {row.get('building_name_source')}, "
                    f"{row.get('building_name_candidate_count')})"
                )

        # 상호 변경은 같은 신고번호 UPSERT 뒤 다음 재계산에서 즉시 반영돼야 한다.
        cur.execute(
            "UPDATE lodging_registry SET biz_name=%s WHERE permit_number=%s",
            ("아이리스모텔 리뉴얼", inserted_permits[0]),
        )
        conn.commit()
        refresh_auto_building_names(conn, [single_id])
        cur.execute(
            "SELECT building_name FROM master_buildings WHERE id=%s", (single_id,)
        )
        if (cur.fetchone() or {}).get("building_name") != "아이리스모텔 리뉴얼":
            failures.append("lodging auto name: 상호 변경이 다음 재계산에 반영되지 않음")

        # 활성 후보가 0건이 되면 자동명명 결과를 되돌리거나 덮어쓰지 않는다.
        cur.execute(
            "UPDATE lodging_registry SET biz_status_name=%s WHERE permit_number=%s",
            ("폐업", inserted_permits[0]),
        )
        conn.commit()
        refresh_auto_building_names(conn, [single_id])
        cur.execute(
            """SELECT building_name, building_name_source, building_name_candidate_count
                 FROM master_buildings WHERE id=%s""",
            (single_id,),
        )
        no_active_row = cur.fetchone() or {}
        if (
            no_active_row.get("building_name") != "아이리스모텔 리뉴얼"
            or no_active_row.get("building_name_source") != "lodging_report"
            or int(no_active_row.get("building_name_candidate_count") or 0) != 1
        ):
            failures.append("lodging auto name: 활성 후보 0건일 때 기존 자동명칭을 변경함")

        detail = client.get(f"/api/building/{tie_id}")
        payload = detail.get_json() or {}
        if (
            detail.status_code != 200
            or payload.get("building_name_source") != "lodging_report"
            or payload.get("building_name_candidate_count") != 2
            or payload.get("building_name_auto_representative") is not True
        ):
            failures.append("lodging auto name: 공개 상세 API에 자동명칭 출처/대표 정보가 없음")

        with client.session_transaction() as sess:
            sess["admin"] = True
        listing = client.get(f"/api/admin/buildings?q=동률신규호텔")
        list_row = next(
            (row for row in (listing.get_json() or {}).get("items", []) if row.get("id") == tie_id),
            None,
        )
        if (
            listing.status_code != 200
            or not list_row
            or list_row.get("building_name_source") != "lodging_report"
            or list_row.get("building_name_auto_representative") is not True
        ):
            failures.append("lodging auto name: 관리자 목록에 자동명칭 출처/대표 정보가 없음")

        # 관리자 수동 명칭 수정도 확정명으로 보호되어 다음 동기화에 덮어써지지 않아야 한다.
        manual_update = client.put(
            f"/api/admin/buildings/{manual_id}",
            json={"building_name": "관리자 확정명"},
        )
        refresh_auto_building_names(conn, [manual_id])
        cur.execute(
            """SELECT building_name, name_pending, building_name_source
                 FROM master_buildings WHERE id=%s""",
            (manual_id,),
        )
        manual_row = cur.fetchone() or {}
        if (
            manual_update.status_code != 200
            or manual_row.get("building_name") != "관리자 확정명"
            or manual_row.get("name_pending") is not False
            or manual_row.get("building_name_source") != "user"
        ):
            failures.append("lodging auto name: 관리자 수동 명칭이 자동명에 덮어써짐")

        if not failures:
            print("OK  영업신고 자동명칭 단일·복수·동률·폐업·상호변경·확정명 보호")
    except Exception as exc:
        failures.append(f"lodging auto name 테스트 오류: {exc}")
    finally:
        try:
            if inserted_permits:
                cur.execute(
                    "DELETE FROM lodging_registry WHERE permit_number = ANY(%s)",
                    (inserted_permits,),
                )
            if inserted_buildings:
                cur.execute("DELETE FROM master_buildings WHERE id = ANY(%s)", (inserted_buildings,))
            conn.commit()
        finally:
            cur.close()
            conn.close()
    return failures


def _check_lodging_cap_auto_naming():
    """일일 캡 도달 시 당일 UPSERT 주소의 자동명칭을 즉시 갱신하는지 확인."""
    import os as _os
    import time as _time
    from unittest.mock import patch
    import addr_norm
    import sync_lodgings as sync_module
    from db import get_conn

    failures = []
    run_id = str(int(_time.time() * 1000))
    road = f"테스트특별시 캡검증구 자동명명대로 {run_id[-4:]}"
    permit = f"TEST-CAP-AUTO-NAME-{run_id}"
    daily_key = f"test_lodging_daily_calls_{run_id}"
    progress_key = f"test_lodging_sync_progress_{run_id}"
    inserted_buildings = []
    conn = get_conn()
    cur = conn.cursor()
    original_daily_key = sync_module.DAILY_CALLS_META_KEY
    original_progress_key = sync_module.PROGRESS_META_KEY
    try:
        for label, suffix in (("캡 처리 전 임시명", "1"), ("당일 미처리 임시명", "2")):
            cur.execute(
                """
                INSERT INTO master_buildings
                    (building_name, road_address, source, lodging_type, name_pending,
                     building_name_source, building_name_pending_base)
                VALUES (%s, %s, 'api_test', '일반', TRUE, 'pending', %s)
                RETURNING id
                """,
                (label, f"{road}-{suffix}", label),
            )
            inserted_buildings.append(cur.fetchone()["id"])
        conn.commit()

        item = {
            "BPLC_NM": "캡당일자동명모텔",
            "MNG_NO": permit,
            "ROAD_NM_ADDR": road + "-1",
            "LOTNO_ADDR": f"테스트특별시 캡동 {run_id[-3:]}-1",
            "LCPMT_YMD": "20260101",
            "SALS_STTS_NM": "영업/정상",
            "DTL_SALS_STTS_NM": "",
            "KSRM_CNT": "5",
            "WSRM_CNT": "0",
            "SNTTN_BZSTAT_NM": "여관업",
            "TELNO": "",
            "DAT_UPDT_PNT": "",
        }
        with patch.object(sync_module, "DAILY_CALLS_META_KEY", daily_key), \
             patch.object(sync_module, "PROGRESS_META_KEY", progress_key), \
             patch.object(
                 sync_module,
                 "_fetch_page_retry",
                 return_value=([item], 2, False),
             ), \
             patch.dict(_os.environ, {sync_module.SERVICE_KEY_ENV: "test-key"}):
            completed, processed, calls_today = sync_module.sync_lodgings(
                num_rows=100, sleep_sec=0, max_calls=1
            )

        cur.execute(
            "SELECT building_name FROM master_buildings WHERE id=%s",
            (inserted_buildings[0],),
        )
        target_name = (cur.fetchone() or {}).get("building_name")
        cur.execute(
            "SELECT building_name FROM master_buildings WHERE id=%s",
            (inserted_buildings[1],),
        )
        untouched_name = (cur.fetchone() or {}).get("building_name")
        if not (
            completed is False
            and processed == 1
            and calls_today == 1
            and target_name == "캡당일자동명모텔"
            and untouched_name == "당일 미처리 임시명"
        ):
            failures.append(
                "lodging cap auto name: 캡 중간 종료 후 당일 처리 건물만 즉시 자동명명되지 않음 "
                f"(completed={completed}, processed={processed}, target={target_name}, "
                f"untouched={untouched_name})"
            )
        else:
            print("OK  일일 캡 도달 시 당일 처리분 자동명칭 즉시 반영")
    except Exception as exc:
        failures.append(f"lodging cap auto name 테스트 오류: {exc}")
    finally:
        sync_module.DAILY_CALLS_META_KEY = original_daily_key
        sync_module.PROGRESS_META_KEY = original_progress_key
        try:
            cur.execute("DELETE FROM lodging_registry WHERE permit_number=%s", (permit,))
            cur.execute(
                "DELETE FROM master_buildings WHERE id = ANY(%s)",
                (inserted_buildings,),
            )
            cur.execute(
                "DELETE FROM app_meta WHERE key = ANY(%s)",
                ([daily_key, progress_key],),
            )
            conn.commit()
        finally:
            cur.close()
            conn.close()
    return failures


def _check_general_units_table_markup(client):
    """관리자 통계표에서 일반숙박 호실수만 참고용으로 표시하는지 확인."""
    failures = []
    response = client.get("/admin")
    if response.status_code != 200:
        return [f"admin stats markup: 관리자 페이지 HTTP {response.status_code}"]

    html = response.get_data(as_text=True)
    required_fragments = [
        "일반숙박시설은 구분소유 호수 개념이 없어 이 값이 실제 객실수를 반영하지 않습니다.",
        "실제 객실수는 '신고율/객실수' 컬럼을 참고하세요",
        "const generalUnitsCell =",
        'row.type === "일반" ? generalUnitsCell(row.units)',
        'if (c.key === "units")',
        "${n(row.units)}",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in html]
    if missing:
        failures.append(
            "admin stats markup: 일반 전용 호실수 표시 또는 비일반 기존 표시가 누락됨 "
            f"({', '.join(missing)})"
        )
    else:
        print("OK  관리자 통계표 일반숙박 호실수 참고용 표시 및 비일반 회귀")
    return failures


def _check_lodging_metric_contract(client):
    """실제 표본 건물과 공개 통계가 일반숙박 지표 계약을 지키는지 확인."""
    import app as app_module
    import time as _time
    import addr_norm
    from db import get_conn
    from io import BytesIO
    from openpyxl import load_workbook

    failures = []
    conn = get_conn()
    cur = conn.cursor()
    try:
        samples = []
        for pattern in ("%라마다인천호텔%", "%THE TRINY HOTEL%"):
            cur.execute(
                "SELECT id, building_name, lodging_type FROM master_buildings "
                "WHERE building_name ILIKE %s ORDER BY id LIMIT 1",
                (pattern,),
            )
            row = cur.fetchone()
            if not row:
                failures.append(f"lodging metric: 표본 건물을 찾지 못했습니다 ({pattern})")
            else:
                samples.append(row)

        cur.execute(
            "SELECT id, building_name, lodging_type FROM master_buildings "
            "WHERE building_name ILIKE %s ORDER BY id LIMIT 1",
            ("%빌리브패러그라프해운대%",),
        )
        living_sample = cur.fetchone()
        if not living_sample:
            failures.append("lodging metric: 표본 건물을 찾지 못했습니다 (빌리브패러그라프해운대)")

        cur.execute(
            "SELECT id, building_name, lodging_type FROM master_buildings "
            "WHERE lodging_type IS DISTINCT FROM '일반' "
            "  AND lodging_type IS DISTINCT FROM 'mixed_use_excluded' "
            "ORDER BY id LIMIT 1"
        )
        non_general = cur.fetchone()
    finally:
        cur.close()
        conn.close()

    for sample in samples:
        resp = client.get(f"/api/building/{sample['id']}")
        payload = resp.get_json() or {}
        if resp.status_code != 200:
            failures.append(
                f"lodging metric: {sample['building_name']} 상세 API HTTP {resp.status_code}"
            )
            continue
        if payload.get("lodging_type") != "일반":
            failures.append(
                f"lodging metric: {sample['building_name']} 유형이 일반이 아님 "
                f"({payload.get('lodging_type')})"
            )
        if payload.get("lodging_metric") != "room_count":
            failures.append(
                f"lodging metric: {sample['building_name']} lodging_metric이 room_count가 아님"
            )
        if payload.get("lodging_report_rate") is not None:
            failures.append(
                f"lodging metric: {sample['building_name']} 상세 응답에 신고율이 남아 있음"
            )
        if payload.get("lodging_active_business_count") != len(payload.get("lodgings") or []):
            failures.append(
                f"lodging metric: {sample['building_name']} 활성 사업장 수가 목록과 다름"
            )
        else:
            print(
                f"OK  {sample['building_name']} 일반숙박 객실수 지표 "
                f"({payload.get('lodging_room_total', 0)}실)"
            )

    if non_general:
        resp = client.get(f"/api/building/{non_general['id']}")
        payload = resp.get_json() or {}
        if resp.status_code != 200:
            failures.append(
                f"lodging metric: 비일반 표본 {non_general['building_name']} 상세 API "
                f"HTTP {resp.status_code}"
            )
        elif payload.get("lodging_metric") != "report_rate":
            failures.append(
                f"lodging metric: 비일반 표본 {non_general['building_name']}이 신고율 지표가 아님"
            )
        else:
            print(f"OK  {non_general['building_name']} 비일반 신고율 지표 유지")
    else:
        failures.append("lodging metric: 비일반 표본 건물을 찾지 못했습니다.")

    if living_sample:
        resp = client.get(f"/api/building/{living_sample['id']}")
        payload = resp.get_json() or {}
        expected_rate = round(153 / 286 * 100, 1)
        if resp.status_code != 200:
            failures.append(
                f"lodging metric: {living_sample['building_name']} 상세 API "
                f"HTTP {resp.status_code}"
            )
        elif payload.get("lodging_type") != "생활":
            failures.append(
                f"lodging metric: {living_sample['building_name']} 유형이 생활이 아님 "
                f"({payload.get('lodging_type')})"
            )
        elif payload.get("lodging_metric") != "report_rate":
            failures.append(
                f"lodging metric: {living_sample['building_name']}가 신고율 지표가 아님"
            )
        elif payload.get("units") != 286 or payload.get("lodging_room_total") != 153:
            failures.append(
                f"lodging metric: {living_sample['building_name']} 객실수/호실수가 "
                f"153/286이 아님 ({payload.get('lodging_room_total')}/{payload.get('units')})"
            )
        elif payload.get("lodging_report_rate") != expected_rate:
            failures.append(
                f"lodging metric: {living_sample['building_name']} 신고율이 "
                f"{expected_rate}%가 아님 ({payload.get('lodging_report_rate')}%)"
            )
        else:
            print(
                f"OK  {living_sample['building_name']} 생활 신고율 지표 "
                f"(153실 / 286실 = {expected_rate}%)"
            )

    # 캐시가 없는 공개 통계와 관리자 전체통계가 같은 일반 제외 분자·분모를 쓰는지 확인한다.
    original_cache = app_module._bld_full_stats_cache
    try:
        app_module._bld_full_stats_cache = {"ts": 0.0, "data": None}
        fallback_response = client.get("/api/stats/registration-rate")
        fallback_stats = fallback_response.get_json() or {}

        with client.session_transaction() as sess:
            sess["admin"] = True

        full_stats_response = client.get("/api/admin/buildings/full-stats")
        full_stats = full_stats_response.get_json() or {}
        rows = {row.get("type"): row for row in full_stats.get("rows", [])}
        total_row = rows.get("전체") or {}
        general_row = rows.get("일반") or {}

        if full_stats_response.status_code != 200 or not full_stats.get("ok"):
            failures.append("lodging metric: 관리자 전체 통계를 불러오지 못했습니다.")
        elif general_row.get("lodging_metric") != "room_count" or general_row.get("report_rate") is not None:
            failures.append("lodging metric: 관리자 일반숙박 행이 객실수 지표가 아님")
        else:
            expected_sub_types = ["일반호텔", "여관업", "여인숙업", "숙박업(생활)"]
            sub_rows = general_row.get("sub_rows")
            if not isinstance(sub_rows, list) or [row.get("type") for row in sub_rows] != expected_sub_types:
                failures.append("lodging metric: 관리자 일반숙박 세분류 행이 4개 업태로 반환되지 않음")
            elif (
                sum(int(row.get("permit_count") or 0) for row in sub_rows) != general_row.get("permit_count")
                or sum(int(row.get("room_count") or 0) for row in sub_rows) != general_row.get("room_count")
            ):
                failures.append("lodging metric: 일반숙박 세분류 업체수 또는 객실수 합계가 일반 행과 불일치")
            else:
                print(
                    f"OK  관리자 일반숙박 4개 세분류 합계 일치 "
                    f"({general_row.get('room_count')}실)"
                )

            expected_rooms = int(total_row.get("report_rate_room_count") or 0)
            expected_units = int(total_row.get("report_rate_units") or 0)
            expected_rate = round(expected_rooms * 100.0 / expected_units, 1) if expected_units else None
            if total_row.get("report_rate") != expected_rate:
                failures.append("lodging metric: 관리자 전체 신고율의 가중 분자·분모가 불일치")
            else:
                print(
                    f"OK  관리자 전체 신고율 일반 제외 "
                    f"({expected_rooms}실 / {expected_units}실 = {expected_rate}%)"
                )

        general_list_response = client.get("/api/admin/buildings?lodging_type_filter=일반")
        general_totals = (general_list_response.get_json() or {}).get("totals") or {}
        if (
            general_list_response.status_code != 200
            or general_totals.get("weighted_report_rate") is not None
            or general_totals.get("report_rate_units") != 0
        ):
            failures.append("lodging metric: 일반숙박만 필터한 관리자 합계에 신고율이 남아 있음")
        else:
            print("OK  관리자 일반숙박 필터 합계는 객실수 지표만 사용")

        cached_response = client.get("/api/stats/registration-rate")
        cached_stats = cached_response.get_json() or {}
        for label, response, stats_payload in (
            ("캐시 미스", fallback_response, fallback_stats),
            ("캐시 히트", cached_response, cached_stats),
        ):
            if (
                response.status_code != 200
                or stats_payload.get("general_excluded") is not True
                or stats_payload.get("biz_units") != total_row.get("report_rate_room_count")
                or stats_payload.get("total_units") != total_row.get("report_rate_units")
                or stats_payload.get("rate") != total_row.get("report_rate")
            ):
                failures.append(f"lodging metric: 공개 전국 신고율 {label} 경로가 일반 제외 집계와 불일치")
            else:
                print(f"OK  공개 전국 신고율 {label} 일반 제외 집계 일치")

        # 관리자 목록과 선택 엑셀도 일반숙박을 객실수 지표로 전달하는지 확인한다.
        ramada = next((row for row in samples if row["building_name"] == "라마다인천호텔"), None)
        if ramada:
            list_response = client.get(
                f"/api/admin/buildings?lodging_type_filter=일반&q={ramada['building_name']}"
            )
            list_payload = list_response.get_json() or {}
            list_row = next(
                (row for row in list_payload.get("items", []) if row.get("id") == ramada["id"]),
                None,
            )
            if not list_row or list_row.get("lodging_metric") != "room_count":
                failures.append("lodging metric: 관리자 목록 일반숙박 지표가 객실수로 내려오지 않음")

            export_response = client.get(f"/api/admin/buildings/export.xlsx?ids={ramada['id']}")
            if export_response.status_code != 200:
                failures.append("lodging metric: 관리자 건물 엑셀 다운로드 실패")
            else:
                wb = load_workbook(BytesIO(export_response.data), data_only=True)
                ws = wb.active
                headers = [cell.value for cell in ws[1]]
                metric_col = headers.index("신고 지표(일반=객실수)") + 1
                metric_value = ws.cell(2, metric_col).value
                if not isinstance(metric_value, str) or not metric_value.endswith("실"):
                    failures.append("lodging metric: 관리자 건물 엑셀에 일반숙박 객실수 표기가 없음")
                else:
                    print(f"OK  관리자 목록·엑셀 일반숙박 객실수 표기 ({metric_value})")

        # 도로명 정규화 키는 다르지만 지번 키가 같은 건물은 상세 API와
        # 관리자 목록 모두 지번 보조 매칭으로 영업신고를 보여야 한다.
        # 개발 DB의 실제 표본 유무에 의존하지 않도록 임시 행을 만들고 정리한다.
        run_id = str(int(_time.time() * 1000))
        building_id = None
        permit_number = f"TEST-ADMIN-JIBUN-{run_id}"
        building_name = f"자동 지번보조매칭 {run_id}"
        # 새 괄호 정규화 규칙이 도로명 매칭을 보강하더라도, 도로명 자체가
        # 다른 경우에는 지번 보조 매칭이 계속 작동해야 한다.
        building_road = "경상북도 칠곡군 동명면 한티로1길 8"
        building_jibun = "경상북도 칠곡군 동명면 기성리 836번지"
        lodging_road = "경상북도 칠곡군 동명면 팔공산로2길 8"
        lodging_jibun = "경상북도 칠곡군 동명면 기성리 836"
        conn = get_conn()
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO master_buildings "
                "(building_name, road_address, jibun_address, source, lodging_type) "
                "VALUES (%s, %s, %s, 'api_test', '일반') RETURNING id",
                (building_name, building_road, building_jibun),
            )
            building_id = cur.fetchone()["id"]
            cur.execute(
                "INSERT INTO lodging_registry "
                "(biz_name, permit_number, road_address, jibun_address, biz_status_name, "
                "room_count, hygiene_type, road_norm, jibun_norm) "
                "VALUES (%s, %s, %s, %s, '영업/정상', 18, '여관업', %s, %s)",
                (
                    "아이리스모텔",
                    permit_number,
                    lodging_road,
                    lodging_jibun,
                    addr_norm.normalize_road_prefix(lodging_road),
                    addr_norm.normalize_jibun_prefix(lodging_jibun),
                ),
            )
            conn.commit()

            detail_response = client.get(f"/api/building/{building_id}")
            detail_payload = detail_response.get_json() or {}
            detail_has_iris = any(
                item.get("biz_name") == "아이리스모텔"
                for item in detail_payload.get("lodgings", [])
            )
            list_response = client.get(f"/api/admin/buildings?q={building_name}")
            list_payload = list_response.get_json() or {}
            list_row = next(
                (row for row in list_payload.get("items", []) if row.get("id") == building_id),
                None,
            )
            list_has_iris = any(
                item.get("biz_name") == "아이리스모텔"
                for item in (list_row or {}).get("lodging_list", [])
            )
            if detail_response.status_code != 200 or not detail_has_iris:
                failures.append("lodging match fallback: 아이리스모텔이 상세 API 지번 보조 매칭에서 누락됨")
            elif list_response.status_code != 200 or not list_row:
                failures.append("lodging match fallback: 지번 보조 매칭 건물 행을 관리자 목록에서 찾지 못함")
            elif not list_row.get("lodging_count") or not list_has_iris:
                failures.append("lodging match fallback: 아이리스모텔이 관리자 목록에서 미매칭으로 표시됨")
            else:
                print("OK  아이리스모텔 지번 보조 매칭이 상세·관리자 목록에서 일치")
        finally:
            if building_id is not None:
                cur.execute("DELETE FROM lodging_registry WHERE permit_number = %s", (permit_number,))
                cur.execute("DELETE FROM master_buildings WHERE id = %s", (building_id,))
                conn.commit()
            cur.close()
            conn.close()
    finally:
        app_module._bld_full_stats_cache = original_cache

    return failures


def _check_chat_phone_verification(client):
    """미인증 사용자의 채팅방 생성을 서버에서 차단하고, 인증 뒤 생성되는지 확인."""
    import time as _time
    from db import get_conn

    failures = []
    run_id = str(int(_time.time() * 1000))
    conn = get_conn()
    cur = conn.cursor()
    seller_id = buyer_id = listing_id = room_id = None
    try:
        cur.execute("SELECT id FROM master_buildings ORDER BY id LIMIT 1")
        building = cur.fetchone()
        if not building:
            return ["chat phone verification: 테스트용 master_buildings 행이 없습니다."]
        cur.execute(
            "INSERT INTO users (email, name, phone, phone_verified) VALUES (%s, %s, %s, TRUE) RETURNING id",
            (f"chat-seller-{run_id}@example.test", "채팅 판매자", "010-0000-0000"),
        )
        seller_id = cur.fetchone()["id"]
        cur.execute(
            "INSERT INTO users (email, name) VALUES (%s, %s) RETURNING id",
            (f"chat-buyer-{run_id}@example.test", "채팅 구매자"),
        )
        buyer_id = cur.fetchone()["id"]
        cur.execute("""
            INSERT INTO listing_requests
                (user_id, master_building_id, deal_type, contact_phone, deal_mode, status)
            VALUES (%s, %s, '매매', %s, 'direct', 'submitted')
            RETURNING id
        """, (seller_id, building["id"], "010-0000-0000"))
        listing_id = cur.fetchone()["id"]
        conn.commit()

        with client.session_transaction() as sess:
            sess["user_id"] = buyer_id
        blocked = client.post("/api/chat/rooms", json={"listing_request_id": listing_id})
        blocked_payload = blocked.get_json() or {}
        if blocked.status_code != 403 or blocked_payload.get("code") != "PHONE_VERIFICATION_REQUIRED":
            failures.append(
                "chat phone verification: 미인증 채팅 생성 응답이 "
                f"HTTP {blocked.status_code}, code={blocked_payload.get('code')} (기대: 403, PHONE_VERIFICATION_REQUIRED)"
            )
        else:
            print("OK  /api/chat/rooms 미인증 차단 (403, PHONE_VERIFICATION_REQUIRED)")

        cur.execute(
            "UPDATE users SET phone=%s, phone_verified=TRUE WHERE id=%s",
            ("010-1111-2222", buyer_id),
        )
        conn.commit()
        allowed = client.post("/api/chat/rooms", json={"listing_request_id": listing_id})
        allowed_payload = allowed.get_json() or {}
        if allowed.status_code != 200 or not allowed_payload.get("ok") or not allowed_payload.get("room_id"):
            failures.append("chat phone verification: 인증 후 채팅방 생성에 실패했습니다.")
        else:
            room_id = allowed_payload["room_id"]
            print("OK  /api/chat/rooms 인증 후 생성")
    except Exception as exc:
        failures.append(f"chat phone verification 테스트 오류: {exc}")
    finally:
        try:
            if room_id:
                cur.execute("DELETE FROM chat_messages WHERE room_id=%s", (room_id,))
                cur.execute("DELETE FROM chat_rooms WHERE id=%s", (room_id,))
            if listing_id:
                cur.execute("DELETE FROM listing_requests WHERE id=%s", (listing_id,))
            if buyer_id:
                cur.execute("DELETE FROM users WHERE id=%s", (buyer_id,))
            if seller_id:
                cur.execute("DELETE FROM users WHERE id=%s", (seller_id,))
            conn.commit()
        finally:
            cur.close()
            conn.close()
    return failures


def _check_room_inventory_contract_dates(client):
    """방 재고 만기일은 입실에만 보관되고, 소유자만 수정할 수 있어야 한다."""
    import time as _time
    from datetime import date, timedelta
    from db import get_conn

    failures = []
    run_id = str(int(_time.time() * 1000))
    conn = get_conn()
    cur = conn.cursor()
    owner_id = other_id = listing_id = room_id = None
    try:
        cur.execute("""
            SELECT is_nullable, column_default
              FROM information_schema.columns
             WHERE table_schema = current_schema()
               AND table_name = 'business_room_inventory'
               AND column_name = 'status'
        """)
        status_column = cur.fetchone()
        if (not status_column or status_column["is_nullable"] != "NO"
                or not status_column.get("column_default")):
            failures.append("room inventory: status가 NOT NULL 기본 공실 제약으로 마이그레이션되지 않음")
        cur.execute("SELECT id FROM master_buildings ORDER BY id LIMIT 1")
        building = cur.fetchone()
        if not building:
            return ["room inventory: 테스트용 master_buildings 행이 없습니다."]
        cur.execute(
            "INSERT INTO users (email, name) VALUES (%s, %s) RETURNING id",
            (f"room-owner-{run_id}@example.test", "방 재고 소유자"),
        )
        owner_id = cur.fetchone()["id"]
        cur.execute(
            "INSERT INTO users (email, name) VALUES (%s, %s) RETURNING id",
            (f"room-other-{run_id}@example.test", "방 재고 타인"),
        )
        other_id = cur.fetchone()["id"]
        cur.execute("""
            INSERT INTO listing_requests
                (user_id, master_building_id, deal_type, contact_phone, deal_mode, status)
            VALUES (%s, %s, '월세', %s, 'direct', 'submitted')
            RETURNING id
        """, (owner_id, building["id"], "010-0000-0000"))
        listing_id = cur.fetchone()["id"]
        conn.commit()

        contract_end_date = (date.today() + timedelta(days=30)).isoformat()
        with client.session_transaction() as sess:
            sess["user_id"] = owner_id
        created = client.post(
            f"/api/my/listing-requests/{listing_id}/rooms",
            json={
                "room_label": "201호",
                "status": "입실",
                "contract_end_date": contract_end_date,
            },
        )
        created_payload = created.get_json() or {}
        if created.status_code != 201 or not created_payload.get("ok"):
            failures.append(f"room inventory: 입실 방 추가 실패 (HTTP {created.status_code})")
            return failures
        room = created_payload.get("item") or {}
        room_id = room.get("id")
        if room.get("status") != "입실" or room.get("contract_end_date") != contract_end_date:
            failures.append("room inventory: 입실 방의 계약만기일이 저장되지 않음")

        invalid_create_body = client.post(
            f"/api/my/listing-requests/{listing_id}/rooms",
            json=[],
        )
        if invalid_create_body.status_code != 400:
            failures.append("room inventory: 객체가 아닌 추가 요청을 400으로 거부하지 않음")

        invalid_create_status = client.post(
            f"/api/my/listing-requests/{listing_id}/rooms",
            json={"room_label": "202호", "status": False},
        )
        if invalid_create_status.status_code != 400:
            failures.append("room inventory: false 상태값을 400으로 거부하지 않음")

        listed = client.get(f"/api/my/listing-requests/{listing_id}/rooms")
        listed_items = (listed.get_json() or {}).get("items") or []
        if listed.status_code != 200 or not any(
            item.get("id") == room_id and item.get("contract_end_date") == contract_end_date
            for item in listed_items
        ):
            failures.append("room inventory: 소유자 조회에서 계약만기일을 찾지 못함")

        invalid_date = client.put(
            f"/api/my/room-inventory/{room_id}",
            json={"status": "입실", "contract_end_date": "2026-99-99"},
        )
        if invalid_date.status_code != 400:
            failures.append("room inventory: 잘못된 날짜를 400으로 거부하지 않음")

        vacated = client.put(
            f"/api/my/room-inventory/{room_id}",
            json={"status": "공실", "contract_end_date": contract_end_date},
        )
        vacated_item = (vacated.get_json() or {}).get("item") or {}
        if (vacated.status_code != 200 or vacated_item.get("status") != "공실"
                or vacated_item.get("contract_end_date") is not None):
            failures.append("room inventory: 공실 전환 때 계약만기일이 초기화되지 않음")

        invalid_status = client.put(
            f"/api/my/room-inventory/{room_id}",
            json={"status": "만기임박", "contract_end_date": contract_end_date},
        )
        if invalid_status.status_code != 400:
            failures.append("room inventory: 만기임박 상태를 거부하지 않음")

        invalid_update_body = client.put(f"/api/my/room-inventory/{room_id}", json=[])
        if invalid_update_body.status_code != 400:
            failures.append("room inventory: 객체가 아닌 수정 요청을 400으로 거부하지 않음")

        with client.session_transaction() as sess:
            sess["user_id"] = other_id
        blocked = client.put(
            f"/api/my/room-inventory/{room_id}",
            json={"status": "입실", "contract_end_date": contract_end_date},
        )
        if blocked.status_code != 403:
            failures.append("room inventory: 타 사용자의 방 재고 수정을 403으로 차단하지 않음")
        if not failures:
            print("OK  방 재고 만기일 저장·공실 초기화·입실/공실 검증·소유자 권한")
    except Exception as exc:
        failures.append(f"room inventory 테스트 오류: {exc}")
    finally:
        try:
            if listing_id:
                cur.execute(
                    "DELETE FROM business_room_inventory WHERE listing_request_id=%s",
                    (listing_id,),
                )
                cur.execute("DELETE FROM listing_requests WHERE id=%s", (listing_id,))
            if other_id:
                cur.execute("DELETE FROM users WHERE id=%s", (other_id,))
            if owner_id:
                cur.execute("DELETE FROM users WHERE id=%s", (owner_id,))
            conn.commit()
        finally:
            cur.close()
            conn.close()
    return failures


def _check_listing_registrant_types(client):
    """신규 3분류 등록자유형 저장과 과거 agent 값 수정 호환성을 검증한다."""
    import time as _time
    from db import get_conn

    failures = []
    run_id = str(int(_time.time() * 1000))
    conn = get_conn()
    cur = conn.cursor()
    user_id = listing_id = None
    try:
        cur.execute("SELECT id FROM master_buildings ORDER BY id LIMIT 1")
        building = cur.fetchone()
        if not building:
            return ["listing registrant type: 테스트용 master_buildings 행이 없습니다."]
        cur.execute(
            """
            INSERT INTO users (email, name, phone, phone_verified)
            VALUES (%s, %s, '01000000000', TRUE)
            RETURNING id
            """,
            (f"registrant-type-{run_id}@example.test", "등록자유형 테스트"),
        )
        user_id = cur.fetchone()["id"]
        conn.commit()
        with client.session_transaction() as sess:
            sess.clear()
            sess["user_id"] = user_id

        created = client.post("/api/listing-requests", json={
            "master_building_id": building["id"],
            "deal_type": "단기임대",
            "deal_mode": "direct",
            "registrant_type": "building_owner",
        })
        created_item = created.get_json() or {}
        listing_id = created_item.get("id")
        if created.status_code != 200 or not listing_id:
            failures.append(
                f"listing registrant type: building_owner 등록 실패 (HTTP {created.status_code})"
            )
            return failures

        for value in ("business", "agent"):
            updated = client.put(
                f"/api/listing-requests/{listing_id}",
                json={"deal_type": "단기임대", "registrant_type": value},
            )
            payload = updated.get_json() or {}
            cur.execute(
                "SELECT registrant_type FROM listing_requests WHERE id=%s",
                (listing_id,),
            )
            stored = cur.fetchone() or {}
            if (
                updated.status_code != 200
                or not payload.get("ok")
                or stored.get("registrant_type") != value
            ):
                failures.append(
                    f"listing registrant type: {value} 수정 호환 실패 (HTTP {updated.status_code})"
                )
                break

        mine = client.get("/api/listing-requests/mine")
        items = (mine.get_json() or {}).get("items") or []
        if mine.status_code != 200 or not any(
            item.get("id") == listing_id and item.get("registrant_type") == "agent"
            for item in items
        ):
            failures.append("listing registrant type: 과거 agent 매물의뢰를 마이페이지 조회에서 찾지 못함")
        if not failures:
            print("OK  등록자유형 building_owner/business 및 과거 agent 수정·조회 호환")
    except Exception as exc:
        failures.append(f"listing registrant type 테스트 오류: {exc}")
    finally:
        try:
            if listing_id:
                cur.execute(
                    "DELETE FROM listing_request_history WHERE listing_request_id=%s",
                    (listing_id,),
                )
                cur.execute("DELETE FROM listing_requests WHERE id=%s", (listing_id,))
            if user_id:
                cur.execute("DELETE FROM users WHERE id=%s", (user_id,))
            conn.commit()
        finally:
            cur.close()
            conn.close()
    return failures


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
    captured_txn_id = None
    captured_other_txn_id = None
    captured_listing_id = None
    captured_user_id = None

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

            # ── ⑥a 지도 원형 배지 — 실거래만·직거래만·동시 조합 회귀 점검 ──
            # API가 같은 건물에서 두 수를 정확히 합산하는지 실제 DB fixture로 검증한다.
            def _assert_badge_counts(label, expected):
                _clear_caches()
                response = client.get(f"/api/buildings-geo?q={TEST_NAME}")
                items = (response.get_json() or {}).get("items", []) if response.status_code == 200 else []
                item = next((it for it in items if it.get("id") == captured_mb_id), None)
                got = (
                    (item or {}).get("txn_count"),
                    (item or {}).get("listing_count"),
                    (item or {}).get("total_count"),
                )
                if response.status_code != 200 or got != expected:
                    failures.append(
                        f"지도 배지 {label}: {got} (기대: {expected}, HTTP={response.status_code})"
                    )
                else:
                    print(f"OK  지도 배지 {label}: {got}")

            cur.execute(
                "INSERT INTO users (email, name) VALUES (%s, %s) RETURNING id",
                (f"map-badge-{_run_ms}@example.test", "지도 배지 테스트"),
            )
            captured_user_id = cur.fetchone()["id"]
            cur.execute("""
                INSERT INTO transactions
                    (building_name, address, price, deal_date, deal_type,
                     sgg_cd, umd_nm, jibun, raw_key)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                TEST_NAME, f"{REAL_UMD_NM} {TEST_JIBUN}", 10000, "2026-08-21",
                "직거래", REAL_SGG_CD, REAL_UMD_NM, TEST_JIBUN,
                f"map-badge-{_run_ms}",
            ))
            captured_txn_id = cur.fetchone()["id"]
            # 같은 필지지만 건물명이 다른 거래는, 정확 이름 거래가 있으면 배지 건수에서 제외된다.
            cur.execute("""
                INSERT INTO transactions
                    (building_name, address, price, deal_date, deal_type,
                     sgg_cd, umd_nm, jibun, raw_key)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                TEST_NAME + " 별관", f"{REAL_UMD_NM} {TEST_JIBUN}", 11000, "2026-08-20",
                "직거래", REAL_SGG_CD, REAL_UMD_NM, TEST_JIBUN,
                f"map-badge-other-{_run_ms}",
            ))
            captured_other_txn_id = cur.fetchone()["id"]
            conn.commit()
            _assert_badge_counts("실거래만", (1, 0, 1))

            cur.execute("""
                INSERT INTO listing_requests
                    (user_id, master_building_id, deal_type, contact_phone, deal_mode, status)
                VALUES (%s, %s, '매매', '01000000000', 'direct', 'submitted')
                RETURNING id
            """, (captured_user_id, captured_mb_id))
            captured_listing_id = cur.fetchone()["id"]
            # 중개 매물과 두 철회 표기는 지도 공개 직거래 집계에서 제외되어야 한다.
            cur.execute("""
                INSERT INTO listing_requests
                    (user_id, master_building_id, deal_type, contact_phone, deal_mode, status)
                VALUES
                    (%s, %s, '매매', '01000000000', 'broker', 'submitted'),
                    (%s, %s, '매매', '01000000000', 'direct', 'withdrawn'),
                    (%s, %s, '매매', '01000000000', 'direct', '철회됨')
            """, (
                captured_user_id, captured_mb_id,
                captured_user_id, captured_mb_id,
                captured_user_id, captured_mb_id,
            ))
            conn.commit()
            _assert_badge_counts("실거래+직거래 매물", (1, 1, 2))

            cur.execute("DELETE FROM transactions WHERE id=%s", (captured_txn_id,))
            captured_txn_id = None
            cur.execute("DELETE FROM transactions WHERE id=%s", (captured_other_txn_id,))
            captured_other_txn_id = None
            conn.commit()
            _assert_badge_counts("직거래 매물만", (0, 1, 1))

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
            if captured_txn_id:
                cur.execute("DELETE FROM transactions WHERE id=%s", (captured_txn_id,))
            if captured_other_txn_id:
                cur.execute("DELETE FROM transactions WHERE id=%s", (captured_other_txn_id,))
            if captured_listing_id:
                cur.execute("DELETE FROM listing_requests WHERE id=%s", (captured_listing_id,))
            if captured_user_id:
                cur.execute("DELETE FROM listing_requests WHERE user_id=%s", (captured_user_id,))
            if captured_req_id:
                cur.execute(
                    "DELETE FROM building_requests WHERE id=%s", (captured_req_id,)
                )
            if captured_mb_id:
                cur.execute(
                    "DELETE FROM master_buildings WHERE id=%s", (captured_mb_id,)
                )
            if captured_user_id:
                cur.execute("DELETE FROM users WHERE id=%s", (captured_user_id,))
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
