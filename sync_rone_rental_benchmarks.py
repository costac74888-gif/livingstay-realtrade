#!/usr/bin/env python3
"""R-ONE 소규모 상가 소득수익률·공실률의 공통 분기를 캐시한다."""

import argparse
import hashlib
import json
import os
from datetime import date
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from db import get_conn


API_URL = "https://www.reb.or.kr/r-one/openapi/SttsApiTblData.do"
INCOME_TABLE_ID = "A_2024_00392"
VACANCY_TABLE_ID = "A_2024_00256"
ITEM_ID = "100001"
PROVINCE_CODES = {
    "500001": ("00", "전국", "national"),
    "500002": ("11", "서울", "province"),
    "500003": ("26", "부산", "province"),
    "500004": ("27", "대구", "province"),
    "500005": ("28", "인천", "province"),
    "500006": ("29", "광주", "province"),
    "500007": ("30", "대전", "province"),
    "500008": ("31", "울산", "province"),
    "500009": ("36", "세종", "province"),
    "500010": ("41", "경기", "province"),
    "500011": ("42", "강원", "province"),
    "500012": ("43", "충북", "province"),
    "500013": ("44", "충남", "province"),
    "500014": ("45", "전북", "province"),
    "500015": ("46", "전남", "province"),
    "500016": ("47", "경북", "province"),
    "500017": ("48", "경남", "province"),
    "500018": ("50", "제주", "province"),
}


def fetch_rows(api_key, table_id):
    rows = []
    page = 1
    while True:
        query = urlencode({
            "KEY": api_key,
            "Type": "json",
            "pIndex": page,
            "pSize": 1000,
            "STATBL_ID": table_id,
            "DTACYCLE_CD": "QY",
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


def indexed_values(rows, expected_name):
    values = {}
    for row in rows:
        cls_id = str(row.get("CLS_ID") or "")
        if cls_id not in PROVINCE_CODES:
            continue
        if str(row.get("ITM_ID") or "") != ITEM_ID or row.get("ITM_NM") != expected_name:
            continue
        period = quarter_date(row.get("WRTTIME_IDTFR_ID"))
        value = float(row["DTA_VAL"])
        values[(period, cls_id)] = (value, row)
    return values


def build_records(income_rows, vacancy_rows, checked_at=None):
    incomes = indexed_values(income_rows, "소득수익률")
    vacancies = indexed_values(vacancy_rows, "공실률")
    records = []
    for key in sorted(set(incomes) & set(vacancies)):
        period, cls_id = key
        quarterly_income, income_row = incomes[key]
        vacancy_rate, vacancy_row = vacancies[key]
        if not 0 <= vacancy_rate <= 100:
            raise ValueError(f"공실률 범위 오류: {vacancy_rate}")
        region_code, region_name, region_level = PROVINCE_CODES[cls_id]
        raw = json.dumps(
            {"income": income_row, "vacancy": vacancy_row},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        records.append({
            "period": period,
            "region_code": region_code,
            "region_name": region_name,
            "region_level": region_level,
            "property_type": "small_retail",
            "property_type_name": "소규모 상가",
            "income_yield": quarterly_income * 4,
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
                    period, region_code, region_name, region_level,
                    property_type, property_type_name, income_yield, vacancy_rate,
                    source_stat_income_id, source_stat_vacancy_id,
                    source_item_income_id, source_item_vacancy_id,
                    source_checked_at, source_hash, collected_at
                ) VALUES (
                    %(period)s, %(region_code)s, %(region_name)s, %(region_level)s,
                    %(property_type)s, %(property_type_name)s, %(income_yield)s, %(vacancy_rate)s,
                    %(income_table)s, %(vacancy_table)s, %(item_id)s, %(item_id)s,
                    NOW(), %(source_hash)s, NOW()
                )
                ON CONFLICT (period, region_code, property_type) DO UPDATE SET
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
                "item_id": ITEM_ID,
            })
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
    income_rows = fetch_rows(api_key, INCOME_TABLE_ID)
    vacancy_rows = fetch_rows(api_key, VACANCY_TABLE_ID)
    records = build_records(income_rows, vacancy_rows)
    if not records:
        raise SystemExit("같은 분기·지역의 소득수익률과 공실률을 찾지 못했습니다.")
    periods = sorted({row["period"] for row in records})
    if not args.dry_run:
        save_records(records)
    mode = "검증" if args.dry_run else "저장"
    print(f"R-ONE 임대 기준값 {mode} 완료: {len(records)}건, {periods[0]}~{periods[-1]}")


if __name__ == "__main__":
    main()