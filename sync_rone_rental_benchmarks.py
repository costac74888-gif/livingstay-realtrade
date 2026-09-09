#!/usr/bin/env python3
"""R-ONE 오피스텔 수익률과 소규모 상가 전국 공실률을 캐시한다."""

import argparse
import hashlib
import json
import os
from datetime import date
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from db import get_conn


API_URL = "https://www.reb.or.kr/r-one/openapi/SttsApiTblData.do"
INCOME_TABLE_ID = "T245503133561624"
VACANCY_TABLE_ID = "T241833134686576"
INCOME_ITEM_ID = "10001"
VACANCY_ITEM_ID = "100001"
REGIONS_BY_GROUP = {
    "전국": ("00", "전국", "national"),
    "서울": ("11", "서울", "province"),
    "부산": ("26", "부산", "province"),
    "대구": ("27", "대구", "province"),
    "인천": ("28", "인천", "province"),
    "(구)광주": ("29", "광주", "province"),
    "대전": ("30", "대전", "province"),
    "울산": ("31", "울산", "province"),
    "세종": ("36", "세종", "province"),
    "경기": ("41", "경기", "province"),
}


def fetch_rows(api_key, table_id, cycle):
    rows = []
    page = 1
    while True:
        query = urlencode({
            "KEY": api_key,
            "Type": "json",
            "pIndex": page,
            "pSize": 1000,
            "STATBL_ID": table_id,
            "DTACYCLE_CD": cycle,
        })
        request = Request(f"{API_URL}?{query}", headers={"User-Agent": "HomeAndStay-RONE/1.0"})
        with urlopen(request, timeout=60) as response:
            payload = json.load(response)
        if "RESULT" in payload:
            result = payload["RESULT"]
            raise RuntimeError(f"R-ONE 응답 오류: {result.get('CODE')} {result.get('MESSAGE')}")
        blocks = payload.get("SttsApiTblData") or []
        if len(blocks) < 2:
            raise RuntimeError("R-ONE 응답에 데이터 블록이 없습니다.")
        total = int(blocks[0]["head"][0]["list_total_count"])
        page_rows = blocks[1].get("row") or []
        rows.extend(page_rows)
        if len(rows) >= total:
            return rows
        if not page_rows or page >= 20:
            raise RuntimeError("R-ONE 페이지 응답이 전체 건수 전에 끝났습니다.")
        page += 1


def quarter_date(identifier):
    text = str(identifier)
    if len(text) != 6 or not text.isdigit():
        raise ValueError(f"알 수 없는 R-ONE 분기 코드: {text}")
    year, quarter = int(text[:4]), int(text[-2:])
    if quarter not in (1, 2, 3, 4):
        raise ValueError(f"알 수 없는 R-ONE 분기 코드: {text}")
    return date(year, 1 + (quarter - 1) * 3, 1)


def month_date(identifier):
    text = str(identifier)
    if len(text) != 6 or not text.isdigit():
        raise ValueError(f"알 수 없는 R-ONE 월 코드: {text}")
    year, month = int(text[:4]), int(text[-2:])
    if not 1 <= month <= 12:
        raise ValueError(f"알 수 없는 R-ONE 월 코드: {text}")
    return date(year, month, 1)


def indexed_vacancies(rows):
    values = {}
    for row in rows:
        if str(row.get("CLS_ID") or "") != "500001":
            continue
        if str(row.get("ITM_ID") or "") != VACANCY_ITEM_ID or row.get("ITM_NM") != "공실률":
            continue
        period = quarter_date(row.get("WRTTIME_IDTFR_ID"))
        value = float(row["DTA_VAL"])
        values[period] = (value, row)
    return values


