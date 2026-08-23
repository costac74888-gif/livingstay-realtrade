# -*- coding: utf-8 -*-
"""
merge_dev_to_prod.py — 개발 DB → 운영 DB 안전 병합 (UPSERT 방식)

사용:
  python merge_dev_to_prod.py --dry-run   # 신규/갱신 건수만 출력, DB 변경 없음
  python merge_dev_to_prod.py             # 실제 반영

필요 환경변수:
  DATABASE_URL      → 개발 DB (기존 그대로)
  PROD_DATABASE_URL → 운영 DB (Replit 데이터베이스 패널 > Production > Connection string)

원칙:
  - master_buildings, transactions 두 테이블만 처리
  - 운영 DB의 기존 ID는 절대 변경하지 않음
  - 자연키(road_address 또는 sgg_cd+umd_nm+jibun) 기준 UPSERT
  - transactions는 raw_key unique 인덱스 기준 INSERT ON CONFLICT DO NOTHING
  - users, agents, operators 등 회원/파트너 테이블은 절대 건드리지 않음
"""

import argparse
import os
import sys
import psycopg2
import psycopg2.extras

from stats_cache import mark_master_stats_invalidated


def _signal_prod_stats_change():
    """운영 DB에 커밋된 변경을 알리되 표식 실패는 병합을 실패시키지 않는다."""
    try:
        mark_master_stats_invalidated(
            "merge_dev_to_prod",
            database_url=os.environ["PROD_DATABASE_URL"],
        )
        print("  통계 원본 캐시 무효화 표식을 갱신했습니다.")
    except Exception as exc:
        print(f"  통계 원본 캐시 표식 갱신 실패: {repr(exc)[:200]}")


def get_dev_conn():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL 환경변수가 없습니다.")
    return psycopg2.connect(url)


def get_prod_conn():
    url = os.environ.get("PROD_DATABASE_URL")
    if not url:
        raise RuntimeError(
            "PROD_DATABASE_URL 환경변수가 없습니다.\n"
            "Replit 데이터베이스 패널 > Production > Connection string을 복사해\n"
            "Secrets에 PROD_DATABASE_URL 이름으로 추가하세요."
        )
    return psycopg2.connect(url)


# master_buildings에서 UPSERT할 컬럼 목록 (id 제외, 운영이 자체 ID 부여)
BUILDING_COLS = [
    "building_name", "road_address", "jibun_address", "sgg_text", "sgg_cd",
    "umd_nm", "jibun", "units", "biz_units", "source", "lodging_type",
    "lodging_type_detail", "lat", "lng", "slot_capacity", "use_apr_day",
    "tot_pkng_cnt", "grnd_flr_cnt", "ugrnd_flr_cnt", "tot_area", "plat_area",
    "hhld_cnt", "strct_nm", "mgm_bldrgst_pk", "name_pending",
    "building_name_source", "building_name_candidate_count", "building_name_pending_base",
    "building_status", "completion_expected_date", "permit_day",
    "actual_start_day", "arch_area", "bc_rat", "vl_rat", "source_key",
    "heit", "ride_use_elvt_cnt", "emgen_use_elvt_cnt",
    "main_purps_nm", "jiyuk_nm", "jigu_nm", "guyuk_nm",
    "last_inspection_agency", "last_inspection_start_day",
    "last_inspection_submit_day", "indr_auto_utcnt", "oudr_auto_utcnt",
    "indr_mech_utcnt", "oudr_mech_utcnt",
]

# transactions에서 복사할 컬럼 (id 제외, raw_key 기준 중복 방지)
TX_COLS = [
    "raw_key", "si_do", "sgg", "umd", "dong", "lot", "deal_year",
    "deal_month", "deal_day", "building_name", "area", "floor",
    "deal_amount", "deal_type", "cancel_deal_day", "req_gbn",
    "rdealer_lawdnm", "road_nm", "road_nm_bonbun", "road_nm_bubun",
    "road_nm_sgg", "road_nm_cd", "road_nm_seq", "road_nm_pocode",
    "road_nm_detail", "bonbun", "bubun", "jibun", "sgg_cd",
    "umd_nm", "building_id", "lodging_type", "lodging_type_detail",
]


