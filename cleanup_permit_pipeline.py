#!/usr/bin/env python3
"""
준공전(permit_pipeline) 건물 정리 스크립트
=============================================
이미 수집된 permit_pipeline 건물 중 아래 조건에 해당하는 건물을 삭제합니다.

삭제 조건 (OR):
  1. 허가일(permit_day)이 현재 기준 5년 이상 경과 — 오래된 오픈 퍼밋
  2. 동일 (sgg_cd, jibun)으로 source != 'permit_pipeline'인 완공 건물이 존재
  3. lodging_type_detail에 오염 키워드 포함
     ("일반숙박", "여관", "모텔", "고시원", "공중위생")

사용법:
  python cleanup_permit_pipeline.py            # dry-run (실제 삭제 없음)
  python cleanup_permit_pipeline.py --execute  # 실제 삭제 실행
  python cleanup_permit_pipeline.py --list     # 삭제 대상 목록 출력 (CSV)
"""

import argparse
import csv
import os
import sys
from datetime import date, timedelta

import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ.get("DATABASE_URL", "")

CUTOFF_YEARS = 5
CUTOFF_DATE = date.today() - timedelta(days=365 * CUTOFF_YEARS)

CONTAMINATED_KEYWORDS = ("일반숙박", "여관", "모텔", "고시원", "공중위생")


def get_conn():
    if not DATABASE_URL:
        print("[오류] DATABASE_URL 환경변수가 설정되지 않았습니다.", file=sys.stderr)
        sys.exit(1)
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)


def fetch_targets(cur) -> list[dict]:
    """삭제 대상 건물 목록과 삭제 사유를 반환."""
    # 1) 허가일 5년 초과
    cur.execute("""
        SELECT id, building_name, sgg_cd, jibun, permit_day, building_status,
               lodging_type_detail, sgg_text
        FROM master_buildings
        WHERE building_status IN ('허가', '착공')
          AND source = 'permit_pipeline'
          AND permit_day IS NOT NULL
          AND to_date(permit_day, 'YYYYMMDD') < %s::date
        ORDER BY to_date(permit_day, 'YYYYMMDD')
    """, (CUTOFF_DATE.isoformat(),))
    old_permit = {row["id"]: dict(row) | {"reason": f"허가일({row['permit_day']}) 5년 초과"} for row in cur.fetchall()}

    # 2) 완공 건물 중복 (sgg_cd + jibun 일치)
    cur.execute("""
        SELECT pp.id, pp.building_name, pp.sgg_cd, pp.jibun, pp.permit_day,
               pp.building_status, pp.lodging_type_detail, pp.sgg_text
        FROM master_buildings pp
        WHERE pp.building_status IN ('허가', '착공')
          AND pp.source = 'permit_pipeline'
          AND EXISTS (
              SELECT 1 FROM master_buildings comp
              WHERE comp.source != 'permit_pipeline'
                AND comp.sgg_cd = pp.sgg_cd
                AND comp.jibun = pp.jibun
          )
    """)
    dup_completed = {row["id"]: dict(row) | {"reason": "완공 건물 중복(sgg_cd+jibun)"} for row in cur.fetchall()}

    # 3) 오염 키워드
    cur.execute("""
        SELECT id, building_name, sgg_cd, jibun, permit_day, building_status,
               lodging_type_detail, sgg_text
        FROM master_buildings
        WHERE building_status IN ('허가', '착공')
          AND source = 'permit_pipeline'
          AND lodging_type_detail ILIKE ANY(%s)
        ORDER BY id
    """, ([f"%{kw}%" for kw in CONTAMINATED_KEYWORDS],))
    contaminated = {row["id"]: dict(row) | {"reason": f"오염 용도({row['lodging_type_detail']})"} for row in cur.fetchall()}

    # 병합 (id 기준 dedup, 사유 누적)
    merged: dict[int, dict] = {}
    for source_dict in (old_permit, dup_completed, contaminated):
        for bid, row in source_dict.items():
            if bid in merged:
                merged[bid]["reason"] += " / " + row["reason"]
            else:
                merged[bid] = row

    return list(merged.values())


def print_summary(targets: list[dict], total_pipeline: int):
    reasons = {}
    for t in targets:
        for r in t["reason"].split(" / "):
            reasons[r.split("(")[0].strip()] = reasons.get(r.split("(")[0].strip(), 0) + 1

    print(f"\n{'='*60}")
    print(f"permit_pipeline 건물 전체 (허가/착공): {total_pipeline}건")
    print(f"삭제 대상:                             {len(targets)}건")
    print(f"삭제 후 잔존 예상:                     {total_pipeline - len(targets)}건")
    print(f"{'─'*60}")
    print("삭제 사유별 분류:")
    for reason, cnt in sorted(reasons.items(), key=lambda x: -x[1]):
        print(f"  {reason}: {cnt}건")
    print(f"{'='*60}\n")


def list_targets_csv(targets: list[dict]):
    writer = csv.DictWriter(sys.stdout, fieldnames=[
        "id", "building_name", "sgg_text", "sgg_cd", "jibun",
        "permit_day", "building_status", "lodging_type_detail", "reason"
    ])
    writer.writeheader()
    for t in targets:
        writer.writerow({k: t.get(k, "") for k in writer.fieldnames})


def main():
    parser = argparse.ArgumentParser(description="permit_pipeline 건물 정리")
    parser.add_argument("--execute", action="store_true",
                        help="실제 삭제를 실행합니다 (기본값: dry-run)")
    parser.add_argument("--list", action="store_true",
                        help="삭제 대상 건물 목록을 CSV로 출력합니다")
    args = parser.parse_args()

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) AS cnt
                FROM master_buildings
                WHERE building_status IN ('허가', '착공') AND source = 'permit_pipeline'
            """)
            total = cur.fetchone()["cnt"]

            targets = fetch_targets(cur)

        if args.list:
            list_targets_csv(targets)
            return

        print_summary(targets, total)

        if not targets:
            print("정리할 건물이 없습니다.")
            return

        if not args.execute:
            print("[DRY-RUN] 실제 삭제를 수행하지 않습니다.")
            print("  실행하려면:  python cleanup_permit_pipeline.py --execute")
            return

        # 실제 삭제
        ids = [t["id"] for t in targets]
        print(f"삭제 실행 중 … (총 {len(ids)}건)")
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM master_buildings WHERE id = ANY(%s)",
                (ids,)
            )
            deleted = cur.rowcount
        conn.commit()
        print(f"✓ {deleted}건 삭제 완료.")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
