#!/usr/bin/env python3
"""
문화체육관광부 일반야영장업 XLSX/CSV를 lodging_registry에 적재한다.

외국인관광도시민박업 importer와 같은 공식 인허가 파일 형식을 사용하지만,
법정분류는 '캠핑'으로 저장하고 객실 수는 캠핑 사이트 수로 오인하지 않는다.

사용법:
    python import_camping_lodging.py --dry-run 문화_일반야영장업1.xlsx
    python import_camping_lodging.py 문화_일반야영장업1.xlsx

관리번호는 지방자치단체별로 중복될 수 있으므로 다음 복합 식별자를 사용한다.
    CAMPING:{개방자치단체코드}:{관리번호}
"""

import argparse

import import_airbnb_lodging as common
from db import get_conn
from lodging_classification import ACTIVE_STATUS, classify_building_use
from stats_cache import mark_master_stats_invalidated


HYGIENE_TYPE_FIXED = "일반야영장업"
LODGING_TYPE_FIXED = "캠핑"
SOURCE_KEY_PREFIX = "CAMPING"
MASTER_SOURCE = "camping_import"
DRY_RUN_SAMPLE_LIMIT = 20


def _permit_number(authority_code, source_permit_number):
    authority = common._identity_text(authority_code)
    permit = common._identity_text(source_permit_number)
    if not authority or not permit:
        return None
    return f"{SOURCE_KEY_PREFIX}:{authority}:{permit}"


def parse_row(row):
    """캠핑 원본 행을 공통 lodging_registry 적재 형태로 변환한다."""
    # 공통 importer가 헤더·주소·날짜·전화번호를 처리하므로 그 결과를 재사용한다.
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

    # 일반야영장업의 '객실수'는 비어 있거나 객실 의미가 아니므로 객실 통계에 넣지 않는다.
    data["room_count"] = None
    return data if data["permit_number"] else None


def _create_master(cur, data, location):
    """주소가 유일하게 해석되지 않은 활성 캠핑장을 기존 패턴으로 등록한다."""
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
            0,
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
        f"[캠핑 로드] 전체 {len(rows):,}행 / 식별 가능 {len(parsed):,}행 / "
        f"영업·정상 {len(active):,}행 / 비영업 {inactive_count:,}행 / "
        f"제외 {skipped:,}행"
    )

    if dry_run:
        for data in active[:DRY_RUN_SAMPLE_LIMIT]:
            print(
                f"  [DRY] {data['permit_number']} | {data['biz_name']} | "
                f"{data['road_address'] or data['jibun_address'] or '-'} | 캠핑"
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
                registry_counter = (
                    "inserted" if registry["is_new"] else "updated"
                )
                outcome_counter = None
                new_building_id = None

                if data["biz_status_name"] != ACTIVE_STATUS:
                    building_id = None
                    outcome_counter = "inactive"
                elif not data.get("road_norm") and not data.get("jibun_norm"):
                    building_id = None
                    outcome_counter = "unmatched"
                else:
                    building_id, match_reason = common._match_master(
                        data, road_index, jibun_index
                    )
                    if building_id:
                        outcome_counter = "matched"
                    elif match_reason:
                        building_id = None
                        outcome_counter = "unmatched"
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
                        if not location:
                            building_id = None
                            outcome_counter = "unmatched"
                        else:
                            building_id = _create_master(cur, data, location)
                            new_building_id = building_id
                            outcome_counter = "created"

                if building_id:
                    cur.execute(
                        "UPDATE lodging_registry "
                        "SET applied_building_id = %s WHERE id = %s",
                        (building_id, registry["id"]),
                    )
                conn.commit()
                counters[registry_counter] += 1
                counters[outcome_counter] += 1
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
        mark_master_stats_invalidated("camping_import")
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
    parser.add_argument("filepath", help="CSV 또는 XLSX 파일 경로")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="DB 연결·스키마 변경 없이 파싱 결과만 확인",
    )
    args = parser.parse_args()
    run(args.filepath, dry_run=args.dry_run)