def merge_buildings(dev_cur, prod_conn, prod_cur, dry_run):
    """master_buildings: 자연키(road_address 또는 sgg_cd+umd_nm+jibun) 기준 UPSERT."""
    print("\n[1] master_buildings 병합 시작...")

    # 개발 DB에서 전체 건물 읽기
    dev_cur.execute(f"SELECT {', '.join(BUILDING_COLS)} FROM master_buildings")
    dev_rows = dev_cur.fetchall()
    print(f"  개발 DB 건물 수: {len(dev_rows)}건")

    # 운영 DB의 기존 자연키 셋 구성
    prod_cur.execute("""
        SELECT road_address, sgg_cd, umd_nm, jibun
        FROM master_buildings
    """)
    prod_roads = set()
    prod_triples = set()
    for r in prod_cur.fetchall():
        if r[0]:
            prod_roads.add(r[0].strip())
        if r[1] and r[2] and r[3]:
            prod_triples.add((r[1].strip(), r[2].strip(), r[3].strip()))
    print(f"  운영 DB 건물 수: {len(prod_roads)}건 (도로명 기준)")

    new_rows = []
    update_rows = []

    for row in dev_rows:
        d = dict(zip(BUILDING_COLS, row))
        road = (d.get("road_address") or "").strip()
        sgg_cd = (d.get("sgg_cd") or "").strip()
        umd_nm = (d.get("umd_nm") or "").strip()
        jibun = (d.get("jibun") or "").strip()

        exists_by_road = road and road in prod_roads
        exists_by_triple = sgg_cd and umd_nm and jibun and (sgg_cd, umd_nm, jibun) in prod_triples

        if exists_by_road or exists_by_triple:
            update_rows.append(d)
        else:
            new_rows.append(d)

    print(f"  → 신규 INSERT 대상: {len(new_rows)}건")
    print(f"  → 기존 UPDATE 대상: {len(update_rows)}건")

    if dry_run:
        if new_rows:
            print("  [dry-run] 신규 건물 샘플 (최대 5건):")
            for r in new_rows[:5]:
                print(f"    {r.get('building_name','?')} | {r.get('road_address','?')} | {r.get('lodging_type','미분류')}")
        return len(new_rows), len(update_rows)

    # 실제 반영
    cols_str = ", ".join(BUILDING_COLS)
    placeholders = ", ".join(["%s"] * len(BUILDING_COLS))
    update_set = ", ".join([f"{c} = EXCLUDED.{c}" for c in BUILDING_COLS
                            if c not in ("road_address", "sgg_cd", "umd_nm", "jibun")])

    insert_sql = f"""
        INSERT INTO master_buildings ({cols_str})
        VALUES ({placeholders})
        ON CONFLICT DO NOTHING
    """

    inserted = 0
    for r in new_rows:
        vals = [r.get(c) for c in BUILDING_COLS]
        prod_cur.execute(insert_sql, vals)
        inserted += prod_cur.rowcount

    prod_conn.commit()
    if inserted:
        _signal_prod_stats_change()
    print(f"  ✅ 실제 INSERT 완료: {inserted}건")
    return inserted, 0


