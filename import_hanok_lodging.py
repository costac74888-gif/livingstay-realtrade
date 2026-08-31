#!/usr/bin/env python3
"""
문화체육관광부 한옥체험업 CSV를 lodging_registry에 적재한다.

에어비앤비·캠핑 CSV importer와 같은 표준 인허가 파일을 사용하지만,
한옥체험업은 HANOK 원본 식별자와 '한옥' 법정분류를 사용한다.

사용법:
    python import_hanok_lodging.py --dry-run 문화_한옥체험업.csv
    python import_hanok_lodging.py 문화_한옥체험업.csv
"""

import argparse

import import_airbnb_lodging as common
from db import get_conn
from lodging_classification import ACTIVE_STATUS, classify_building_use
from stats_cache import mark_master_stats_invalidated


HYGIENE_TYPE_FIXED = "한옥체험업"
LODGING_TYPE_FIXED = "한옥"
SOURCE_KEY_PREFIX = "HANOK"
MASTER_SOURCE = "hanok_import"
DRY_RUN_SAMPLE_LIMIT = 20


def _permit_number(authority_code, source_permit_number):
    authority = common._identity_text(authority_code)
    permit = common._identity_text(source_permit_number)
    if not authority or not permit:
        return None
    return f"{SOURCE_KEY_PREFIX}:{authority}:{permit}"


def parse_row(row):
    """표준 인허가 CSV 행을 한옥체험업 lodging_registry 형태로 변환한다."""
    data = common.parse_row(row)
    if data is None:
        return None
    data["permit_number"] = _permit_number(
        row.get("개방자치단체코드"),
        row.get("관리번호"),
    )
    data["hygiene_type"] = HYGIENE_TYPE_FIXED
    data["lodging_type"] = LODGING_TYPE_FIXED
    data["master_source"] = MASTER_SOURCE
    return data if data["permit_number"] else None


def _create_master(cur, data, location):
    """주소가 일치하는 건물이 없을 때 한옥체험업 건물을 생성한다."""
    address = data.get("road_address") or data.get("jibun_address")
    cur.execute(
        """
        INSERT INTO master_buildings (
            building_name, sgg_cd, sgg_text, umd_nm, jibun,
            road_address, jibun_address, lodging_type, lodging_type_detail,
            units, source, name_pending, building_use_type, building_use_detail,
            lodging_classification_source, lodging_classification_confidence
        ) VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, TRUE, %s, %s, 'active_permit', 'high'
        )
        RETURNING id
        """,
        (
            data["biz_name"],
            location["sgg_cd"],
            location["sgg_text"],
            location["umd_nm"],
            location["jibun"],
            address,
            data.get("jibun_address"),
            LODGING_TYPE_FIXED,
            HYGIENE_TYPE_FIXED,
            data.get("room_count") or 0,
            MASTER_SOURCE,
            classify_building_use(data.get("bld_use_nm")),
            data.get("bld_use_nm"),
        ),
    )
    return cur.fetchone()["id"]


def run(filepath, dry_run=False):
    rows = common.read_rows(filepath)
    parsed = [data for data in (parse_row(row) for row in rows) if data]
    skipped = len(rows) - len(parsed)
    active = [
        data for data in parsed
        if data["biz_status_name"] == ACTIVE_STATUS
    ]
    inactive_count = len(parsed) - len(active)
    print(
        f"[한옥 CSV] 전체 {len(rows):,}행 / 식별 가능 {len(parsed):,}행 / "
        f"영업·정상 {len(active):,}행 / 비영업 {inactive_count:,}행 / "
        f"제외 {skipped:,}행"
    )

    if dry_run:
        for data in active[:DRY_RUN_SAMPLE_LIMIT]:
            print(
                f"  [DRY] {data['permit_number']} | {data['biz_name']} | "
                f"{data['road_address'] or data['jibun_address'] or '-'} | "
                f"{data['biz_status_name'] or '-'}"
            )
        if len(active) > DRY_RUN_SAMPLE_LIMIT:
            print(f"  ... 나머지 {len(active) - DRY_RUN_SAMPLE_LIMIT:,}행 생략")
        return {
            "total": len(rows),
            "valid": len(parsed),
            "active": len(active),
            "inactive": inactive_count,
            "skipped": skipped,
        }

    bjdong = common.BjdongMap(common.BJDONG_CODE_CSV)
    conn = get_conn()
    cur = conn.cursor()
    counters = {
        "inserted": 0,
        "updated": 0,
        "matched": 0,
        "created": 0,
        "inactive": 0,
        "unmatched": 0,
        "failed": 0,
    }
    try:
        common._assert_schema(cur)
        road_index, jibun_index = common._load_master_indexes(cur)
        for data in parsed:
            try:
                registry = common._upsert_registry(cur, data)
                counters["inserted" if registry["is_new"] else "updated"] += 1
                building_id = None
                new_building_id = None

                if data["biz_status_name"] != ACTIVE_STATUS:
                    counters["inactive"] += 1
                elif not data.get("road_norm") and not data.get("jibun_norm"):
                    counters["unmatched"] += 1
                else:
                    building_id, match_reason = common._match_master(
                        data, road_index, jibun_index
                    )
                    if building_id:
                        counters["matched"] += 1
                    elif match_reason:
                        counters["unmatched"] += 1
                        print(
                            f"  [검토] {data['biz_name']} — {match_reason}: "
                            f"{data['road_address'] or data['jibun_address'] or '-'}"
                        )
                    else:
                        location = common._location_from_addresses(
                            bjdong,
                            data.get("road_address"),
                            data.get("jibun_address"),
                        )
                        if location:
                            building_id = _create_master(cur, data, location)
                            new_building_id = building_id
                            counters["created"] += 1
                        else:
                            counters["unmatched"] += 1

                if building_id:
                    cur.execute(
                        "UPDATE lodging_registry "
                        "SET applied_building_id=%s WHERE id=%s",
                        (building_id, registry["id"]),
                    )
                conn.commit()
                if new_building_id:
                    common._register_new_master_in_indexes(
                        new_building_id, data, road_index, jibun_index
                    )
            except Exception as exc:
                conn.rollback()
                counters["failed"] += 1
                print(f"  [실패] {data['biz_name']}: {exc}")
    finally:
        cur.close()
        conn.close()

    if counters["inserted"] or counters["updated"]:
        mark_master_stats_invalidated("hanok_import")
    print(
        "\n완료 — "
        f"신규 적재 {counters['inserted']:,} / 갱신 {counters['updated']:,} / "
        f"기존 건물 연결 {counters['matched']:,} / 신규 건물 {counters['created']:,} / "
        f"비영업 상태 {counters['inactive']:,} / 미연결 {counters['unmatched']:,} / "
        f"실패 {counters['failed']:,}"
    )
    return counters


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("filepath", help="한옥체험업 CSV 파일 경로")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="DB 변경 없이 파싱 결과만 확인",
    )
    args = parser.parse_args()
    run(args.filepath, dry_run=args.dry_run)