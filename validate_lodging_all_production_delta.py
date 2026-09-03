"""8종 정부 숙박 staging을 운영 원장·건물 마스터와 비교하는 읽기 전용 검증기."""

import argparse
import json
import os
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import psycopg2
import psycopg2.extras

from addr_norm import get_building_jibun_key, normalize_jibun_prefix, normalize_road_prefix
from db import get_conn
from lodging_data_contract import GOVERNMENT_LODGING_SOURCES


def _room_count(raw_record):
    value = (raw_record or {}).get("객실수")
    if value in (None, ""):
        return 0
    try:
        return int(Decimal(str(value).replace(",", "")))
    except (InvalidOperation, TypeError, ValueError):
        return 0


def _json_default(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return int(value)
    raise TypeError(type(value).__name__)


def classify_production_match(road_key, jibun_key, road_index, jibun_index):
    """운영 건물 마스터에서 신규 신고 주소의 후보를 분류한다."""
    road_ids = tuple(sorted(road_index.get(road_key, ()))) if road_key else ()
    jibun_ids = tuple(sorted(jibun_index.get(jibun_key, ()))) if jibun_key else ()
    if not road_key and not jibun_key:
        return "no_address", (), None
    if len(road_ids) == 1:
        if len(jibun_ids) == 1 and road_ids[0] != jibun_ids[0]:
            return "address_conflict", tuple(sorted(set(road_ids + jibun_ids))), None
        return "existing_building", road_ids, road_ids[0]
    if len(road_ids) > 1:
        return "ambiguous_existing_building", road_ids, None
    if len(jibun_ids) == 1:
        return "existing_building", jibun_ids, jibun_ids[0]
    if len(jibun_ids) > 1:
        return "ambiguous_existing_building", jibun_ids, None
    return "new_building_candidate", (), None


def _fetch_staging(batch_ids):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT sb.id, sb.source_key, sb.reference_date, sb.total_rows,
                   sr.row_number, sr.permit_number, sr.biz_name,
                   sr.status_bucket, sr.road_address, sr.jibun_address,
                   sr.raw_record
              FROM lodging_source_batches sb
              JOIN lodging_source_rows sr ON sr.batch_id=sb.id
             WHERE sb.id = ANY(%s)
             ORDER BY sb.source_key, sr.row_number
            """,
            (list(batch_ids),),
        )
        rows = [dict(row) for row in cur.fetchall()]
        if not rows:
            raise RuntimeError("분석할 staging 행이 없습니다.")
        batches = {}
        for row in rows:
            batches[row["id"]] = {
                "id": row["id"],
                "source_key": row["source_key"],
                "reference_date": row["reference_date"],
                "total_rows": row["total_rows"],
            }
        return list(batches.values()), rows
    finally:
        cur.close()
        conn.close()


def _fetch_production():
    production_url = os.environ.get("PROD_DATABASE_URL")
    if not production_url:
        raise RuntimeError("PROD_DATABASE_URL이 없어 운영 검증을 실행할 수 없습니다.")
    conn = psycopg2.connect(production_url, connect_timeout=10)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(
            """
            SELECT permit_number, biz_name, biz_status_name, room_count,
                   camping_site_count, applied_building_id, road_address,
                   jibun_address
              FROM lodging_registry
            """
        )
        registry = [dict(row) for row in cur.fetchall()]
        cur.execute(
            """
            SELECT id, road_address, jibun_address, lat, lng, lodging_type
              FROM master_buildings
            """
        )
        buildings = [dict(row) for row in cur.fetchall()]
        return registry, buildings
    finally:
        cur.close()
        conn.close()


def _address_key(row):
    return (
        normalize_road_prefix(row.get("road_address"))
        or normalize_jibun_prefix(row.get("jibun_address"))
        or None
    )


def _new_building_match(row, road_index, jibun_index):
    return classify_production_match(
        normalize_road_prefix(row.get("road_address")),
        normalize_jibun_prefix(row.get("jibun_address")),
        road_index,
        jibun_index,
    )


def validate(batch_ids, sample_limit=5):
    batches, staging_rows = _fetch_staging(batch_ids)
    registry_rows, building_rows = _fetch_production()
    registry_by_permit = {
        row["permit_number"]: row
        for row in registry_rows
        if row.get("permit_number")
    }
    road_index = defaultdict(set)
    jibun_index = defaultdict(set)
    for building in building_rows:
        road_key = normalize_road_prefix(building.get("road_address"))
        jibun_key = get_building_jibun_key(building)
        if road_key:
            road_index[road_key].add(building["id"])
        if jibun_key:
            jibun_index[jibun_key].add(building["id"])

    rows_by_source = defaultdict(list)
    for row in staging_rows:
        rows_by_source[row["source_key"]].append(row)

    overall_status = Counter()
    overall_new_status = Counter()
    overall_match = Counter()
    overall_new_addresses = {}
    overall_existing_active_permits = 0
    overall_existing_active_rooms = 0
    source_results = {}

    for source_key, source_rows in sorted(rows_by_source.items()):
        status_counts = Counter(row.get("status_bucket") or "unknown" for row in source_rows)
        new_rows = [
            row for row in source_rows
            if row.get("permit_number") not in registry_by_permit
        ]
        new_status = Counter(row.get("status_bucket") or "unknown" for row in new_rows)
        match_counts = Counter()
        new_addresses = defaultdict(list)
        samples = defaultdict(list)
        new_rooms = 0
        new_active_rooms = 0
        for row in new_rows:
            state, candidate_ids, building_id = _new_building_match(
                row, road_index, jibun_index
            )
            match_counts[state] += 1
            rooms = _room_count(row.get("raw_record"))
            new_rooms += rooms
            if row.get("status_bucket") == "active":
                new_active_rooms += rooms
            if state == "new_building_candidate":
                address_key = _address_key(row) or f"row:{row['row_number']}"
                new_addresses[address_key].append(row.get("permit_number"))
                overall_new_addresses.setdefault(
                    address_key, []
                ).append(row.get("permit_number"))
            if len(samples[state]) < sample_limit:
                samples[state].append({
                    "permit_number": row.get("permit_number"),
                    "biz_name": row.get("biz_name"),
                    "status_bucket": row.get("status_bucket"),
                    "rooms": rooms,
                    "road_address": row.get("road_address"),
                    "jibun_address": row.get("jibun_address"),
                    "candidate_ids": list(candidate_ids)[:10],
                })

        existing_rows = [
            row for row in source_rows
            if row.get("permit_number") in registry_by_permit
        ]
        current_registry_active = sum(
            registry_by_permit[row["permit_number"]].get("biz_status_name")
            == "영업/정상"
            for row in existing_rows
        )
        current_registry_rooms = sum(
            int(registry_by_permit[row["permit_number"]].get("room_count") or 0)
            for row in existing_rows
            if registry_by_permit[row["permit_number"]].get("biz_status_name")
            == "영업/정상"
        )
        overall_existing_active_permits += current_registry_active
        overall_existing_active_rooms += current_registry_rooms
        linked_existing_buildings = len({
            registry_by_permit[row["permit_number"]]["applied_building_id"]
            for row in existing_rows
            if registry_by_permit[row["permit_number"]].get("applied_building_id")
            is not None
        })
        source_results[source_key] = {
            "label": GOVERNMENT_LODGING_SOURCES.get(source_key, {}).get(
                "label", source_key
            ),
            "staging_rows": len(source_rows),
            "status_counts": dict(status_counts),
            "production_existing_permits": len(existing_rows),
            "new_permits": len(new_rows),
            "new_status_counts": dict(new_status),
            "production_existing_active_permits": current_registry_active,
            "production_existing_active_rooms": current_registry_rooms,
            "production_linked_buildings": linked_existing_buildings,
            "new_match_counts": dict(match_counts),
            "new_existing_building_rows": match_counts["existing_building"],
            "new_building_candidate_rows": match_counts["new_building_candidate"],
            "new_building_candidate_unique_addresses": len(new_addresses),
            "new_building_candidate_duplicate_rows": sum(
                max(0, len(values) - 1) for values in new_addresses.values()
            ),
            "new_active_permits": new_status["active"],
            "new_active_rooms": new_active_rooms,
            "new_rooms": new_rooms,
            "estimated_after_apply": {
                "registry_rows": len(existing_rows) + len(new_rows),
                "active_permits": status_counts["active"],
                "staging_reported_active_rooms": sum(
                    _room_count(row.get("raw_record"))
                    for row in source_rows
                    if row.get("status_bucket") == "active"
                ),
                "new_buildings": len(new_addresses),
            },
            "samples": dict(samples),
        }
        overall_status.update(status_counts)
        overall_new_status.update(new_status)
        overall_match.update(match_counts)

    overall_new_permits = sum(
        result["new_permits"] for result in source_results.values()
    )
    overall_existing_permits = sum(
        result["production_existing_permits"] for result in source_results.values()
    )
    overall_active_rooms = sum(
        result["estimated_after_apply"]["staging_reported_active_rooms"]
        for result in source_results.values()
    )
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "read_only": True,
        "production_baseline": True,
        "batches": batches,
        "staging_rows": len(staging_rows),
        "production_registry_rows": len(registry_rows),
        "production_master_buildings": len(building_rows),
        "overall": {
            "status_counts": dict(overall_status),
            "production_existing_permits": overall_existing_permits,
            "new_permits": overall_new_permits,
            "new_status_counts": dict(overall_new_status),
            "new_match_counts": dict(overall_match),
            "new_existing_building_rows": overall_match["existing_building"],
            "new_building_candidate_rows": overall_match["new_building_candidate"],
            "new_building_candidate_unique_addresses": len(overall_new_addresses),
            "new_building_candidate_duplicate_rows": sum(
                max(0, len(values) - 1)
                for values in overall_new_addresses.values()
            ),
            "new_active_permits": overall_new_status["active"],
            "new_active_rooms": sum(
                result["new_active_rooms"] for result in source_results.values()
            ),
            "production_existing_active_permits": overall_existing_active_permits,
            "production_existing_active_rooms": overall_existing_active_rooms,
            "staging_reported_active_rooms": overall_active_rooms,
            "active_permits_after_apply": overall_status["active"],
            "active_permits_net_change": (
                overall_status["active"] - overall_existing_active_permits
            ),
            "room_count_quality_gate": {
                "safe_to_replace_existing_values": False,
                "reason": "CSV 객실수 공란·집계 기준 차이로 기존 운영 합계보다 작음",
                "preserve_existing_when_csv_blank": True,
                "new_permits_reported_active_rooms": sum(
                    result["new_active_rooms"] for result in source_results.values()
                ),
            },
        },
        "estimated_after_apply": {
            "registry_rows": len(registry_rows) + overall_new_permits,
            "master_buildings": (
                len(building_rows) + len(overall_new_addresses)
            ),
            "active_permits": overall_status["active"],
            "active_permits_net_change": (
                overall_status["active"] - overall_existing_active_permits
            ),
            "active_rooms": None,
            "active_rooms_reason": (
                "기존 호실 보존 규칙을 적용한 뒤에만 확정 가능"
            ),
            "new_master_buildings": len(overall_new_addresses),
        },
        "by_source": source_results,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-id", type=int, action="append", required=True)
    parser.add_argument("--sample-limit", type=int, default=5)
    parser.add_argument("--output")
    args = parser.parse_args()
    result = validate(args.batch_id, args.sample_limit)
    text = json.dumps(result, ensure_ascii=False, indent=2, default=_json_default)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
    print(text)


if __name__ == "__main__":
    main()