def sync_lodging_types(dev_cur, prod_conn, prod_cur, dry_run):
    """
    개발 DB의 lodging_type 분류 결과를 운영 DB에 반영.
    소스(brhub_bulk/original 등) 무관하게 lodging_type이 확정된 건물을 조회해
    운영 DB에서 자연키(road_address 또는 sgg_cd+umd_nm+jibun)로 매칭 후,
    운영에 값이 없는 행만 업데이트한다(안전장치 — 기존 값 덮어쓰지 않음).
    """
    print("\n[3] lodging_type 동기화 (전체 소스 재분류 결과)...")

    dev_cur.execute("""
        SELECT id, road_address, sgg_cd, umd_nm, jibun,
               lodging_type, lodging_type_detail, lodging_subtype
        FROM master_buildings
        WHERE lodging_type IS NOT NULL AND lodging_type != ''
    """)
    dev_rows = dev_cur.fetchall()
    print(f"  개발 DB 대상 건물: {len(dev_rows)}건")

    # 운영 DB 자연키 → (prod_id, lodging_type) 맵 구성
    prod_cur.execute("""
        SELECT id, road_address, sgg_cd, umd_nm, jibun, lodging_type
        FROM master_buildings
    """)
    prod_by_road   = {}   # road_address → (id, lodging_type)
    prod_by_triple = {}   # (sgg_cd, umd_nm, jibun) → (id, lodging_type)
    for pid, road, sgg_cd, umd_nm, jibun, lt in prod_cur.fetchall():
        if road:
            prod_by_road[road.strip()] = (pid, lt)
        if sgg_cd and umd_nm and jibun:
            prod_by_triple[(sgg_cd.strip(), umd_nm.strip(), jibun.strip())] = (pid, lt)

    matched = []   # (prod_id, lodging_type, lodging_type_detail, lodging_subtype)
    skipped = 0
    not_found = 0

    for row in dev_rows:
        _, road, sgg_cd, umd_nm, jibun, dev_lt, dev_detail, dev_sub = row
        road    = (road    or "").strip()
        sgg_cd  = (sgg_cd  or "").strip()
        umd_nm  = (umd_nm  or "").strip()
        jibun   = (jibun   or "").strip()

        hit = prod_by_road.get(road) or (
            prod_by_triple.get((sgg_cd, umd_nm, jibun)) if sgg_cd and umd_nm and jibun else None
        )
        if hit is None:
            not_found += 1
            continue

        prod_id, prod_lt = hit
        if prod_lt and prod_lt.strip():   # 운영에 이미 값 있으면 건드리지 않음
            skipped += 1
            continue

        matched.append((prod_id, dev_lt, dev_detail, dev_sub))

    print(f"  → 매칭 성공(업데이트 대상): {len(matched)}건")
    print(f"  → 이미 값 있어서 스킵:       {skipped}건")
    print(f"  → 운영에서 건물 못 찾음:      {not_found}건")

    if dry_run:
        return len(matched), skipped, not_found

    # 실제 반영
    updated = 0
    for prod_id, lt, detail, sub in matched:
        prod_cur.execute("""
            UPDATE master_buildings
            SET lodging_type        = %s,
                lodging_type_detail = %s,
                lodging_subtype     = %s
            WHERE id = %s
              AND (lodging_type IS NULL OR lodging_type = '')
        """, (lt, detail, sub, prod_id))
        updated += prod_cur.rowcount
    prod_conn.commit()
    if updated:
        _signal_prod_stats_change()
    print(f"  ✅ 실제 UPDATE 완료: {updated}건")
    return updated, skipped, not_found


