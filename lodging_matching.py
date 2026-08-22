# -*- coding: utf-8 -*-
"""행안부 숙박업 신고와 건물 마스터의 주소 매칭·자동명칭 공통 로직."""

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
                   lr.source_updated_at, lr.biz_name_norm
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
                   lr.source_updated_at, lr.biz_name_norm
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

    확정 명칭(name_pending=FALSE)은 절대 수정하지 않는다. 자동명이었던
    건물에서 활성 후보가 사라지면 원래 지번 기반 임시명으로 되돌려 다음
    동기화에서 폐업/재개업 상태가 정확히 반영되게 한다.
    """
    cur = conn.cursor()
    try:
        params = []
        where = [
            "name_pending IS TRUE",
            "lodging_type = '일반'",
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
        updated = 0
        for building in buildings:
            rows, match_source = matched_lodgings(cur, building, active_only=True)
            representative = choose_representative(rows)
            if representative:
                next_name = (representative.get("biz_name") or "").strip()
                if not next_name:
                    continue
                next_source = "lodging_report"
            else:
                next_name = (
                    building.get("building_name_pending_base")
                    or f"{building.get('umd_nm') or ''} {building.get('jibun') or ''}".strip()
                    or building.get("jibun_address")
                    or building.get("road_address")
                    or building.get("building_name")
                )
                next_source = "pending"
            if (
                building.get("building_name") != next_name
                or building.get("building_name_source") != next_source
                or (building.get("building_name_candidate_count") or 0) != len(rows)
            ):
                cur.execute(
                    """
                    UPDATE master_buildings
                       SET building_name=%s,
                           building_name_source=%s,
                           building_name_candidate_count=%s,
                           building_name_pending_base=COALESCE(
                               building_name_pending_base,
                               CASE WHEN building_name_source <> 'lodging_report'
                                    THEN building_name ELSE NULL END
                           )
                     WHERE id=%s
                       AND name_pending IS TRUE
                       AND lodging_type='일반'
                    """,
                    (next_name, next_source, len(rows), building["id"]),
                )
                updated += cur.rowcount
        conn.commit()
        return updated
    finally:
        cur.close()