"""Preview and apply admin-uploaded lodging registry source files."""

from __future__ import annotations

from collections import Counter

from db import get_conn
from lodging_classification import ACTIVE_STATUS


def _importer(source):
    if source == "airbnb":
        import import_airbnb_lodging as module
    elif source == "rural":
        import import_rural_lodging as module
    elif source == "hanok":
        import import_hanok_lodging as module
    else:
        raise ValueError("지원하지 않는 숙박 원본입니다.")
    return module


def allowed_extensions(source):
    return {"csv"} if source == "rural" else {"csv", "xlsx"}


def preview_file(source, filepath):
    """Parse and match a file without mutating either registry or master data."""
    module = _importer(source)
    rows = module.read_rows(filepath) if source == "rural" else module.common.read_rows(filepath) if source == "hanok" else module.read_rows(filepath)
    parsed = [data for data in (module.parse_row(row) for row in rows) if data]
    permit_counts = Counter(data["permit_number"] for data in parsed)
    unique = {}
    for data in parsed:
        unique[data["permit_number"]] = data
    records = list(unique.values())

    conn = get_conn()
    cur = conn.cursor()
    try:
        permits = list(unique)
        existing = set()
        for offset in range(0, len(permits), 5000):
            cur.execute(
                "SELECT permit_number FROM lodging_registry WHERE permit_number = ANY(%s)",
                (permits[offset:offset + 5000],),
            )
            existing.update(row["permit_number"] for row in cur.fetchall())
        common = module.common if hasattr(module, "common") else module
        road_index, jibun_index = common._load_master_indexes(cur)
        matched = 0
        for data in records:
            if data.get("biz_status_name") != ACTIVE_STATUS:
                continue
            building_id, _reason = common._match_master(data, road_index, jibun_index)
            if building_id:
                matched += 1
    finally:
        cur.close()
        conn.close()

    active = sum(1 for data in records if data.get("biz_status_name") == ACTIVE_STATUS)
    inactive = len(records) - active
    return {
        "total_rows": len(rows),
        "valid_rows": len(records),
        "skipped_rows": len(rows) - len(parsed),
        "duplicate_rows": sum(count - 1 for count in permit_counts.values()),
        "active_rows": active,
        "inactive_rows": inactive,
        "new_rows": len(records) - len(existing),
        "update_rows": len(existing),
        "matched_existing_buildings": matched,
        "unmatched_active_rows": max(0, active - matched),
        "samples": [
            {
                "permit_number": data["permit_number"],
                "biz_name": data.get("biz_name"),
                "status": data.get("biz_status_name"),
                "address": data.get("road_address") or data.get("jibun_address"),
            }
            for data in records[:10]
        ],
    }


def run_import(source, filepath):
    return _importer(source).run(filepath, dry_run=False)