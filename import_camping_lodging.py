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


LODGING_TYPE_FIXED = "캠핑"
HYGIENE_TYPE_FIXED = "일반야영장업"
SOURCE_KEY_PREFIX = "CAMPING"
MASTER_SOURCE = "camping_import"
DRY_RUN_SAMPLE_LIMIT = 20
AUTOMOTIVE_HYGIENE_TYPE = "자동차야영장업"
AUTOMOTIVE_SUBTYPE = "자동차야영"

_SITE_COUNT_HEADERS = (
    "야영사이트수",
    "야영사이트 수",
    "사이트수",
    "사이트 수",
    "캠핑사이트수",
    "캠핑사이트 수",
)


def _camping_site_count(row):
    """표준 파일에 있는 사이트 수를 객실 수와 별도로 읽는다."""
    for header in _SITE_COUNT_HEADERS:
        if header in row:
            return common._integer(row.get(header))
    return None


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
    source_type = common._text(row.get("문화체육업종명")) or HYGIENE_TYPE_FIXED
    data["hygiene_type"] = source_type
    data["lodging_type"] = LODGING_TYPE_FIXED
    data["lodging_subtype"] = (
        AUTOMOTIVE_SUBTYPE if source_type == AUTOMOTIVE_HYGIENE_TYPE else None
    )
    data["master_source"] = MASTER_SOURCE

    # 일반야영장업의 '객실수'는 비어 있거나 객실 의미가 아니므로 객실 통계에 넣지 않는다.
    data["room_count"] = None
    data["camping_site_count"] = _camping_site_count(row)
    # 정부 CSV는 유형별 사이트 칼럼을 주지 않는다. 업태로 알 수 있는 단일
    # 유형만 보수적으로 채우며, 사이트 수 자체가 없으면 유형도 확정하지 않는다.
    site_count = data["camping_site_count"]
    data.update({
        "camping_general_site_count": (
            site_count if source_type != AUTOMOTIVE_HYGIENE_TYPE else None
        ),
        "camping_auto_site_count": (
            site_count if source_type == AUTOMOTIVE_HYGIENE_TYPE else None
        ),
        "camping_glamping_site_count": None,
        "camping_caravan_site_count": None,
        "camping_classification": (
            "auto_only" if source_type == AUTOMOTIVE_HYGIENE_TYPE
            else "general_only"
        ) if site_count is not None else "unknown",
    })
    return data if data["permit_number"] else None


def _first_value(item, *keys):
    for key in keys:
        value = item.get(key)
        if value is not None and str(value).strip():
            return value
    return None


def _camping_site_count_from_api(item):
    """고캠핑 API의 유형별 사이트 수 합계(하위 호환용)."""
    return _camping_site_breakdown_from_api(item)["camping_site_count"]


def _nonnegative_site_count(value):
    """누락·잘못된·음수 사이트 수는 0으로 안전하게 정규화한다."""
    parsed = common._integer(value)
    return parsed if parsed is not None and parsed >= 0 else 0


def _camping_classification(general, auto, glamping, caravan):
    """양수로 확인된 유형만으로 보수적인 내부 캠핑 분류를 정한다."""
    positive = [
        name for name, count in (
            ("general_only", general),
            ("auto_only", auto),
            ("glamping_only", glamping),
            ("caravan_only", caravan),
        ) if count > 0
    ]
    if len(positive) >= 2:
        return "confirmed_mixed"
    return positive[0] if positive else "unknown"


def _camping_site_breakdown_from_api(item):
    """GoCamping의 다섯 원본 필드를 네 내부 유형과 합계로 정규화한다.

    API가 필드를 아예 누락해도 0으로 보관하고 ``unknown``으로 판정한다.
    따라서 공개 표시는 복합으로 매핑할 수 있지만, 확인된 혼합 유형과는
    내부적으로 구분된다.
    """
    general = _nonnegative_site_count(item.get("gnrlSiteCo"))
    auto = _nonnegative_site_count(item.get("autoSiteCo"))
    glamping = _nonnegative_site_count(item.get("glampSiteCo"))
    caravan = (
        _nonnegative_site_count(item.get("caravSiteCo"))
        + _nonnegative_site_count(item.get("indvdlCaravSiteCo"))
    )
    return {
        "camping_general_site_count": general,
        "camping_auto_site_count": auto,
        "camping_glamping_site_count": glamping,
        "camping_caravan_site_count": caravan,
        "camping_site_count": general + auto + glamping + caravan,
        "camping_classification": _camping_classification(
            general, auto, glamping, caravan
        ),
    }


