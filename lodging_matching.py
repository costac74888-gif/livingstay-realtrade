# -*- coding: utf-8 -*-
"""행안부 숙박업 신고와 건물 마스터의 주소 매칭·자동명칭 공통 로직."""

from psycopg2.extras import execute_values

from addr_norm import get_building_jibun_key, normalize_road_prefix


ACTIVE_STATUS = "영업/정상"


def matched_lodgings(cur, building, active_only=True):
    """건물 주소에 매칭되는 신고사업장을 반환한다.

    도로명 키에 활성 사업장이 하나라도 있으면 도로명 결과만 사용하고,
    없을 때만 지번 키를 보조로 사용한다. 사업장명 유사도는 매칭 근거로
    사용하지 않는다.
    """
    status_clause = " AND lr.biz_status_name = %s" if active_only else ""
    status_params = [ACTIVE_STATUS] if active_only else []
    road_norm = normalize_road_prefix(building.get("road_address"))
    if road_norm:
        cur.execute(
            f"""
            SELECT lr.biz_name, lr.permit_number, lr.permit_date,
                   lr.biz_status_name, lr.biz_status_detail, lr.room_count,
                   lr.hygiene_type, lr.phone, lr.road_address, lr.jibun_address,
                   lr.source_updated_at, lr.biz_name_norm, lr.road_norm, lr.jibun_norm,
                   lr.facility_area, lr.camping_site_count,
                   lr.camping_general_site_count, lr.camping_auto_site_count,
                   lr.camping_glamping_site_count, lr.camping_caravan_site_count,
                   lr.camping_classification, lr.camping_location_types,
                   lr.camping_theme_types, lr.camping_amenities,
                   lr.camping_toilet_count, lr.camping_shower_count,
                   lr.camping_sink_count, lr.camping_operating_seasons,
                   lr.camping_animal_policy, lr.camping_reservation_url,
                   lr.camping_first_image_url
            FROM lodging_registry lr
            WHERE lr.road_norm = %s{status_clause}
            """,
            [road_norm] + status_params,
        )
        rows = cur.fetchall()
        if rows:
            return [dict(row) for row in rows], "road"

    jibun_key = get_building_jibun_key(building)
    if jibun_key:
        cur.execute(
            f"""
            SELECT lr.biz_name, lr.permit_number, lr.permit_date,
                   lr.biz_status_name, lr.biz_status_detail, lr.room_count,
                   lr.hygiene_type, lr.phone, lr.road_address, lr.jibun_address,
                   lr.source_updated_at, lr.biz_name_norm, lr.road_norm, lr.jibun_norm,
                   lr.facility_area, lr.camping_site_count,
                   lr.camping_general_site_count, lr.camping_auto_site_count,
                   lr.camping_glamping_site_count, lr.camping_caravan_site_count,
                   lr.camping_classification, lr.camping_location_types,
                   lr.camping_theme_types, lr.camping_amenities,
                   lr.camping_toilet_count, lr.camping_shower_count,
                   lr.camping_sink_count, lr.camping_operating_seasons,
                   lr.camping_animal_policy, lr.camping_reservation_url,
                   lr.camping_first_image_url
            FROM lodging_registry lr
            WHERE lr.jibun_norm = %s{status_clause}
            """,
            [jibun_key] + status_params,
        )
        return [dict(row) for row in cur.fetchall()], "jibun"
    return [], None


def _permit_date_sort_value(value):
    """YYYYMMDD/ISO 문자열을 신고일 정렬용 값으로 정규화한다."""
    if value is None:
        return ""
    return "".join(ch for ch in str(value).strip() if ch.isdigit())[:8]


def choose_representative(rows):
    """객실수 내림차순, 신고일 최신순으로 대표 사업장을 선택한다."""
    if not rows:
        return None
    return max(
        rows,
        key=lambda row: (
            int(row.get("room_count") or 0),
            _permit_date_sort_value(row.get("permit_date")),
            # 동일 데이터가 완전히 같을 때도 결과가 실행마다 흔들리지 않게 한다.
            str(row.get("permit_number") or ""),
        ),
    )


