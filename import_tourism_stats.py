#!/usr/bin/env python3
"""한국관광 데이터랩 ZIP/CSV를 열지도 전용 테이블에 멱등 적재한다."""

import argparse
import csv
import hashlib
import io
import json
import math
import os
import re
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values

import addr_norm
from address_utils import BjdongMap, normalize_umd_nm, parse_jibun, road_to_jibun
from building_registry import (
    _fetch_title_rows,
    _find_categories,
    _hocnt,
    _title_row_to_dict,
    extract_tourist_subtype,
    resolve_api_building_name,
)


TYPE_RULES = (
    # This must precede the generic attraction-ranking rule below: the two
    # exports have similarly named filenames but describe different entities.
    ("숙박시설_검색순위_TOP100_상세주소", "lodging_search_rank"),
    ("숙박시설 검색순위 TOP100 상세주소", "lodging_search_rank"),
    ("관광숙박_검색순위", "lodging_search_rank"),
    ("관광숙박 검색순위", "lodging_search_rank"),
    ("방문자 급등동네(내국인)", "surge_domestic_dong"),
    ("방문자 급등동네(외국인)", "surge_foreign_dong"),
    ("외국인 지역별 방문자 수(기초지자체별)", "foreign_sgg"),
    ("지역별 방문자 수(기초지자체별)", "visitor_sgg"),
    ("외국인 지역별 방문자 수(광역별)", "foreign_sido"),
    ("지역별 방문자 수(광역별)", "visitor_sido"),
    ("외국인 방문자 거주지", "foreign_country"),
    ("외국인 방문자 수 추이", "foreign_trend"),
    ("방문자 수 추이", "visitor_trend"),
    ("지역별 지출액", "consumption_region"),
    ("관광소비 추이", "consumption_trend"),
    ("업종별 지출액", "consumption_sector"),
    ("지역별 검색건수", "search_sgg"),
    ("검색건수 추이", "search_trend"),
    ("지역별 관광지 검색순위", "search_ranking"),
    ("캠핑장 업종별 분포", "camping_sector"),
    ("캠핑사이트 유형별 현황", "camping_site_type"),
    ("업종별 분포", "lodging_sector"),
)

def latest_source_order_sql(alias="t"):
    """Authoritative, fixed SQL ordering for selecting one source per type."""
    if alias not in {"t", "tourism_stats"}:
        raise ValueError("unsafe SQL alias")
    p = f"{alias}."
    return (
        f"CASE WHEN {p}stat_type='search_ranking' THEN {p}collected_at END DESC NULLS LAST, "
        f"CASE WHEN {p}stat_type<>'search_ranking' THEN split_part({p}source_period,'-',2) END DESC NULLS LAST, "
        f"CASE WHEN {p}stat_type<>'search_ranking' THEN split_part({p}source_period,'-',1) END DESC NULLS LAST, "
        f"{p}collected_at DESC, {p}source_file DESC, {p}source_period DESC NULLS LAST"
    )

LODGING_RANK_FIELDS = {
    "datalab_id": (
        "데이터랩ID", "관광숙박ID", "관광숙박업ID", "관광숙박업명 ID",
        "관광지ID", "관광지명 ID", "ID",
    ),
    "place_name": ("관광숙박명", "관광숙박업명", "관광지명", "명"),
    "sub_category": (
        "소분류 카테고리", "소분류", "관광숙박 소분류", "관광숙박업 소분류",
    ),
    "mid_category": (
        "중분류 카테고리", "중분류", "관광숙박 중분류", "관광숙박업 중분류",
    ),
    "search_count": ("검색건수",),
    "rank": ("검색순위", "순위"),
    "road_address": ("도로명주소", "상세주소"),
}

FIELD_MAP = {
    "visitor_sgg": (
        ("광역지자체명", "기초지자체명"),
        (("기초지자체 방문자 수", "명"), ("기초지자체 방문자 비율", "%")),
    ),
    "foreign_sgg": (
        ("광역지자체명", "기초지자체명"),
        (("기초지자체 방문자 수", "명"), ("기초지자체 방문자 비율", "%")),
    ),
    "visitor_sido": (
        ("광역지자체명", None),
        (("광역지자체 방문자 수", "명"), ("광역지자체 방문자 비율", "%")),
    ),
    "foreign_sido": (
        ("광역지자체명", None),
        (("광역지자체 방문자 수", "명"), ("광역지자체 방문자 비율", "%")),
    ),
    "consumption_region": (
        ("광역지자체 명", "기초지자체 명"),
        (("기초지자체 지출액 비율(%)", "%"), ("광역지자체 지출액 비율(%)", "%")),
    ),
    "search_sgg": (
        ("광역지자체", "기초지자체"),
        (("기초지자체 검색건수", "건"), ("기초지자체 검색건수 비율", "%")),
    ),
}


def clean_archive_name(name):
    try:
        return name.encode("cp437").decode("cp949")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return name


def normalize_region(sido, sgg):
    sido = (sido or "").strip()
    sgg = (sgg or "").strip()
    if sido == "전남광주통합특별시":
        sido = "광주광역시" if sgg in {"동구", "서구", "남구", "북구", "광산구"} else "전라남도"
    return sido or None, sgg or None


def number(value):
    text = str(value or "").replace(",", "").strip()
    if not text:
        return None
    try:
        parsed = float(text)
        return parsed if math.isfinite(parsed) else None
    except ValueError:
        return None


def normalize_place_name(value):
    """Use the same deliberately small comparison key in Python and SQL."""
    text = str(value or "").strip().lower()
    text = re.sub(r"[(\[].*?[)\]]", "", text)
    text = re.sub(r"[^0-9가-힣a-z]", "", text)
    return text or None