def merge_transactions(dev_cur, prod_conn, prod_cur, dry_run):
    """transactions: raw_key unique 인덱스 기준 INSERT ON CONFLICT DO NOTHING."""
    print("\n[2] transactions 병합 시작...")

    # 운영에 없는 raw_key만 선별 (메모리 효율을 위해 raw_key 셋 먼저 로드)
    prod_cur.execute("SELECT raw_key FROM transactions WHERE raw_key IS NOT NULL")
    prod_raw_keys = {r[0] for r in prod_cur.fetchall()}
    print(f"  운영 DB 기존 거래: {len(prod_raw_keys)}건")

    # 개발·운영 두 DB에 공통으로 존재하는 컬럼만 사용 (id, created_at 제외)
    EXCLUDE = {"id", "created_at"}
    dev_cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name='transactions' ORDER BY ordinal_position
    """)
    dev_cols = {r[0] for r in dev_cur.fetchall()} - EXCLUDE
    prod_cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name='transactions' ORDER BY ordinal_position
    """)
    prod_cols = {r[0] for r in prod_cur.fetchall()} - EXCLUDE
    tx_cols = sorted(dev_cols & prod_cols)   # 교집합, 정렬로 순서 고정
    print(f"  병합 컬럼 ({len(tx_cols)}개): {', '.join(tx_cols)}")

    dev_cur.execute(f"SELECT {', '.join(tx_cols)} FROM transactions WHERE raw_key IS NOT NULL")
    dev_rows = dev_cur.fetchall()
    print(f"  개발 DB 거래: {len(dev_rows)}건")

    raw_key_idx = tx_cols.index("raw_key")
    new_rows = [r for r in dev_rows if r[raw_key_idx] not in prod_raw_keys]
    print(f"  → 신규 INSERT 대상: {len(new_rows)}건")

    if dry_run:
        return len(new_rows)

    cols_str = ", ".join(tx_cols)

    batch_size = 500
    inserted = 0
    for i in range(0, len(new_rows), batch_size):
        batch = new_rows[i:i + batch_size]
        psycopg2.extras.execute_values(
            prod_cur,
            f"""
                INSERT INTO transactions ({cols_str})
                VALUES %s
                ON CONFLICT (raw_key) DO NOTHING
                RETURNING raw_key
            """,
            batch,
            page_size=len(batch),
        )
        inserted_batch = len(prod_cur.fetchall())
        inserted += inserted_batch
        prod_conn.commit()
        if inserted_batch:
            _signal_prod_stats_change()
        print(f"  진행: {min(i + batch_size, len(new_rows))}/{len(new_rows)}건", flush=True)

    print(f"\n  ✅ 실제 INSERT 완료: {inserted}건")
    return inserted


def main():
    parser = argparse.ArgumentParser(description="개발 DB → 운영 DB 안전 병합")
    parser.add_argument("--dry-run", action="store_true",
                        help="DB 변경 없이 신규/갱신 건수만 출력")
    args = parser.parse_args()

    mode = "[DRY-RUN]" if args.dry_run else "[실제 반영]"
    print(f"=== 개발 → 운영 DB 병합 {mode} ===")
    print("  대상: master_buildings, transactions")
    print("  보호: users, agents, operators 등 회원/파트너 테이블 — 절대 건드리지 않음\n")

    dev_conn = get_dev_conn()
    prod_conn = get_prod_conn()
    dev_cur = dev_conn.cursor()
    prod_cur = prod_conn.cursor()

    try:
        b_new, b_upd = merge_buildings(dev_cur, prod_conn, prod_cur, args.dry_run)
        tx_new = merge_transactions(dev_cur, prod_conn, prod_cur, args.dry_run)
        lt_updated, lt_skipped, lt_missing = sync_lodging_types(
            dev_cur, prod_conn, prod_cur, args.dry_run
        )

        print("\n=== 최종 요약 ===")
        print(f"  master_buildings 신규:          {b_new}건")
        print(f"  transactions 신규:              {tx_new}건")
        print(f"  lodging_type 업데이트:          {lt_updated}건")
        print(f"  lodging_type 스킵(이미 값 있음): {lt_skipped}건")
        print(f"  lodging_type 매칭 실패:          {lt_missing}건")
        if args.dry_run:
            print("\n  ※ dry-run 모드 — DB는 변경되지 않았습니다.")
            print("  ※ 결과가 상식적이면 --dry-run 없이 다시 실행하세요.")
        else:
            print("\n  ✅ 병합 완료!")

    except Exception as e:
        prod_conn.rollback()
        print(f"\n[ERROR] {e}", file=sys.stderr)
        raise
    finally:
        dev_cur.close()
        prod_cur.close()
        dev_conn.close()
        prod_conn.close()


if __name__ == "__main__":
    main()