def refresh_auto_building_names(conn, building_ids=None):
    """미확정 일반숙박 건물의 신고 기준 임시 명칭을 다시 계산한다.

    확정 명칭과 활성 후보가 없는 건물은 건드리지 않는다. 대상 건물과
    활성 신고를 각각 한 번에 읽어, 대량 백필 후에도 원격 DB 왕복 없이
    도로명 우선·지번 보조 규칙으로 대표 사업장을 선택한다.
    """
    cur = conn.cursor()
    try:
        params = []
        where = [
            "name_pending IS TRUE",
            "lodging_type = '일반'",
            "building_name_source IS DISTINCT FROM 'official'",
            "building_name_source IS DISTINCT FROM 'user'",
        ]
        if building_ids:
            where.append("id = ANY(%s)")
            params.append(building_ids)
        cur.execute(
            f"""
            SELECT id, building_name, building_name_source,
                   building_name_candidate_count,
                   building_name_pending_base,
                   umd_nm, jibun, road_address, jibun_address
            FROM master_buildings
            WHERE {' AND '.join(where)}
            ORDER BY id
            """,
            params,
        )
        buildings = [dict(row) for row in cur.fetchall()]
        if not buildings:
            return 0

        building_keys = []
        road_norms = set()
        jibun_norms = set()
        for building in buildings:
            road_norm = normalize_road_prefix(building.get("road_address"))
            jibun_norm = get_building_jibun_key(building)
            building_keys.append((building, road_norm, jibun_norm))
            if road_norm:
                road_norms.add(road_norm)
            if jibun_norm:
                jibun_norms.add(jibun_norm)

        cur.execute(
            """
            SELECT biz_name, permit_number, permit_date, room_count,
                   road_norm, jibun_norm
            FROM lodging_registry
            WHERE biz_status_name = %s
              AND (road_norm = ANY(%s) OR jibun_norm = ANY(%s))
            """,
            (ACTIVE_STATUS, list(road_norms) or ["__none__"],
             list(jibun_norms) or ["__none__"]),
        )
        road_matches = {}
        jibun_matches = {}
        for row in cur.fetchall():
            lodging = dict(row)
            permit_number = lodging["permit_number"]
            if lodging.get("road_norm"):
                road_matches.setdefault(lodging["road_norm"], {})[permit_number] = lodging
            if lodging.get("jibun_norm"):
                jibun_matches.setdefault(lodging["jibun_norm"], {})[permit_number] = lodging

        updates = []
        for building, road_norm, jibun_norm in building_keys:
            road_rows = list(road_matches.get(road_norm, {}).values()) if road_norm else []
            rows = road_rows or (
                list(jibun_matches.get(jibun_norm, {}).values()) if jibun_norm else []
            )
            representative = choose_representative(rows)
            # 활성 후보가 없으면 자동명명 보류: 기존 이름과 출처를 건드리지 않는다.
            if not representative:
                continue
            next_name = (representative.get("biz_name") or "").strip()
            if not next_name:
                continue
            next_source = "lodging_report"
            if (
                building.get("building_name") != next_name
                or building.get("building_name_source") != next_source
                or (building.get("building_name_candidate_count") or 0) != len(rows)
            ):
                updates.append((building["id"], next_name, next_source, len(rows)))

        updated = 0
        for start in range(0, len(updates), 1000):
            batch = updates[start:start + 1000]
            execute_values(
                cur,
                """
                UPDATE master_buildings AS mb
                   SET building_name = values.building_name,
                       building_name_source = values.building_name_source,
                       building_name_candidate_count = values.candidate_count,
                       building_name_pending_base = COALESCE(
                           mb.building_name_pending_base,
                           CASE WHEN mb.building_name_source <> 'lodging_report'
                                THEN mb.building_name ELSE NULL END
                       )
                  FROM (VALUES %s) AS values(
                      id, building_name, building_name_source, candidate_count
                  )
                 WHERE mb.id = values.id
                   AND mb.name_pending IS TRUE
                   AND mb.lodging_type = '일반'
                   AND mb.building_name_source IS DISTINCT FROM 'official'
                   AND mb.building_name_source IS DISTINCT FROM 'user'
                """,
                batch,
                template="(%s, %s, %s, %s)",
                page_size=len(batch),
            )
            updated += cur.rowcount
        conn.commit()
        return updated
    finally:
        cur.close()