def region_core_sql(sido_expression, sgg_expression):
    """Return the SQL equivalent of the app's canonical province key."""
    sido = f"regexp_replace(lower(trim(coalesce({sido_expression}, ''))), '\\s+', '', 'g')"
    sgg = f"regexp_replace(lower(trim(coalesce({sgg_expression}, ''))), '\\s+', '', 'g')"
    stripped = (
        f"regexp_replace({sido}, "
        "'(특별자치도|특별자치시|특별시|광역시|도|시)$', '')"
    )
    abbreviated = (
        f"regexp_replace(regexp_replace(regexp_replace({stripped}, "
        "'^전라', '전'), '^충청', '충'), '^경상', '경')"
    )
    return (
        f"CASE WHEN {sido} = '전남광주통합특별시' THEN "
        f"CASE WHEN {sgg} IN ('동구','서구','남구','북구','광산구') "
        f"THEN '광주' ELSE '전남' END ELSE {abbreviated} END"
    )


def lodging_rank_value(row, field):
    for key in LODGING_RANK_FIELDS[field]:
        value = row.get(key)
        if value not in (None, ""):
            return str(value).strip()
    # Data Lab exports have used both "관광숙박업명 ID" and
    # "관광숙박업명ID"; accept presentation-only header changes without
    # broadening the data contract to unrelated columns.
    normalized = {
        re.sub(r"[\s_-]+", "", str(key)).lower(): value
        for key, value in row.items()
    }
    for key in LODGING_RANK_FIELDS[field]:
        value = normalized.get(re.sub(r"[\s_-]+", "", key).lower())
        if value not in (None, ""):
            return str(value).strip()
    return None


def is_lodging_top100_address_file(filename):
    normalized = re.sub(
        r"[\s_-]+", "", os.path.basename(str(filename or ""))
    ).lower()
    return "숙박시설검색순위top100상세주소" in normalized


def validate_lodging_top100_address_rows(filename, rows):
    """Enforce the dedicated detailed-address export in every import path."""
    if not is_lodging_top100_address_file(filename):
        return
    ranks = [number(lodging_rank_value(row, "rank")) for row in rows]
    missing_required = [
        index
        for index, row in enumerate(rows, start=2)
        if not lodging_rank_value(row, "place_name")
        or not lodging_rank_value(row, "search_count")
        or not lodging_rank_value(row, "road_address")
    ]
    if (
        len(rows) != 100
        or set(ranks) != set(range(1, 101))
        or missing_required
    ):
        details = (
            f" 필수값 누락 행: {missing_required[:5]}"
            if missing_required else ""
        )
        raise ValueError(
            f"{filename}: 상세주소 TOP100은 정확한 1~100위와 "
            f"관광지명·검색건수·도로명주소 100개가 모두 필요합니다.{details}"
        )


