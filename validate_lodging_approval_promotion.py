"""정부 숙박 8종 승인 배치를 운영 원장과 다시 비교하는 읽기 전용 dry-run."""

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
from lodging_staging import _database_fingerprint
from validate_lodging_all_production_delta import classify_production_match


def parse_optional_room_count(raw_record):
    value = (raw_record or {}).get("객실수")
    if value is None or not str(value).strip():
        return None
    try:
        return int(Decimal(str(value).replace(",", "").strip()))
    except (InvalidOperation, TypeError, ValueError):
        return None


def classify_registry_action(payload, existing):
    if not existing:
        return "insert"
    if (existing.get("biz_status_name") or "") != (payload.get("raw_status") or ""):
        return "status_change"
    comparisons = (
        ("biz_name", "biz_name"),
        ("road_address", "road_address"),
        ("jibun_address", "jibun_address"),
        ("raw_hygiene_type", "hygiene_type"),
    )
    for payload_key, existing_key in comparisons:
        if (payload.get(payload_key) or "") != (existing.get(existing_key) or ""):
            return "update"
    room_count = parse_optional_room_count(payload.get("raw_record"))
    if room_count is not None and room_count != existing.get("room_count"):
        return "update"
    return "unchanged"


def _fetch_approved_rows():
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT DISTINCT ON (source_key)
                   id, source_key, reference_date, file_sha256, status,
                   total_rows, valid_rows, review_rows
              FROM lodging_source_batches
             ORDER BY source_key, reference_date DESC, created_at DESC, id DESC
            """
        )
        batches = {row["source_key"]: dict(row) for row in cur.fetchall()}
        missing_sources = set(GOVERNMENT_LODGING_SOURCES) - set(batches)
        if missing_sources:
            raise RuntimeError(
                "최신 staging 배치가 없는 원본: " + ", ".join(sorted(missing_sources))
            )

        approved_rows = []
        readiness = {}
        for source_key in GOVERNMENT_LODGING_SOURCES:
            batch = batches[source_key]
            cur.execute(
                """
                SELECT COUNT(*) AS count
                  FROM lodging_source_rows
                 WHERE batch_id=%s
                   AND row_state='validated'
                   AND diff_kind <> 'unchanged'
                """,
                (batch["id"],),
            )
            changed_count = int(cur.fetchone()["count"])
            cur.execute(
                """
                SELECT id, status, row_count, run_id
                  FROM lodging_approval_batches
                 WHERE source_batch_id=%s
                """,
                (batch["id"],),
            )
            approval = cur.fetchone()
            if changed_count:
                if not approval or approval["status"] != "dry_run":
                    raise RuntimeError(
                        f"{source_key} 변경 {changed_count}건이 승인 dry-run 상태가 아닙니다."
                    )
                if int(approval["row_count"] or 0) != changed_count:
                    raise RuntimeError(
                        f"{source_key} 승인 행 수가 staging 변경 행 수와 다릅니다."
                    )
                cur.execute(
                    """
                    SELECT ar.payload
                      FROM lodging_approval_rows ar
                     WHERE ar.approval_batch_id=%s
                     ORDER BY ar.source_row_id
                    """,
                    (approval["id"],),
                )
                rows = [dict(row["payload"]) for row in cur.fetchall()]
                if len(rows) != changed_count:
                    raise RuntimeError(
                        f"{source_key} 승인 payload 행 수가 고정된 row_count와 다릅니다."
                    )
                for row in rows:
                    row["_source_key"] = source_key
                    row["_approval_run_id"] = approval["run_id"]
                approved_rows.extend(rows)
            elif approval and int(approval["row_count"] or 0):
                raise RuntimeError(
                    f"{source_key}는 변경이 없지만 승인 행이 남아 있습니다."
                )
            readiness[source_key] = {
                "batch_id": batch["id"],
                "reference_date": str(batch["reference_date"]),
                "file_sha256": batch["file_sha256"],
                "source_status": batch["status"],
                "total_rows": int(batch["total_rows"] or 0),
                "valid_rows": int(batch["valid_rows"] or 0),
                "review_rows": int(batch["review_rows"] or 0),
                "changed_rows": changed_count,
                "approval_id": approval["id"] if approval else None,
                "approval_status": approval["status"] if approval else None,
                "approval_run_id": approval["run_id"] if approval else None,
            }
        return conn, readiness, approved_rows
    except Exception:
        conn.close()
        raise
    finally:
        cur.close()


def _fetch_production(prod_conn):
    cur = prod_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(
            """
            SELECT permit_number, biz_name, biz_status_name, room_count,
                   hygiene_type, applied_building_id, road_address, jibun_address
              FROM lodging_registry
            """
        )
        registry = {
            row["permit_number"]: dict(row)
            for row in cur.fetchall()
            if row.get("permit_number")
        }
        cur.execute(
            """
            SELECT id, road_address, jibun_address, sgg_cd, umd_nm, jibun
              FROM master_buildings
            """
        )
        road_index = defaultdict(set)
        jibun_index = defaultdict(set)
        for row in cur.fetchall():
            road_key = normalize_road_prefix(row.get("road_address"))
            jibun_key = get_building_jibun_key(row)
            if road_key:
                road_index[road_key].add(row["id"])
            if jibun_key:
                jibun_index[jibun_key].add(row["id"])
        return registry, road_index, jibun_index
    finally:
        cur.close()


def validate():
    dev_conn, readiness, approved_rows = _fetch_approved_rows()
    production_url = os.environ.get("PROD_DATABASE_URL")
    if not production_url:
        dev_conn.close()
        raise RuntimeError("PROD_DATABASE_URL이 없어 운영 dry-run을 실행할 수 없습니다.")
    prod_conn = psycopg2.connect(production_url, connect_timeout=10)
    try:
        prod_conn.set_session(readonly=True, isolation_level="REPEATABLE READ")
        if _database_fingerprint(dev_conn) == _database_fingerprint(prod_conn):
            raise RuntimeError("개발 DB와 운영 DB가 같아 dry-run을 중단했습니다.")
        registry, road_index, jibun_index = _fetch_production(prod_conn)
        permit_numbers = [row.get("permit_number") for row in approved_rows]
        if len(permit_numbers) != len(set(permit_numbers)):
            raise RuntimeError("승인 payload에 중복 permit_number가 있습니다.")

        actions = Counter()
        status_counts = Counter()
        new_match_counts = Counter()
        existing_links_preserved = 0
        blank_room_preserved = 0
        for payload in approved_rows:
            permit_number = payload.get("permit_number")
            if not permit_number:
                raise RuntimeError("승인 payload에 permit_number가 없습니다.")
            existing = registry.get(permit_number)
            action = classify_registry_action(payload, existing)
            actions[action] += 1
            status_counts[payload.get("status_bucket") or "unknown"] += 1
            room_count = parse_optional_room_count(payload.get("raw_record"))
            if existing:
                if existing.get("applied_building_id"):
                    existing_links_preserved += 1
                if room_count is None and existing.get("room_count") is not None:
                    blank_room_preserved += 1
                continue
            road_key = normalize_road_prefix(payload.get("road_address"))
            jibun_key = normalize_jibun_prefix(payload.get("jibun_address"))
            state, _candidate_ids, _building_id = classify_production_match(
                road_key, jibun_key, road_index, jibun_index
            )
            new_match_counts[state] += 1

        return {
            "read_only": True,
            "production_writes": 0,
            "source_readiness": readiness,
            "approval_rows": len(approved_rows),
            "production_registry_rows": len(registry),
            "action_counts_against_production": dict(actions),
            "status_counts": dict(status_counts),
            "new_match_counts": dict(new_match_counts),
            "existing_links_preserved": existing_links_preserved,
            "blank_room_values_preserved": blank_room_preserved,
            "would_auto_create_master_buildings": 0,
        }
    finally:
        prod_conn.close()
        dev_conn.close()


def _json_default(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(type(value).__name__)


def main():
    parser = argparse.ArgumentParser(
        description="정부 숙박 8종 승인 배치의 운영 반영 전용 read-only dry-run"
    )
    parser.add_argument("--output", help="결과 JSON 저장 경로")
    args = parser.parse_args()
    result = validate()
    text = json.dumps(
        result,
        ensure_ascii=False,
        indent=2,
        default=_json_default,
    )
    print(text)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")


if __name__ == "__main__":
    main()