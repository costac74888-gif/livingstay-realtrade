"""정부 숙박 staging을 운영 원장·건물 마스터와 비교하는 읽기 전용 검증기."""

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


FOREIGN_SOURCE = "foreign_city_homestay"
FOREIGN_HYGIENE_TYPE = "외국인관광도시민박업"


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


def _fetch_staging(batch_id):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT sb.id, sb.source_key, sb.reference_date, sb.total_rows,
                   sr.id AS source_row_id, sr.row_number, sr.permit_number,
                   sr.biz_name, sr.status_bucket, sr.road_address,
                   sr.jibun_address, sr.raw_record
              FROM lodging_source_batches sb
              JOIN lodging_source_rows sr ON sr.batch_id=sb.id
             WHERE sb.id=%s
             ORDER BY sr.row_number
            """,
            (batch_id,),
        )
        rows = [dict(row) for row in cur.fetchall()]
        if not rows:
            raise RuntimeError(f"staging 배치 {batch_id}를 찾을 수 없습니다.")
        batch = {
            "id": rows[0]["id"],
            "source_key": rows[0]["source_key"],
            "reference_date": rows[0]["reference_date"],
            "total_rows": rows[0]["total_rows"],
        }
        return batch, rows
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
                   applied_building_id, road_address, jibun_address,
                   road_norm, jibun_norm
              FROM lodging_registry
             WHERE hygiene_type=%s
            """,
            (FOREIGN_HYGIENE_TYPE,),
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


def validate(batch_id, sample_limit=20):
    batch, staging_rows = _fetch_staging(batch_id)
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

    counts = Counter()
    by_status = Counter()
    samples = defaultdict(list)
    new_building_addresses = defaultdict(list)
    existing_linked_building_ids = set()
    new_rows = []
    for row in staging_rows:
        permit = row.get("permit_number")
        current = registry_by_permit.get(permit)
        if current:
            counts["existing_permits"] += 1
            if current.get("applied_building_id") is not None:
                counts["existing_permits_with_building"] += 1
                existing_linked_building_ids.add(current["applied_building_id"])
            continue

        counts["new_permits"] += 1
        by_status[row.get("status_bucket") or "unknown"] += 1
        if row.get("status_bucket") == "active":
            counts["new_active_permits"] += 1
            counts["new_active_rooms"] += _room_count(row.get("raw_record"))
        elif row.get("status_bucket") == "temporarily_closed":
            counts["new_temporarily_closed_permits"] += 1
            counts["new_temporarily_closed_rooms"] += _room_count(row.get("raw_record"))
        state, candidate_ids, building_id = classify_production_match(
            normalize_road_prefix(row.get("road_address")),
            normalize_jibun_prefix(row.get("jibun_address")),
            road_index,
            jibun_index,
        )
        counts[f"new:{state}"] += 1
        if building_id:
            counts["new_permits_matching_existing_building"] += 1
        if state == "new_building_candidate":
            address_key = (
                normalize_road_prefix(row.get("road_address"))
                or normalize_jibun_prefix(row.get("jibun_address"))
                or f"row:{row['row_number']}"
            )
            new_building_addresses[address_key].append(row["permit_number"])
        new_rows.append({
            "permit_number": permit,
            "biz_name": row.get("biz_name"),
            "status_bucket": row.get("status_bucket"),
            "rooms": _room_count(row.get("raw_record")),
            "match_state": state,
            "candidate_ids": list(candidate_ids)[:10],
            "road_address": row.get("road_address"),
            "jibun_address": row.get("jibun_address"),
        })
        if len(samples[state]) < sample_limit:
            samples[state].append(new_rows[-1])

    counts["new_building_candidate_unique_addresses"] = len(new_building_addresses)
    counts["new_building_candidate_duplicate_rows"] = sum(
        max(0, len(permits) - 1) for permits in new_building_addresses.values()
    )
    production_active_rows = [
        row for row in registry_rows if row.get("biz_status_name") == "영업/정상"
    ]
    production_active_rooms = sum(
        int(row.get("room_count") or 0) for row in production_active_rows
    )
    new_building_count = counts["new_building_candidate_unique_addresses"]
    result = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "read_only": True,
        "production_baseline": True,
        "source_key": FOREIGN_SOURCE,
        "batch": batch,
        "staging_rows": len(staging_rows),
        "production_registry_rows": len(registry_rows),
        "production_linked_buildings": len(existing_linked_building_ids),
        "production_master_buildings": len(building_rows),
        "counts": dict(counts),
        "new_by_status": dict(by_status),
        "estimated_after_apply": {
            "production_master_buildings": len(building_rows) + new_building_count,
            "foreign_registry_rows": len(registry_rows) + counts["new_permits"],
            "foreign_active_permits": (
                len(production_active_rows) + counts["new_active_permits"]
            ),
            "foreign_active_rooms": (
                production_active_rooms + counts["new_active_rooms"]
            ),
            "new_master_buildings": new_building_count,
        },
        "new_rows": new_rows,
        "samples": dict(samples),
    }
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-id", type=int, required=True)
    parser.add_argument("--sample-limit", type=int, default=20)
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