def _camping_status(value):
    """고캠핑 운영상태를 서비스의 영업상태 표기로 정규화한다."""
    status = common._text(value)
    if not status:
        return None
    if status in {"운영", "운영중", "영업", "영업중", "정상", "Y", "1"}:
        return "영업/정상"
    if status in {"휴장", "휴업", "일시휴업"}:
        return "휴업"
    if status in {"폐업", "폐장", "운영종료", "N", "0"}:
        return "폐업"
    return status


def _nonnegative_count(value):
    parsed = common._integer(value)
    return parsed if parsed is not None and parsed >= 0 else None


def parse_api_item(item):
    """고캠핑 basedList 응답 한 건을 lodging_registry 형태로 변환한다."""
    if not isinstance(item, dict):
        return None
    original_key = common._identity_text(
        _first_value(item, "contentId", "contentid", "contentID")
    )
    biz_name = common._text(_first_value(item, "facltNm", "facltNM"))
    if not original_key or not biz_name:
        return None

    address = common._text(_first_value(item, "addr1", "address"))
    status_source = _first_value(
        item, "manageSttus", "manageStNm", "manageSt", "manageStCd"
    )
    status = _camping_status(status_source)
    status_detail = common._text(
        _first_value(
            item, "hvofReason", "manageSttus", "manageStNm", "manageSt"
        )
    )
    site_breakdown = _camping_site_breakdown_from_api(item)
    return {
        "permit_number": f"{SOURCE_KEY_PREFIX}:{original_key}",
        "permit_date": common._text(
            _first_value(
                item, "prmisnDe", "operDe", "operDeYmd", "createdtime"
            )
        ),
        "biz_name": biz_name,
        "room_count": None,
        **site_breakdown,
        "bld_use_nm": None,
        "source_updated_at": common._text(
            _first_value(item, "modifiedtime", "modifiedTime", "lastUpdate")
        ),
        "road_address": address,
        "hygiene_type": HYGIENE_TYPE_FIXED,
        "lodging_subtype": None,
        "biz_status_name": status,
        "biz_status_detail": status_detail,
        "facility_area": common._decimal(_first_value(item, "allar", "allAr")),
        "camping_location_types": common._text(item.get("lctCl")),
        "camping_theme_types": common._text(item.get("themaEnvrnCl")),
        "camping_amenities": common._text(item.get("sbrsCl")),
        "camping_toilet_count": _nonnegative_count(item.get("toiletCo")),
        "camping_shower_count": _nonnegative_count(item.get("swrmCo")),
        "camping_sink_count": _nonnegative_count(item.get("wtrplCo")),
        "camping_operating_seasons": common._text(item.get("operPdCl")),
        "camping_animal_policy": common._text(item.get("animalCmgCl")),
        "camping_reservation_url": common._text(
            _first_value(item, "resveUrl", "homepage")
        ),
        "camping_first_image_url": common._text(
            _first_value(item, "firstImageUrl", "firstImageUrl2")
        ),
        "phone": common._phone(_first_value(item, "tel", "TELNO")),
        # 고캠핑은 addr1 한 필드만 제공하므로 도로명 주소를 지번 칼럼에 복제하지 않는다.
        "jibun_address": None,
        "region_name": common._text(
            _first_value(item, "doNm", "sigunguNm", "lctCl")
        ),
        "road_norm": common.normalize_road_prefix(address),
        "jibun_norm": common.normalize_jibun_prefix(address),
        "biz_name_norm": common.normalize_name(biz_name),
    }


def _create_master(cur, data, location):
    """주소가 유일하게 해석되지 않은 활성 캠핑장을 기존 패턴으로 등록한다."""
    address = data.get("road_address") or data.get("jibun_address")
    cur.execute(
        """
        INSERT INTO master_buildings (
            building_name, sgg_cd, sgg_text, umd_nm, jibun,
            road_address, jibun_address, lodging_type, lodging_type_detail, lodging_subtype,
            units, source, name_pending, building_use_type, building_use_detail,
            lodging_classification_source, lodging_classification_confidence
        ) VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
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
            data["hygiene_type"],
            data.get("lodging_subtype"),
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
                    if data.get("lodging_subtype"):
                        cur.execute(
                            """
                            UPDATE master_buildings
                            SET lodging_type = %s,
                                lodging_type_detail = %s,
                                lodging_subtype = %s,
                                lodging_classification_source = 'active_permit',
                                lodging_classification_confidence = 'high'
                            WHERE id = %s
                            """,
                            (
                                LODGING_TYPE_FIXED,
                                data["hygiene_type"],
                                data["lodging_subtype"],
                                building_id,
                            ),
                        )
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