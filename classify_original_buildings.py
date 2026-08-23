# -*- coding: utf-8 -*-
"""
classify_original_buildings.py — source='original' 미분류 건물 재분류 (멱등 스크립트)

건축물대장 API 판정이 불가능해 lodging_type=NULL로 남겨진 original 소스 건물들을
건물명·도로명 주소 기반 정규식으로 관광/일반으로 분류한다.

멱등 보장:
  - WHERE (lodging_type IS NULL OR lodging_type = '') 조건으로 이미 분류된 행은 건드리지 않음
  - 재실행해도 결과가 동일함

분류 규칙 (두 조건 중 하나라도 해당 → 관광, 그 외 → 일반):
  - building_name 에 콘도미니엄·콘도·호스텔·게스트하우스·호텔 (정규식, 대소문자 무관)
  - road_address  에 관광호텔·가족호텔·휴양콘도·호스텔

사용:
  python classify_original_buildings.py            # 실제 반영
  python classify_original_buildings.py --dry-run  # 변경 없이 건수만 출력
"""

import argparse
import os
import psycopg2
from stats_cache import mark_master_stats_invalidated

NAME_TOURIST = r'콘도미니엄|콘도|호스텔|게스트하우스|호텔'
ADDR_TOURIST = r'관광호텔|가족호텔|휴양콘도|호스텔'

CLASSIFY_SQL = f"""
SELECT id,
       building_name,
       road_address,
       CASE
         WHEN building_name ~* %(name_re)s
           OR road_address   ~* %(addr_re)s
         THEN '관광'
         ELSE '일반'
       END AS new_type
FROM master_buildings
WHERE source = 'original'
  AND (lodging_type IS NULL OR lodging_type = '')
ORDER BY id
"""

UPDATE_SQL = """
UPDATE master_buildings
SET
  lodging_type = CASE
    WHEN building_name ~* %(name_re)s
      OR road_address   ~* %(addr_re)s
    THEN '관광'
    ELSE '일반'
  END,
  lodging_type_detail = CASE
    WHEN building_name ~* %(name_re)s
      OR road_address   ~* %(addr_re)s
    THEN '건물명/주소 기반 관광숙박 분류 (API 판정 불가)'
    ELSE '건물명 기반 일반숙박 분류 (API 판정 불가)'
  END
WHERE source = 'original'
  AND (lodging_type IS NULL OR lodging_type = '')
"""


def main():
    parser = argparse.ArgumentParser(description="original 소스 미분류 건물 재분류")
    parser.add_argument("--dry-run", action="store_true",
                        help="DB 변경 없이 건수만 출력")
    args = parser.parse_args()

    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL 환경변수가 없습니다.")

    conn = psycopg2.connect(url)
    cur = conn.cursor()

    params = {"name_re": NAME_TOURIST, "addr_re": ADDR_TOURIST}

    cur.execute(CLASSIFY_SQL, params)
    rows = cur.fetchall()

    tourist = [r for r in rows if r[3] == "관광"]
    general = [r for r in rows if r[3] == "일반"]

    print(f"대상 건물: {len(rows)}건  (관광 {len(tourist)}건 / 일반 {len(general)}건)")

    if rows:
        print("\n[관광 분류 예정]")
        for rid, name, addr, _ in tourist:
            print(f"  id={rid}  {name}  |  {addr[:60]}")
        print("\n[일반 분류 예정]")
        for rid, name, addr, _ in general:
            print(f"  id={rid}  {name}  |  {addr[:60]}")

    if args.dry_run:
        print("\n  ※ dry-run 모드 — DB는 변경되지 않았습니다.")
        cur.close()
        conn.close()
        return

    cur.execute(UPDATE_SQL, params)
    updated = cur.rowcount
    conn.commit()
    if updated:
        try:
            mark_master_stats_invalidated("classify_original_buildings")
        except Exception as e:
            print(f"[classify_original_buildings] 통계 원본 캐시 표식 갱신 실패: {e}")
    print(f"\n✅ UPDATE 완료: {updated}건")

    # 검증: 분류 후 잔여 미분류 건수
    cur.execute(
        "SELECT count(*) FROM master_buildings "
        "WHERE source='original' AND (lodging_type IS NULL OR lodging_type='')"
    )
    remaining = cur.fetchone()[0]
    print(f"   잔여 미분류(original): {remaining}건")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
