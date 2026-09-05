#!/usr/bin/env python3
"""한국관광 데이터랩 ZIP/CSV를 열지도 전용 테이블에 멱등 적재한다."""

import argparse
import csv
import hashlib
import io
import json
import os
import re
import zipfile
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values


TYPE_RULES = (
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
        return float(text)
    except ValueError:
        return None


def detect_type(filename):
    for needle, stat_type in TYPE_RULES:
        if needle in filename:
            return stat_type
    return None


def source_period(path):
    match = re.search(r"_(\d{6})-(\d{6})_", path.name)
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
    if stat_type in {"camping_sector", "camping_site_type", "lodging_sector"}:
        return None, None, row.get("기준년도"), (
            ("현황수", "개"),
            ("숙박영업현황수", "개"),
            ("분포율", "%"),
        )
    if stat_type == "consumption_sector":
        return None, None, None, (
            ("대분류 지출액 비율", "%"),
            ("중분류 지출액 비율", "%"),
        )
    return None, None, None, ()


def build_rows(paths):
    output = []
    skipped = []
    for outer, filename, raw in iter_csvs(paths):
        stat_type = detect_type(filename)
        if not stat_type:
            skipped.append(filename)
            continue
        text = raw.decode("utf-8-sig")
        period = source_period(outer)
        source_file = f"{outer.name}::{filename}"
        for row_index, row in enumerate(csv.DictReader(io.StringIO(text)), 2):
            sido, sgg, ref, metrics = generic_fields(stat_type, row)
            sido, sgg = normalize_region(sido, sgg)
            dimensions = {k: v for k, v in row.items() if v not in (None, "")}
            for metric_name, unit in metrics:
                value = number(row.get(metric_name))
                if value is None:
                    continue
                # 값이 정정돼도 같은 원본 행·지표는 같은 식별자를 사용한다.
                # 실제 적재 시 source_file 단위로 교체하므로 삭제/순서변경도 남지 않는다.
                identity = json.dumps(
                    [source_file, stat_type, row_index, metric_name],
                    ensure_ascii=False,
                )
                output.append((
                    stat_type, sido, sgg, ref, metric_name, value, unit,
                    source_file, period, json.dumps(dimensions, ensure_ascii=False),
                    hashlib.sha256(identity.encode()).hexdigest(),
                ))
    return output, skipped


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
        refresh_coords(cur)
        conn.commit()
        print(f"적재/갱신 완료: {len(rows):,}개 지표 행")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()