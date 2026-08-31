#!/usr/bin/env python3
"""
문화체육관광부 농어촌민박업 CSV를 lodging_registry에 적재한다.

사용법:
    python import_rural_lodging.py --dry-run 문화_농어촌민박업.csv
    python import_rural_lodging.py 문화_농어촌민박업.csv

관리번호는 지방자치단체별로 중복될 수 있으므로 다음 복합 식별자를 사용한다.
    RURAL:{개방자치단체코드}:{관리번호}
"""

import argparse
import csv
import io
from pathlib import Path

import import_airbnb_lodging as common
from db import get_conn
from lodging_classification import ACTIVE_STATUS, classify_building_use
from stats_cache import mark_master_stats_invalidated


HYGIENE_TYPE_FIXED = "농어촌민박업"
LODGING_TYPE_FIXED = "농어촌민박"
SOURCE_KEY_PREFIX = "RURAL"
MASTER_SOURCE = "rural_import"
DRY_RUN_SAMPLE_LIMIT = 20

REQUIRED_HEADERS = frozenset({
    "개방자치단체코드",
    "관리번호",
    "인허가일자",
    "영업상태명",
    "사업장명",
    "객실수",
    "데이터갱신시점",
    "도로명주소",
    "상세영업상태명",
    "전화번호",
    "지번주소",
})


def read_rows(filepath):
    """UTF-8 또는 CP949 인코딩의 농어촌민박 CSV를 읽는다."""
    path = Path(filepath)
    if path.suffix.lower() != ".csv":
        raise ValueError("지원 형식은 .csv입니다.")
    raw = path.read_bytes()
    decoded = None
    for encoding in ("utf-8-sig", "cp949"):
        try:
            decoded = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if decoded is None:
        raise ValueError("CSV 인코딩을 확인할 수 없습니다.")
    reader = csv.DictReader(io.StringIO(decoded))
    headers = {
        common._text(value) or ""
        for value in (reader.fieldnames or ())
    }
    missing = REQUIRED_HEADERS - headers
    if missing:
        raise ValueError("필수 컬럼이 없습니다: " + ", ".join(sorted(missing)))
    return [dict(row) for row in reader]


def _permit_number(authority_code, source_permit_number):
    authority = common._identity_text(authority_code)
    permit = common._identity_text(source_permit_number)
    if not authority or not permit:
        return None
    return f"{SOURCE_KEY_PREFIX}:{authority}:{permit}"


def parse_row(row):
    """농어촌민박 CSV 행을 lodging_registry 공통 형태로 변환한다."""
    permit_number = _permit_number(
        row.get("개방자치단체코드"),
        row.get("관리번호"),
    )
    biz_name = common._text(row.get("사업장명"))
    if not permit_number or not biz_name:
        return None
    road_address = common._text(row.get("도로명주소"))
    jibun_address = common._text(row.get("지번주소"))
    return {
        "permit_number": permit_number,
        "permit_date": common._date_text(row.get("인허가일자")),
        "biz_name": biz_name,
        "room_count": common._integer(row.get("객실수")),
        "camping_site_count": None,
        # 원본의 건물형태구분명은 현재 비어 있어 건축물 용도는 미지정으로 둔다.
        "bld_use_nm": common._text(row.get("건물형태구분명")),
        "source_updated_at": common._date_text(row.get("데이터갱신시점")),
        "road_address": road_address,
        "hygiene_type": HYGIENE_TYPE_FIXED,
        "biz_status_name": common._text(row.get("영업상태명")),
        "biz_status_detail": common._text(row.get("상세영업상태명")),
        "facility_area": common._decimal(
            common._text(row.get("주택면적"))
            or common._text(row.get("소재지면적"))
        ),
        "phone": common._phone(row.get("전화번호")),
        "jibun_address": jibun_address,
        "region_name": None,
        "road_norm": common.normalize_road_prefix(road_address),
        "jibun_norm": common.normalize_jibun_prefix(jibun_address),
        "biz_name_norm": common.normalize_name(biz_name),
        "lodging_type": LODGING_TYPE_FIXED,
        "master_source": MASTER_SOURCE,
    }


def _create_master(cur, data, location):
    """주소가 일치하는 건물이 없을 때 농어촌민박 건물을 생성한다."""
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
    rows = read_rows(filepath)
    parsed = [data for data in (parse_row(row) for row in rows) if data]
    skipped = len(rows) - len(parsed)
    active = [
        data for data in parsed
        if data["biz_status_name"] == ACTIVE_STATUS
    ]
    inactive_count = len(parsed) - len(active)
    print(
        f"[농어촌 CSV] 전체 {len(rows):,}행 / 식별 가능 {len(parsed):,}행 / "
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
        mark_master_stats_invalidated("rural_import")
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
    parser.add_argument("filepath", help="농어촌민박업 CSV 파일 경로")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="DB 변경 없이 파싱 결과만 확인",
    )
    args = parser.parse_args()
    run(args.filepath, dry_run=args.dry_run)