def build_lodging_rank_row(row, source_file, period, row_index=None):
    """Build the one canonical metric emitted by a lodging-rank CSV row."""
    place_name = lodging_rank_value(row, "place_name")
    rank = number(lodging_rank_value(row, "rank"))
    if not place_name or rank is None or rank <= 0:
        return None
    sido, sgg = normalize_region(row.get("광역시/도"), row.get("시/군/구"))
    dimensions = {
        key: lodging_rank_value(row, key)
        for key in (
            "datalab_id", "place_name", "sub_category", "mid_category",
            "search_count",
        )
    }
    road_address = lodging_rank_value(row, "road_address")
    if road_address:
        dimensions["road_address"] = road_address
    datalab_id = dimensions["datalab_id"]
    identity_key = (
        [
            "id",
            datalab_id,
            normalize_place_name(sido) or "",
            normalize_place_name(sgg) or "",
            normalize_place_name(place_name) or "",
        ]
        if datalab_id
        else [
            "row",
            row_index,
            normalize_place_name(sido) or "",
            normalize_place_name(sgg) or "",
            normalize_place_name(place_name) or "",
            normalize_place_name(dimensions["mid_category"]) or "",
            normalize_place_name(dimensions["sub_category"]) or "",
        ]
    )
    identity = json.dumps(
        [source_file, "lodging_search_rank", identity_key],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return (
        "lodging_search_rank", sido, sgg, None, "검색순위", rank, "위",
        source_file, period, json.dumps(dimensions, ensure_ascii=False),
        hashlib.sha256(identity.encode()).hexdigest(),
    )


def detect_type(filename):
    normalized_filename = re.sub(r"[\s_-]+", "", filename)
    for needle, stat_type in TYPE_RULES:
        if re.sub(r"[\s_-]+", "", needle) in normalized_filename:
            return stat_type
    return None


def detect_type_from_rows(filename, rows):
    """Promote generic ranking exports only when every row is lodging-only."""
    stat_type = detect_type(filename)
    if stat_type != "search_ranking" or not rows:
        return stat_type
    categories = [
        normalize_place_name(lodging_rank_value(row, "mid_category"))
        for row in rows
    ]
    required_values_present = all(
        lodging_rank_value(row, "place_name")
        and lodging_rank_value(row, "rank")
        and lodging_rank_value(row, "datalab_id")
        for row in rows
    )
    if (
        required_values_present
        and categories
        and all(category in {"숙박", "관광숙박"} for category in categories)
    ):
        return "lodging_search_rank"
    return stat_type


def source_period(path):
    return source_period_name(path.name)


def source_period_name(name):
    """Extract a Data Lab period from either a Path or an uploaded filename."""
    match = re.search(r"_(\d{6})-(\d{6})_", name)
    return f"{match.group(1)}-{match.group(2)}" if match else None


def iter_csvs(paths):
    for path in paths:
        if path.suffix.lower() == ".zip":
            with zipfile.ZipFile(path) as archive:
                for info in archive.infolist():
                    name = clean_archive_name(info.filename)
                    if name.lower().endswith(".csv"):
                        yield path, name, archive.read(info)
        elif path.suffix.lower() == ".csv":
            yield path, path.name, path.read_bytes()


def generic_fields(stat_type, row):
    if stat_type in {"surge_domestic_dong", "surge_foreign_dong"}:
        return row.get("시도명"), row.get("시군구명"), row.get("기준년월"), (
            ("관광객수", "명"),
            ("전년동기관광객수", "명"),
            ("증감율", "%"),
        )
    if stat_type in FIELD_MAP:
        (sido_key, sgg_key), metrics = FIELD_MAP[stat_type]
        return row.get(sido_key), row.get(sgg_key) if sgg_key else None, None, metrics
    if stat_type == "visitor_trend":
        return row.get("광역지자체"), None, row.get("기준년월"), (("방문자 수", "명"),)
    if stat_type == "foreign_trend":
        return row.get("지역"), None, row.get("날짜"), (("외국인 방문자수", "명"),)
    if stat_type == "consumption_trend":
        return row.get("광역지자체"), None, row.get("기준년월"), (("지출액(천원)", "천원"),)
    if stat_type == "search_trend":
        return row.get("광역지자체"), None, row.get("기준년월"), (("광역지자체 검색건수", "건"),)
    if stat_type == "search_ranking":
        return row.get("광역시/도"), row.get("시/군/구"), None, (("검색건수", "건"),)
    if stat_type == "foreign_country":
        return None, None, None, (("비율(%)", "%"),)
    if stat_type == "camping_sector":
        return None, None, row.get("기준년도"), (
            ("현황수", "개"),
            ("분포율", "%"),
        )
    if stat_type == "camping_site_type":
        return None, None, row.get("기준년도"), (("현황수", "개"),)
    if stat_type == "lodging_sector":
        return None, None, row.get("기준년도"), (
            ("숙박영업현황수", "개"),
            ("분포율", "%"),
        )
    if stat_type == "consumption_sector":
        return None, None, None, (
            ("대분류 지출액 비율", "%"),
            ("중분류 지출액 비율", "%"),
        )
    return None, None, None, ()


def build_member_metric_rows(source_file, filename, csv_rows, period):
    """Canonical CSV-member parser used by both CLI and admin staging.

    Row hashes deliberately retain the historical JSON identity format.
    """
    stat_type = detect_type_from_rows(filename, csv_rows)
    if not stat_type:
        return [], None, len(csv_rows)
    if stat_type == "lodging_search_rank":
        validate_lodging_top100_address_rows(filename, csv_rows)
    output, skipped = [], 0
    for row_index, row in enumerate(csv_rows, 2):
        if stat_type == "lodging_search_rank":
            built = build_lodging_rank_row(row, source_file, period, row_index=row_index)
            if built:
                output.append(built)
            else:
                skipped += 1
            continue
        sido, sgg, ref, metrics = generic_fields(stat_type, row)
        sido, sgg = normalize_region(sido, sgg)
        dimensions = {k: v for k, v in row.items() if v not in (None, "")}
        before = len(output)
        parsed_metrics = []
        for metric_name, unit in metrics:
            value = number(row.get(metric_name))
            if value is None:
                parsed_metrics = []
                break
            parsed_metrics.append((metric_name, unit, value))
        if not parsed_metrics or len(parsed_metrics) != len(metrics):
            skipped += 1
            continue
        for metric_name, unit, value in parsed_metrics:
            identity = json.dumps([source_file, stat_type, row_index, metric_name], ensure_ascii=False)
            output.append((stat_type, sido, sgg, ref, metric_name, value, unit,
                           source_file, period, json.dumps(dimensions, ensure_ascii=False),
                           hashlib.sha256(identity.encode()).hexdigest()))
        if len(output) == before:
            skipped += 1
    return output, stat_type, skipped


def build_rows(paths):
    output = []
    skipped = []
    for outer, filename, raw in iter_csvs(paths):
        text = raw.decode("utf-8-sig")
        csv_rows = list(csv.DictReader(io.StringIO(text)))
        source_file = f"{outer.name}::{filename}"
        member_rows, stat_type, _ = build_member_metric_rows(
            source_file, filename, csv_rows, source_period(outer)
        )
        if not stat_type:
            skipped.append(filename)
            continue
        output.extend(member_rows)
    hashes = [row[10] for row in output]
    if len(hashes) != len(set(hashes)):
        raise ValueError("중복 행 해시가 있는 원본입니다.")
    return output, skipped


def _lodging_rank_place_matches(expected, candidate):
    """Require the Kakao result to identify the requested lodging, not just a region."""
    expected_key = normalize_place_name(expected) or ""
    candidate_key = normalize_place_name(candidate) or ""
    if not expected_key or not candidate_key:
        return False
    return (
        expected_key == candidate_key
        or (len(expected_key) >= 5 and expected_key in candidate_key)
        or (len(candidate_key) >= 5 and candidate_key in expected_key)
    )


def _kakao_address_matches_source_region(address, sido, sgg):
    """Reject Kakao branch/chain hits outside the rank row's reported region."""
    address_key = normalize_place_name(address) or ""
    sgg_key = normalize_place_name(sgg) or ""
    if not address_key or not sgg_key or sgg_key not in address_key:
        return False
    sido_key = re.sub(
        r"(특별자치도|특별자치시|특별시|광역시|도|시)$", "",
        normalize_place_name(sido) or "",
    )
    sido_key = re.sub(r"^전라", "전", sido_key)
    sido_key = re.sub(r"^충청", "충", sido_key)
    sido_key = re.sub(r"^경상", "경", sido_key)
    return bool(sido_key) and sido_key in address_key


def _verified_kakao_candidates(place_name, sido, sgg, documents):
    """Filter Kakao keyword hits by both lodging identity and returned region."""
    return [
        item for item in documents
        if _lodging_rank_place_matches(place_name, item.get("place_name"))
        and (item.get("road_address_name") or item.get("address_name"))
        and _kakao_address_matches_source_region(
            item.get("road_address_name") or item.get("address_name"), sido, sgg
        )
    ]


def verify_latest_top100_lodging_addresses(cur):
    """Save Kakao-confirmed addresses for unlinked rows in the latest TOP100.

    Kakao has no multi-keyword endpoint, so this deliberately reads the bounded
    TOP100 set once and checks it as one import batch.  The result is evidence
    for the later address-only building match; a business name is never used as
    a building-link key.
    """
    api_key = os.environ.get("KAKAO_REST_API_KEY", "").strip()
    if not api_key:
        print("경고: KAKAO_REST_API_KEY가 없어 TOP100 미연결 숙소 주소 확인을 건너뜁니다.")
        return {"checked": 0, "confirmed": 0}
    cur.execute(f"""
        WITH latest AS (
            SELECT source_file
            FROM tourism_stats t
            WHERE stat_type = 'lodging_search_rank'
            ORDER BY {latest_source_order_sql("t")}
            LIMIT 1
        )
        SELECT t.id, t.sido_name, t.sgg_name, t.dimensions->>'place_name' AS place_name
        FROM tourism_stats t
        JOIN latest l ON l.source_file = t.source_file
        WHERE t.stat_type = 'lodging_search_rank'
          AND t.master_building_id IS NULL
          AND t.metric_value > 0 AND t.metric_value <= 100
          AND NULLIF(t.dimensions->>'road_address', '') IS NULL
          AND NULLIF(t.dimensions->>'kakao_confirmed_address', '') IS NULL
        ORDER BY t.metric_value, t.id
        LIMIT 100
    """)
    pending = cur.fetchall()
    confirmed = 0
    for raw in pending:
        row = dict(raw)
        place_name = (row.get("place_name") or "").strip()
        if not place_name:
            continue
        try:
            request = urllib.request.Request(
                _KAKAO_LOCAL_KEYWORD_URL + "?" + urllib.parse.urlencode({
                    "query": " ".join(filter(None, (
                        place_name, row.get("sido_name"), row.get("sgg_name"),
                    ))),
                    "size": 5,
                }),
                headers={"Authorization": f"KakaoAK {api_key}"},
            )
            with urllib.request.urlopen(request, timeout=8) as response:
                documents = json.load(response).get("documents") or []
        except Exception as exc:
            print(f"TOP100 숙소 주소 확인 실패: {place_name} ({type(exc).__name__})")
            continue
        eligible = _verified_kakao_candidates(
            place_name, row.get("sido_name"), row.get("sgg_name"), documents
        )
        # A chain can return similarly named branches.  Even two results at a
        # similarly formatted address are not proof that they denote one
        # facility, so accept one verified Kakao candidate only.
        if len(eligible) != 1:
            _set_lodging_match_review(
                cur, row["id"],
                ("kakao_candidate_address_ambiguous" if eligible
                 else "kakao_candidate_not_verified"),
                {"eligible_candidate_count": len(eligible), "addresses": [
                    str(item.get("road_address_name") or item.get("address_name") or "")
                    for item in eligible
                ]},
            )
            continue
        document = eligible[0]
        address = str(
            document.get("road_address_name") or document.get("address_name") or ""
        ).strip()
        if not address:
            continue
        cur.execute("""
            UPDATE tourism_stats
            SET dimensions = dimensions || jsonb_build_object(
                'kakao_confirmed_address', %s,
                'kakao_confirmed_road_address', %s,
                'kakao_confirmed_jibun_address', %s,
                'kakao_x', %s,
                'kakao_y', %s
            )
            WHERE id = %s
              AND master_building_id IS NULL
        """, (
            address,
            str(document.get("road_address_name") or "").strip() or None,
            str(document.get("address_name") or "").strip() or None,
            str(document.get("x") or "").strip() or None,
            str(document.get("y") or "").strip() or None,
            row["id"],
        ))
        confirmed += cur.rowcount
    print(f"TOP100 미연결 숙소 카카오 주소 확인: {confirmed}/{len(pending)}건")
    return {"checked": len(pending), "confirmed": confirmed}


_KAKAO_LOCAL_KEYWORD_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"


def _set_lodging_match_review(cur, stat_id, reason, evidence=None):
    """Persist an auditable, retry-safe reason instead of guessing a tower."""
    cur.execute("""
        UPDATE tourism_stats
        SET dimensions = dimensions || jsonb_build_object(
            'lodging_match_review_reason', %s,
            'lodging_match_review_evidence', %s::jsonb
        )
        WHERE id = %s AND master_building_id IS NULL
    """, (reason, json.dumps(evidence or {}, ensure_ascii=False), stat_id))


def _hub_lodging_identities(title_rows):
    """Return all distinct lodging-building identities at one verified parcel."""
    identities = {}
    for row in title_rows:
        text = f"{row.get('mainPurpsCdNm', '')} {row.get('etcPurps', '')}"
        if "숙박" not in text:
            continue
        # The HUB management PK is stable across refreshes.  Do not fall back
        # to a display/tourism business name: an absent HUB identity is manual.
        identity = (row.get("mgmBldrgstPk") or "").strip()
        if not identity:
            continue
        identities.setdefault(identity, []).append(row)
    return identities


def _classify_hub_title_snapshot(title_rows, identities):
    """Classify/reselect solely from the fetched HUB snapshot.

    ``classify_lodging_type`` may fetch a newer title/floor snapshot.  That can
    disagree with the management identity checked immediately above, so this
    conservative path accepts only title-row evidence and leaves floor-only
    classification for manual review.
    """
    if len(identities) != 1:
        return None, "", None, None, "lodging identity is not unique"
    identity, rows = next(iter(identities.items()))
    representative = _title_row_to_dict(max(rows, key=_hocnt))
    categories, details = set(), []
    for row in title_rows:
        text = f"{row.get('mainPurpsCdNm', '')} {row.get('etcPurps', '')}".strip()
        categories |= _find_categories(text)
        if text:
            details.append(text)
    if len(categories) > 1:
        return None, "", None, None, "title snapshot has mixed lodging categories"
    if categories:
        label = next(iter(categories))
        subtype = next((
            extract_tourist_subtype(
                f"{row.get('mainPurpsCdNm', '')} {row.get('etcPurps', '')}"
            )
            for row in title_rows
            if extract_tourist_subtype(
                f"{row.get('mainPurpsCdNm', '')} {row.get('etcPurps', '')}"
            )
        ), None)
        return label, " / ".join(sorted(set(details))), subtype, representative, "title snapshot"
    # Explicit 숙박 primary use is sufficient for the registry's general-
    # lodging fallback, without relying on a second floor API call.
    if all("숙박" in (row.get("mainPurpsCdNm") or "") for row in rows):
        return "일반", " / ".join(sorted(set(details))), None, representative, "title snapshot lodging fallback"
    return None, "", None, None, "title snapshot requires floor-dependent classification"


def enrich_latest_top100_lodging_buildings(
        cur, bjdong=None, *, road_to_jibun_fn=road_to_jibun,
        fetch_title_rows_fn=_fetch_title_rows):
    """Create only one unambiguous lodging HUB building for confirmed TOP100.

    The Kakao road address is converted to a legal parcel before calling
    Building HUB.  A parcel with multiple lodging management-building IDs is
    not resolved by business name, title name, or coordinates; it is recorded
    for manual review.  ``bjdong`` and API callables are injectable for tests.
    """
    if bjdong is None:
        code_path = os.environ.get("BJDONG_CODE_CSV", "법정동코드_전체자료.zip")
        if not os.path.exists(code_path):
            print("경고: 법정동 코드 파일이 없어 TOP100 건축HUB 보완을 건너뜁니다.")
            return {"checked": 0, "created": 0, "manual_review": 0}
        bjdong = BjdongMap(code_path)
    cur.execute(f"""
        WITH latest AS (
            SELECT source_file FROM tourism_stats t
            WHERE stat_type = 'lodging_search_rank'
            ORDER BY {latest_source_order_sql("t")}
            LIMIT 1
        )
        SELECT t.id, t.dimensions
        FROM tourism_stats t JOIN latest l ON l.source_file = t.source_file
        WHERE t.stat_type = 'lodging_search_rank'
          AND t.master_building_id IS NULL
          AND t.metric_value > 0 AND t.metric_value <= 100
          AND (
              NULLIF(t.dimensions->>'road_address', '') IS NOT NULL
              OR NULLIF(t.dimensions->>'kakao_confirmed_address', '') IS NOT NULL
          )
        ORDER BY t.metric_value, t.id LIMIT 100
    """)
    pending = [dict(row) for row in cur.fetchall()]
    created = manual_review = 0
    for stat in pending:
        dimensions = stat.get("dimensions") or {}
        road_address = (
            dimensions.get("road_address")
            or dimensions.get("kakao_confirmed_road_address")
            or ""
        ).strip()
        if not road_address:
            _set_lodging_match_review(cur, stat["id"], "verified_road_address_missing")
            manual_review += 1
            continue
        try:
            parcel = road_to_jibun_fn(road_address)
        except Exception as exc:
            _set_lodging_match_review(
                cur, stat["id"], "road_to_jibun_failed", {"error": type(exc).__name__}
            )
            manual_review += 1
            continue
        if not parcel:
            _set_lodging_match_review(cur, stat["id"], "road_to_jibun_not_found")
            manual_review += 1
            continue
        sgg_cd = str(parcel.get("admCd") or "")[:5]
        umd_nm = (parcel.get("emdNm") or "").strip()
        main = str(parcel.get("lnbrMnnm") or "").strip()
        sub = str(parcel.get("lnbrSlno") or "").strip()
        if not (sgg_cd and umd_nm and main):
            _set_lodging_match_review(cur, stat["id"], "road_to_jibun_incomplete")
            manual_review += 1
            continue
        bjdong_cd = bjdong.find_bjdong_cd(sgg_cd, umd_nm)
        if not bjdong_cd:
            _set_lodging_match_review(cur, stat["id"], "building_hub_bjdong_not_found")
            manual_review += 1
            continue
        jibun = f"{'산 ' if str(parcel.get('mtYn') or '') == '1' else ''}{main}"
        if sub and sub != "0":
            jibun += f"-{sub}"
        plat_gb, bun, ji = parse_jibun(jibun)
        try:
            title_rows = fetch_title_rows_fn(sgg_cd, bjdong_cd, plat_gb, bun, ji)
        except Exception as exc:
            _set_lodging_match_review(
                cur, stat["id"], "building_hub_title_failed", {"error": type(exc).__name__}
            )
            manual_review += 1
            continue
        identities = _hub_lodging_identities(title_rows)
        if len(identities) != 1:
            _set_lodging_match_review(cur, stat["id"], "building_hub_lodging_identity_ambiguous", {
                "lodging_identity_count": len(identities),
                "lodging_management_ids": sorted(identities),
            })
            manual_review += 1
            continue
        identity, rows = next(iter(identities.items()))
        label, detail, subtype, representative, classification_reason = (
            _classify_hub_title_snapshot(title_rows, identities)
        )
        if label not in {"생활", "관광", "일반"}:
            _set_lodging_match_review(cur, stat["id"], "building_hub_title_classification_uncertain", {
                "classification": label, "reason": classification_reason,
                "management_id": identity,
            })
            manual_review += 1
            continue
        building_name = resolve_api_building_name(representative)
        if not building_name:
            _set_lodging_match_review(cur, stat["id"], "building_hub_building_name_missing", {
                "management_id": identity,
            })
            manual_review += 1
            continue
        # mgmBldrgstPk is the Building HUB identity.  The schema intentionally
        # does not impose it as a global unique key, so inspect duplicates
        # rather than relying on an invalid ON CONFLICT target.
        cur.execute("""
            SELECT id FROM master_buildings WHERE mgm_bldrgst_pk = %s ORDER BY id
        """, (identity,))
        existing = cur.fetchall()
        if len(existing) > 1:
            _set_lodging_match_review(cur, stat["id"], "building_hub_identity_duplicate", {
                "management_id": identity, "master_building_count": len(existing),
            })
            manual_review += 1
            continue
        if existing:
            cur.execute("""
                UPDATE master_buildings
                SET road_address = COALESCE(road_address, %s),
                    jibun_address = COALESCE(jibun_address, %s)
                WHERE id = %s
            """, (
                road_address,
                representative.get("plat_plc") or dimensions.get("kakao_confirmed_jibun_address"),
                dict(existing[0])["id"],
            ))
            continue
        cur.execute("""
            INSERT INTO master_buildings
                (building_name, road_address, jibun_address, sgg_text, sgg_cd,
                 umd_nm, jibun, units, source, verified_at, lodging_type,
                 lodging_type_detail, lodging_subtype, mgm_bldrgst_pk, lat, lng)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'tourism_verified', NOW(),
                    %s, %s, %s, %s, %s, %s)
        """, (
            building_name, road_address,
            representative.get("plat_plc") or dimensions.get("kakao_confirmed_jibun_address"),
            bjdong.sgg_text(sgg_cd) or "", sgg_cd, normalize_umd_nm(umd_nm), jibun,
            representative.get("ho_cnt") or 0, label, detail, subtype, identity,
            float(dimensions["kakao_y"]) if dimensions.get("kakao_y") else None,
            float(dimensions["kakao_x"]) if dimensions.get("kakao_x") else None,
        ))
        created += cur.rowcount
    print(f"TOP100 건축HUB 보완: 생성 {created}/{len(pending)}, 수동검토 {manual_review}")
    return {"checked": len(pending), "created": created, "manual_review": manual_review}


def match_lodging_rank_to_buildings(cur, source_files):
    """Attach rank rows only when a verified road address has one master match.

    Same-address multi-building complexes intentionally remain unlinked for
    manual review.  Selecting an arbitrary/nearest tower would make the detail
    link look authoritative while being unsafe.
    """
    if not source_files:
        return {"total": 0, "address": 0, "unmatched": 0}
    scope = ("lodging_search_rank", source_files)
    cur.execute("""
        SELECT COUNT(*) AS total
        FROM tourism_stats
        WHERE stat_type = %s AND source_file = ANY(%s)
    """, scope)
    count_row = cur.fetchone()
    total = (
        count_row["total"]
        if isinstance(count_row, dict)
        else count_row[0]
    )
    cur.execute("""
        SELECT id, dimensions
        FROM tourism_stats
        WHERE stat_type = %s AND source_file = ANY(%s)
          AND master_building_id IS NULL
          AND (
              NULLIF(dimensions->>'road_address', '') IS NOT NULL
              OR NULLIF(dimensions->>'kakao_confirmed_address', '') IS NOT NULL
          )
    """, scope)
    stats = [dict(row) for row in cur.fetchall()]
    cur.execute("""
        SELECT id, road_address, jibun_address
        FROM master_buildings
        WHERE road_address IS NOT NULL OR jibun_address IS NOT NULL
    """)
    road_matches, jibun_matches = {}, {}
    for raw in cur.fetchall():
        building = dict(raw)
        road_key = addr_norm.normalize_road_prefix(building.get("road_address"))
        jibun_key = addr_norm.normalize_jibun_prefix(building.get("jibun_address"))
        if road_key:
            road_matches.setdefault(road_key, set()).add(building["id"])
        if jibun_key:
            jibun_matches.setdefault(jibun_key, set()).add(building["id"])
    updates = []
    for stat in stats:
        dimensions = stat.get("dimensions") or {}
        candidates = set()
        road_key = addr_norm.normalize_road_prefix(
            dimensions.get("road_address")
            or dimensions.get("kakao_confirmed_road_address")
        )
        jibun_key = addr_norm.normalize_jibun_prefix(
            dimensions.get("kakao_confirmed_jibun_address")
        )
        if road_key:
            candidates.update(road_matches.get(road_key, set()))
        if jibun_key:
            candidates.update(jibun_matches.get(jibun_key, set()))
        if len(candidates) == 1:
            updates.append((next(iter(candidates)), stat["id"]))
    address = 0
    for building_id, stat_id in updates:
        cur.execute("""
            UPDATE tourism_stats
            SET master_building_id = %s
            WHERE id = %s AND master_building_id IS NULL
        """, (building_id, stat_id))
        address += cur.rowcount
    result = {
        "total": total,
        "address": address,
        "unmatched": total - address,
    }
    print(
        "관광숙박 검색순위 건물 매칭: "
        f"전체 {total}, 상세주소 일치 {address}, 미매칭 {result['unmatched']}"
    )
    return result


def refresh_coords(cur):
    cur.execute("""
        INSERT INTO sgg_coords
            (sido_name, sgg_name, lat, lng, building_count, refreshed_at)
        SELECT
            split_part(trim(sgg_text), ' ', 1),
            regexp_replace(trim(sgg_text), '^\\S+\\s+', ''),
            AVG(lat), AVG(lng), COUNT(*), NOW()
        FROM master_buildings
        WHERE lat IS NOT NULL AND lng IS NOT NULL
          AND NULLIF(trim(sgg_text), '') IS NOT NULL
          AND position(' ' in trim(sgg_text)) > 0
        GROUP BY 1, 2
        ON CONFLICT (sido_name, sgg_name) DO UPDATE SET
            lat = EXCLUDED.lat,
            lng = EXCLUDED.lng,
            building_count = EXCLUDED.building_count,
            refreshed_at = NOW()
    """)


def refresh_dong_coords(cur):
    """급등동네 행정동을 마스터 건물의 같은 법정동 좌표 중심에 연결한다."""
    cur.execute("""
        WITH requested AS (
            SELECT DISTINCT
                sido_name,
                sgg_name,
                dimensions->>'행정동명' AS dong_name,
                regexp_replace(dimensions->>'행정동명', '[0-9]+동$', '동') AS legal_dong_name
            FROM tourism_stats
            WHERE stat_type IN ('surge_domestic_dong', 'surge_foreign_dong')
              AND NULLIF(dimensions->>'행정동명', '') IS NOT NULL
        ),
        building_points AS (
            SELECT
                r.sido_name,
                r.sgg_name,
                r.dong_name,
                AVG(m.lat) AS lat,
                AVG(m.lng) AS lng,
                COUNT(*) AS building_count
            FROM requested r
            JOIN master_buildings m
              ON split_part(trim(m.sgg_text), ' ', 1) = r.sido_name
             AND regexp_replace(trim(m.sgg_text), '^\\S+\\s+', '') = r.sgg_name
             AND trim(m.umd_nm) = r.legal_dong_name
            WHERE m.lat IS NOT NULL AND m.lng IS NOT NULL
            GROUP BY r.sido_name, r.sgg_name, r.dong_name
        )
        INSERT INTO tourism_dong_coords
            (sido_name, sgg_name, dong_name, lat, lng, building_count, refreshed_at)
        SELECT sido_name, sgg_name, dong_name, lat, lng, building_count, NOW()
        FROM building_points
        ON CONFLICT (sido_name, sgg_name, dong_name) DO UPDATE SET
            lat = EXCLUDED.lat,
            lng = EXCLUDED.lng,
            building_count = EXCLUDED.building_count,
            refreshed_at = NOW()
    """)


def geocode_missing_dong_coords(cur):
    """건물 중심 좌표가 없는 행정동은 주민센터 검색 좌표로 보완한다."""
    api_key = os.environ.get("KAKAO_REST_API_KEY")
    if not api_key:
        print("경고: KAKAO_REST_API_KEY가 없어 행정동 누락 좌표를 보완하지 못했습니다.")
        return
    cur.execute("""
        SELECT DISTINCT
            t.sido_name,
            t.sgg_name,
            t.dimensions->>'행정동명' AS dong_name
        FROM tourism_stats t
        LEFT JOIN tourism_dong_coords c
          ON c.sido_name = t.sido_name
         AND c.sgg_name = t.sgg_name
         AND c.dong_name = t.dimensions->>'행정동명'
        WHERE t.stat_type IN ('surge_domestic_dong', 'surge_foreign_dong')
          AND NULLIF(t.dimensions->>'행정동명', '') IS NOT NULL
          AND (c.id IS NULL OR c.lat IS NULL OR c.lng IS NULL)
        ORDER BY t.sido_name, t.sgg_name, t.dimensions->>'행정동명'
    """)
    missing = cur.fetchall()
    resolved = 0
    for sido, sgg, dong in missing:
        query = f"{sido} {sgg} {dong} 주민센터"
        url = "https://dapi.kakao.com/v2/local/search/keyword.json?" + urllib.parse.urlencode({
            "query": query,
            "size": 1,
        })
        request = urllib.request.Request(
            url,
            headers={"Authorization": f"KakaoAK {api_key}"},
        )
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                payload = json.load(response)
            documents = payload.get("documents") or []
            if not documents:
                print(f"행정동 좌표 미확인: {sido} {sgg} {dong}")
                continue
            lat = float(documents[0]["y"])
            lng = float(documents[0]["x"])
            if not (33 <= lat <= 39 and 124 <= lng <= 132):
                print(f"행정동 좌표 범위 오류: {sido} {sgg} {dong}")
                continue
            cur.execute("""
                INSERT INTO tourism_dong_coords
                    (sido_name, sgg_name, dong_name, lat, lng, building_count, refreshed_at)
                VALUES (%s, %s, %s, %s, %s, 0, NOW())
                ON CONFLICT (sido_name, sgg_name, dong_name) DO UPDATE SET
                    lat = EXCLUDED.lat,
                    lng = EXCLUDED.lng,
                    refreshed_at = NOW()
            """, (sido, sgg, dong, lat, lng))
            resolved += 1
        except Exception as exc:
            print(f"행정동 좌표 조회 실패: {sido} {sgg} {dong} ({type(exc).__name__})")
    if missing:
        print(f"행정동 좌표 보완: {resolved}/{len(missing)}곳")


def _normalized_tourism_region_name(value):
    return re.sub(r"(특별자치도|특별자치시|특별시|광역시|도|시)$", "", str(value or "").strip())


def _verified_admin_dong(documents, sido, sgg, allowed_dongs):
    """좌표 API 응답에서 대상 지역의 유일한 행정동(H)만 반환한다."""
    expected_sido = _normalized_tourism_region_name(sido)
    expected_sgg = re.sub(r"\s+", "", str(sgg or "").strip())
    allowed = {str(name or "").strip() for name in allowed_dongs}
    region_dongs = {
        str(item.get("region_3depth_name") or "").strip()
        for item in (documents or [])
        if item.get("region_type") == "H"
        and _normalized_tourism_region_name(item.get("region_1depth_name")) == expected_sido
        and re.sub(r"\s+", "", str(item.get("region_2depth_name") or "").strip()) == expected_sgg
    }
    if len(region_dongs) != 1:
        return None
    admin_dong = next(iter(region_dongs))
    return admin_dong if admin_dong in allowed else None


def refresh_building_dong_matches(cur):
    """숫자 분동 후보 건물을 좌표 기반 행정동으로 검증해 교차표를 갱신한다."""
    api_key = os.environ.get("KAKAO_REST_API_KEY")
    if not api_key:
        print("경고: KAKAO_REST_API_KEY가 없어 분동 건물 검증을 건너뜁니다.")
        return
    cur.execute("""
        WITH requested AS (
            SELECT DISTINCT
                sido_name,
                sgg_name,
                trim(dimensions->>'행정동명') AS admin_dong_name,
                regexp_replace(trim(dimensions->>'행정동명'), '[0-9]+동$', '동') AS legal_dong_name
            FROM tourism_stats
            WHERE stat_type IN ('surge_domestic_dong', 'surge_foreign_dong')
              AND trim(dimensions->>'행정동명') ~ '[0-9]+동$'
        )
        SELECT
            m.id AS building_id, m.lat, m.lng, trim(m.umd_nm) AS legal_dong_name,
            r.sido_name, r.sgg_name,
            array_agg(DISTINCT r.admin_dong_name ORDER BY r.admin_dong_name) AS allowed_dongs
        FROM requested r
        JOIN master_buildings m
          ON regexp_replace(split_part(trim(m.sgg_text), ' ', 1),
               '(특별자치도|특별자치시|특별시|광역시|도|시)$', '') =
             regexp_replace(r.sido_name,
               '(특별자치도|특별자치시|특별시|광역시|도|시)$', '')
         AND regexp_replace(trim(m.sgg_text), '^\\S+\\s+', '') = r.sgg_name
         AND trim(m.umd_nm) = r.legal_dong_name
        LEFT JOIN tourism_building_dong_matches existing
          ON existing.building_id = m.id
         AND existing.building_lat = m.lat
         AND existing.building_lng = m.lng
        WHERE m.lat IS NOT NULL AND m.lng IS NOT NULL
          AND existing.building_id IS NULL
        GROUP BY m.id, m.lat, m.lng, trim(m.umd_nm), r.sido_name, r.sgg_name
        ORDER BY m.id
    """)
    candidates = cur.fetchall()
    verified = 0
    for row in candidates:
        url = "https://dapi.kakao.com/v2/local/geo/coord2regioncode.json?" + urllib.parse.urlencode({
            "x": row["lng"],
            "y": row["lat"],
        })
        request = urllib.request.Request(
            url,
            headers={"Authorization": f"KakaoAK {api_key}"},
        )
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                payload = json.load(response)
            admin_dong = _verified_admin_dong(
                payload.get("documents"), row["sido_name"], row["sgg_name"], row["allowed_dongs"]
            )
            if not admin_dong:
                cur.execute(
                    "DELETE FROM tourism_building_dong_matches WHERE building_id = %s",
                    (row["building_id"],),
                )
                continue
            cur.execute("""
                INSERT INTO tourism_building_dong_matches
                    (building_id, sido_name, sgg_name, legal_dong_name, admin_dong_name,
                     building_lat, building_lng, verification_source, verified_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'kakao_coord2regioncode', NOW())
                ON CONFLICT (building_id) DO UPDATE SET
                    sido_name = EXCLUDED.sido_name,
                    sgg_name = EXCLUDED.sgg_name,
                    legal_dong_name = EXCLUDED.legal_dong_name,
                    admin_dong_name = EXCLUDED.admin_dong_name,
                    building_lat = EXCLUDED.building_lat,
                    building_lng = EXCLUDED.building_lng,
                    verification_source = EXCLUDED.verification_source,
                    verified_at = NOW()
            """, (
                row["building_id"], row["sido_name"], row["sgg_name"], row["legal_dong_name"],
                admin_dong, row["lat"], row["lng"],
            ))
            verified += 1
        except Exception as exc:
            print(f"분동 건물 검증 실패: building_id={row['building_id']} ({type(exc).__name__})")
    if candidates:
        print(f"분동 건물 검증: {verified}/{len(candidates)}개")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default="datalab_csv")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    root = Path(args.dir)
    paths = sorted([*root.glob("*.zip"), *root.glob("*.csv")])
    rows, skipped = build_rows(paths)
    print(f"파일 {len(paths)}개, 지표 행 {len(rows):,}개, 미지원 CSV {len(skipped)}개")
    if skipped:
        print("미지원:", ", ".join(skipped))
    if args.dry_run:
        counts = {}
        for row in rows:
            counts[row[0]] = counts.get(row[0], 0) + 1
        for key in sorted(counts):
            print(f"  {key}: {counts[key]:,}")
        return
    if not paths:
        raise SystemExit(f"{root}에 ZIP 또는 CSV가 없습니다.")
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        source_files = sorted({row[7] for row in rows})
        cur.execute(
            "DELETE FROM tourism_stats WHERE source_file = ANY(%s)",
            (source_files,),
        )
        execute_values(cur, """
            INSERT INTO tourism_stats
                (stat_type, sido_name, sgg_name, ref_yearmonth, metric_name,
                 metric_value, unit, source_file, source_period, dimensions, row_hash)
            VALUES %s
            ON CONFLICT (row_hash) DO UPDATE SET
                metric_value = EXCLUDED.metric_value,
                dimensions = EXCLUDED.dimensions
        """, rows, page_size=1000)
        verify_latest_top100_lodging_addresses(cur)
        enrich_latest_top100_lodging_buildings(cur)
        match_lodging_rank_to_buildings(cur, source_files)
        refresh_coords(cur)
        refresh_dong_coords(cur)
        geocode_missing_dong_coords(cur)
        refresh_building_dong_matches(cur)
        conn.commit()
        print(f"적재/갱신 완료: {len(rows):,}개 지표 행")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()