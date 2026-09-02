"""정부 숙박 staging과 건물 마스터의 주소 매칭을 읽기 전용으로 검증한다."""

import argparse
import json
from collections import Counter, defaultdict
from datetime import date, datetime

from addr_norm import get_building_jibun_key, normalize_jibun_prefix, normalize_road_prefix
from db import get_conn
from lodging_data_contract import GOVERNMENT_LODGING_SOURCES


SOURCE_KEYS = tuple(GOVERNMENT_LODGING_SOURCES)


def classify_match(road_key, jibun_key, road_index, jibun_index):
    road_ids = tuple(sorted(road_index.get(road_key, ()))) if road_key else ()
    jibun_ids = tuple(sorted(jibun_index.get(jibun_key, ()))) if jibun_key else ()
    if not road_key and not jibun_key:
        return "no_address", (), None
    if len(road_ids) == 1:
        if len(jibun_ids) == 1 and road_ids[0] != jibun_ids[0]:
            return "address_conflict", tuple(sorted(set(road_ids + jibun_ids))), None
        return "road_unique", road_ids, road_ids[0]
    if len(road_ids) > 1:
        return "road_ambiguous", road_ids, None
    if len(jibun_ids) == 1:
        return "jibun_unique", jibun_ids, jibun_ids[0]
    if len(jibun_ids) > 1:
        return "jibun_ambiguous", jibun_ids, None
    return "unmatched", (), None


def _json_default(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(type(value).__name__)


def analyze(batch_ids=None, sample_limit=20):
    conn = get_conn()
    cur = conn.cursor()
    try:
        if batch_ids:
            cur.execute(
                """
                SELECT id, source_key, reference_date, total_rows
                  FROM lodging_source_batches
                 WHERE id = ANY(%s)
                 ORDER BY source_key, id
                """,
                (list(batch_ids),),
            )
        else:
            cur.execute(
                """
                SELECT DISTINCT ON (source_key)
                       id, source_key, reference_date, total_rows
                  FROM lodging_source_batches
                 WHERE source_key = ANY(%s)
                 ORDER BY source_key, reference_date DESC, created_at DESC, id DESC
                """,
                (list(SOURCE_KEYS),),
            )
        batches = [dict(row) for row in cur.fetchall()]
        if not batches:
            raise RuntimeError("분석할 staging 배치가 없습니다.")

        cur.execute(
            """
            SELECT id, road_address, jibun_address, umd_nm, jibun
              FROM master_buildings
            """
        )
        road_index = defaultdict(set)
        jibun_index = defaultdict(set)
        for row in cur.fetchall():
            building = dict(row)
            road_key = normalize_road_prefix(building.get("road_address"))
            jibun_key = get_building_jibun_key(building)
            if road_key:
                road_index[road_key].add(building["id"])
            if jibun_key:
                jibun_index[jibun_key].add(building["id"])

        cur.execute(
            """
            SELECT sr.id, sr.batch_id, sb.source_key, sr.row_number,
                   sr.permit_number, sr.biz_name, sr.service_category,
                   sr.status_bucket, sr.road_address, sr.jibun_address,
                   sr.row_state, sr.diff_kind
              FROM lodging_source_rows sr
              JOIN lodging_source_batches sb ON sb.id=sr.batch_id
             WHERE sr.batch_id = ANY(%s)
             ORDER BY sr.batch_id, sr.row_number
            """,
            ([batch["id"] for batch in batches],),
        )

        overall = Counter()
        by_source = defaultdict(Counter)
        by_service = defaultdict(Counter)
        by_status = defaultdict(Counter)
        matched_building_rows = Counter()
        samples = defaultdict(list)
        for raw in cur.fetchall():
            row = dict(raw)
            road_key = normalize_road_prefix(row.get("road_address"))
            jibun_key = normalize_jibun_prefix(row.get("jibun_address"))
            state, candidate_ids, building_id = classify_match(
                road_key, jibun_key, road_index, jibun_index
            )
            overall[state] += 1
            by_source[row["source_key"]][state] += 1
            by_service[row.get("service_category") or "미분류"][state] += 1
            by_status[row.get("status_bucket") or "미분류"][state] += 1
            if building_id:
                matched_building_rows[building_id] += 1
                if row.get("status_bucket") == "active":
                    overall["active_rows_matched"] += 1
            if len(samples[state]) < sample_limit:
                samples[state].append({
                    "source": row["source_key"],
                    "row_number": row["row_number"],
                    "permit_number": row["permit_number"],
                    "biz_name": row["biz_name"],
                    "road_address": row["road_address"],
                    "jibun_address": row["jibun_address"],
                    "candidate_ids": list(candidate_ids)[:10],
                })

        matched_rows = overall["road_unique"] + overall["jibun_unique"]
        report = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "read_only": True,
            "batches": batches,
            "master_buildings": {
                "count": len({value for values in road_index.values() for value in values}
                             | {value for values in jibun_index.values() for value in values}),
                "road_keys": len(road_index),
                "ambiguous_road_keys": sum(len(v) > 1 for v in road_index.values()),
                "jibun_keys": len(jibun_index),
                "ambiguous_jibun_keys": sum(len(v) > 1 for v in jibun_index.values()),
            },
            "overall": dict(overall),
            "matched_rows": matched_rows,
            "matched_unique_buildings": len(matched_building_rows),
            "buildings_with_multiple_source_rows": sum(
                count > 1 for count in matched_building_rows.values()
            ),
            "max_source_rows_on_one_building": max(
                matched_building_rows.values(), default=0
            ),
            "by_source": {key: dict(value) for key, value in sorted(by_source.items())},
            "by_service": {key: dict(value) for key, value in sorted(by_service.items())},
            "by_status": {key: dict(value) for key, value in sorted(by_status.items())},
            "samples": dict(samples),
        }
        return report
    finally:
        cur.close()
        conn.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-id", type=int, action="append")
    parser.add_argument("--sample-limit", type=int, default=20)
    parser.add_argument("--output")
    args = parser.parse_args()
    report = analyze(args.batch_id, args.sample_limit)
    text = json.dumps(report, ensure_ascii=False, indent=2, default=_json_default)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
    print(text)


if __name__ == "__main__":
    main()