def build_records(income_rows, vacancy_rows, checked_at=None):
    vacancies = indexed_vacancies(vacancy_rows)
    vacancy_periods = sorted(vacancies)
    records = []
    for income_row in income_rows:
        group_name = str(income_row.get("GRP_FULLNM") or income_row.get("GRP_NM") or "")
        if group_name not in REGIONS_BY_GROUP or income_row.get("CLS_NM") != "전체":
            continue
        if str(income_row.get("ITM_ID") or "") != INCOME_ITEM_ID or income_row.get("ITM_NM") != "수익률":
            continue
        period = month_date(income_row.get("WRTTIME_IDTFR_ID"))
        eligible = [candidate for candidate in vacancy_periods if candidate <= period]
        if not eligible:
            continue
        vacancy_period = eligible[-1]
        vacancy_rate, vacancy_row = vacancies[vacancy_period]
        if not 0 <= vacancy_rate <= 100:
            raise ValueError(f"공실률 범위 오류: {vacancy_rate}")
        region_code, region_name, region_level = REGIONS_BY_GROUP[group_name]
        raw = json.dumps(
            {"income": income_row, "vacancy": vacancy_row},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        records.append({
            "period": period,
            "vacancy_period": vacancy_period,
            "region_code": region_code,
            "region_name": region_name,
            "region_level": region_level,
            "property_type": "officetel",
            "property_type_name": "오피스텔",
            "income_yield": float(income_row["DTA_VAL"]),
            "vacancy_rate": vacancy_rate,
            "source_hash": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        })
    return records


def save_records(records):
    conn = get_conn()
    cur = conn.cursor()
    try:
        for row in records:
            cur.execute("""
                INSERT INTO rone_rental_benchmarks (
                    period, vacancy_period, region_code, region_name, region_level,
                    property_type, property_type_name, income_yield, vacancy_rate,
                    source_stat_income_id, source_stat_vacancy_id,
                    source_item_income_id, source_item_vacancy_id,
                    source_checked_at, source_hash, collected_at
                ) VALUES (
                    %(period)s, %(vacancy_period)s, %(region_code)s, %(region_name)s, %(region_level)s,
                    %(property_type)s, %(property_type_name)s, %(income_yield)s, %(vacancy_rate)s,
                    %(income_table)s, %(vacancy_table)s, %(income_item)s, %(vacancy_item)s,
                    NOW(), %(source_hash)s, NOW()
                )
                ON CONFLICT (period, region_code, property_type) DO UPDATE SET
                    vacancy_period = EXCLUDED.vacancy_period,
                    region_name = EXCLUDED.region_name,
                    region_level = EXCLUDED.region_level,
                    property_type_name = EXCLUDED.property_type_name,
                    income_yield = EXCLUDED.income_yield,
                    vacancy_rate = EXCLUDED.vacancy_rate,
                    source_stat_income_id = EXCLUDED.source_stat_income_id,
                    source_stat_vacancy_id = EXCLUDED.source_stat_vacancy_id,
                    source_item_income_id = EXCLUDED.source_item_income_id,
                    source_item_vacancy_id = EXCLUDED.source_item_vacancy_id,
                    source_checked_at = EXCLUDED.source_checked_at,
                    source_hash = EXCLUDED.source_hash,
                    collected_at = NOW()
            """, {
                **row,
                "income_table": INCOME_TABLE_ID,
                "vacancy_table": VACANCY_TABLE_ID,
                "income_item": INCOME_ITEM_ID,
                "vacancy_item": VACANCY_ITEM_ID,
            })
        cur.execute("DELETE FROM rone_rental_benchmarks WHERE property_type = 'small_retail'")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    api_key = os.environ.get("RONE_API_KEY")
    if not api_key:
        raise SystemExit("RONE_API_KEY가 등록되지 않았습니다.")
    income_rows = fetch_rows(api_key, INCOME_TABLE_ID, "MM")
    vacancy_rows = fetch_rows(api_key, VACANCY_TABLE_ID, "QY")
    records = build_records(income_rows, vacancy_rows)
    if not records:
        raise SystemExit("오피스텔 수익률과 전국 공실률을 결합하지 못했습니다.")
    periods = sorted({row["period"] for row in records})
    if not args.dry_run:
        save_records(records)
    mode = "검증" if args.dry_run else "저장"
    print(f"R-ONE 임대 기준값 {mode} 완료: {len(records)}건, {periods[0]}~{periods[-1]}")


if __name__ == "__main__":
    main()