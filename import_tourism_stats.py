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
from psycopg2.extras import execute_values


TYPE_RULES = (
    # This must precede the generic attraction-ranking rule below: the two
    # exports have similarly named filenames but describe different entities.
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


def build_lodging_rank_row(row, source_file, period, row_index=None):
    """Build the one canonical metric emitted by a lodging-rank CSV row."""
    place_name = lodging_rank_value(row, "place_name")
    rank = number(lodging_rank_value(row, "rank"))
    if not place_name or rank is None or rank <= 0:
        return None
    sido, sgg = normalize_region(row.get("광역시/도"), row.get("시/군/구"))
    dimensions = {
        key: lodging_rank_value(row, key)
        for key in ("datalab_id", "place_name", "sub_category", "mid_category", "search_count")
    }
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


def match_lodging_rank_to_buildings(cur, source_files):
    """Attach only unambiguous, same-region lodging-rank rows to buildings."""
    if not source_files:
        return {"total": 0, "exact": 0, "containment": 0, "unmatched": 0}
    scope = ("lodging_search_rank", source_files)
    cur.execute("""
        SELECT COUNT(*)
        FROM tourism_stats
        WHERE stat_type = %s AND source_file = ANY(%s)
    """, scope)
    total = cur.fetchone()[0]
    building_sido = region_core_sql(
        "split_part(trim(b.sgg_text), ' ', 1)",
        "regexp_replace(trim(b.sgg_text), '^\\S+\\s+', '')",
    )
    tourism_sido = region_core_sql("t.sido_name", "t.sgg_name")
    # A candidate is eligible only if both normalized region components agree.
    # GROUP BY/HAVING deliberately rejects ambiguity rather than choosing an
    # arbitrary building.
    cur.execute(f"""
        WITH candidates AS (
            SELECT t.id AS tourism_stat_id, MIN(b.id) AS building_id
            FROM tourism_stats t
            JOIN master_buildings b
              ON {building_sido} = {tourism_sido}
             AND regexp_replace(lower(regexp_replace(trim(b.sgg_text), '^\\S+\\s+', '')), '\\s+', '', 'g')
                 = regexp_replace(lower(coalesce(t.sgg_name, '')), '\\s+', '', 'g')
             AND regexp_replace(lower(b.building_name), '[^0-9가-힣a-z]', '', 'g')
                 = regexp_replace(lower(coalesce(t.dimensions->>'place_name', '')), '[^0-9가-힣a-z]', '', 'g')
            WHERE t.stat_type = %s AND t.source_file = ANY(%s)
              AND t.master_building_id IS NULL
            GROUP BY t.id
            HAVING COUNT(DISTINCT b.id) = 1
        )
        UPDATE tourism_stats t
        SET master_building_id = c.building_id
        FROM candidates c
        WHERE t.id = c.tourism_stat_id
    """, scope)
    exact = cur.rowcount
    cur.execute(f"""
        WITH candidates AS (
            SELECT t.id AS tourism_stat_id, MIN(b.id) AS building_id
            FROM tourism_stats t
            JOIN master_buildings b
              ON {building_sido} = {tourism_sido}
             AND regexp_replace(lower(regexp_replace(trim(b.sgg_text), '^\\S+\\s+', '')), '\\s+', '', 'g')
                 = regexp_replace(lower(coalesce(t.sgg_name, '')), '\\s+', '', 'g')
            WHERE t.stat_type = %s AND t.source_file = ANY(%s)
              AND t.master_building_id IS NULL
              AND length(regexp_replace(lower(coalesce(t.dimensions->>'place_name', '')), '[^0-9가-힣a-z]', '', 'g')) >= 4
              AND length(regexp_replace(lower(b.building_name), '[^0-9가-힣a-z]', '', 'g')) >= 4
              AND (
                    regexp_replace(lower(b.building_name), '[^0-9가-힣a-z]', '', 'g')
                    LIKE '%%' || regexp_replace(lower(t.dimensions->>'place_name'), '[^0-9가-힣a-z]', '', 'g') || '%%'
                 OR regexp_replace(lower(t.dimensions->>'place_name'), '[^0-9가-힣a-z]', '', 'g')
                    LIKE '%%' || regexp_replace(lower(b.building_name), '[^0-9가-힣a-z]', '', 'g') || '%%'
              )
            GROUP BY t.id
            HAVING COUNT(DISTINCT b.id) = 1
        )
        UPDATE tourism_stats t
        SET master_building_id = c.building_id
        FROM candidates c
        WHERE t.id = c.tourism_stat_id
    """, scope)
    containment = cur.rowcount
    result = {
        "total": total,
        "exact": exact,
        "containment": containment,
        "unmatched": total - exact - containment,
    }
    print(
        "관광숙박 검색순위 건물 매칭: "
        f"전체 {total}, 정확 {exact}, 포함 {containment}, 미매칭 {result['unmatched']}"
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
        cur = conn.cursor()
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
        match_lodging_rank_to_buildings(cur, source_files)
        refresh_coords(cur)
        refresh_dong_coords(cur)
        geocode_missing_dong_coords(cur)
        conn.commit()
        print(f"적재/갱신 완료: {len(rows):,}개 지표 행")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()