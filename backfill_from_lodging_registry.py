"""
backfill_from_lodging_registry.py

영업신고(lodging_registry) 기반으로 master_buildings에 누락된 건물을 등록한다.
discover_new_buildings.py(실거래가 기반)에서 buildingUse='오피스텔'로 분류되어
누락된 생숙(블루오션레지던스4 등)을 포착하는 것이 주목적.

사용법:
    # 전체 실행 (처음)
    python backfill_from_lodging_registry.py

    # 특정 시군구만 테스트 (예: 인천 중구 28110)
    python backfill_from_lodging_registry.py --sgg 28110

    # dry-run (실제 등록 없이 후보만 출력)
    python backfill_from_lodging_registry.py --dry-run
"""

import os
import argparse
import time

from db import get_conn, init_db
from address_utils import road_to_jibun, BjdongMap, parse_jibun, normalize_umd_nm
from building_registry import classify_lodging_type
from stats_cache import mark_master_stats_invalidated

BJDONG_CODE_CSV = os.environ.get("BJDONG_CODE_CSV", "법정동코드 전체자료.csv")
REQUEST_SLEEP = 0.3  # 건축HUB API 쿼터 보호

LEGACY_SGG_TEXT_MAP = {
    # 2026년 제물포구·영종구 분리 전 인천광역시 중구 코드.
    # 과거 중구 주소와 분리 후 두 구 주소를 모두 같은 실행 범위로 본다.
    "28110": (
        "인천광역시 중구",
        "인천광역시 제물포구",
        "인천광역시 영종구",
    ),
}

HYGIENE_TYPE_MAP = {
    "생활숙박시설":        ("생숙",      "생활숙박시설"),
    "관광숙박업":          ("분양형호텔", "관광숙박업"),
    "일반숙박업":          ("일반",      "일반숙박업"),
    "외국인관광도시민박업": ("생숙",      "외국인관광도시민박업"),
}


def hygiene_to_lodging_type(hygiene_type: str):
    """영업신고 업종명 → (lodging_type, lodging_type_detail)"""
    for key, val in HYGIENE_TYPE_MAP.items():
        if key in (hygiene_type or ""):
            return val
    return ("기타", hygiene_type or "")


def run(sgg_filter=None, dry_run=False):
    init_db()
    bjdong = BjdongMap(BJDONG_CODE_CSV)
    conn = get_conn()
    cur = conn.cursor()

    # ── 1. 후보 추출 ────────────────────────────────────────
    # sgg_filter가 있으면 BjdongMap으로 시군구 텍스트 변환 후 SQL에서 먼저 필터
    addr_filters = []
    addr_params = []
    if sgg_filter:
        for sgg_cd_f in sgg_filter:
            sgg_text_f = bjdong.sgg_text(sgg_cd_f)
            if not sgg_text_f:
                # 하위 읍면동이 있는 시군구는 sgg_text()의 leaf 목록에서
                # 제외되므로, 전체 시군구 행에서 상위 텍스트를 보완한다.
                sgg_text_f = next(
                    (name for cd, name in bjdong._all_sgg_rows if cd == sgg_cd_f),
                    None,
                )
            sgg_texts = [sgg_text_f] if sgg_text_f else list(
                LEGACY_SGG_TEXT_MAP.get(sgg_cd_f, ())
            )
            if sgg_texts:
                prefix_filters = []
                for sgg_text in sgg_texts:
                    prefix_filters.append(
                        "(lr.road_address LIKE %s OR lr.jibun_address LIKE %s)"
                    )
                    addr_params += [f"{sgg_text}%", f"{sgg_text}%"]
                addr_filters.append(
                    "(" + " OR ".join(prefix_filters) + ")"
                )
            else:
                raise ValueError(f"시군구 코드에 해당하는 주소명을 찾을 수 없습니다: {sgg_cd_f}")

    where_extra = ("AND (" + " OR ".join(addr_filters) + ")") if addr_filters else ""

    query = f"""
        SELECT lr.id, lr.biz_name, lr.road_address, lr.jibun_address,
               lr.road_norm, lr.jibun_norm, lr.hygiene_type,
               lr.room_count, lr.phone
        FROM lodging_registry lr
        WHERE lr.biz_status_name IN ('영업/정상', '영업중', '영업')
          AND lr.applied_building_id IS NULL
          AND lr.dismissed_at IS NULL
          AND lr.hygiene_type IS NOT NULL
          AND lr.hygiene_type != ''
          {where_extra}
    """
    cur.execute(query, addr_params)
    candidates = cur.fetchall()
    print(f"[후보] 총 {len(candidates)}건")

    registered = skipped = failed = 0

    for lr in candidates:
        road_addr = lr["road_address"] or ""
        jibun_addr = lr["jibun_address"] or ""
        biz_name = lr["biz_name"]
        lr_id = lr["id"]

        # ── 3. 지번 변환 ──────────────────────────────────────
        target_addr = road_addr or jibun_addr
        if not target_addr:
            failed += 1
            print(f"  [스킵] {biz_name} — 주소 없음")
            continue

        juso = road_to_jibun(target_addr)
        if not juso:
            failed += 1
            print(f"  [실패] {biz_name} — 주소 변환 실패: {target_addr}")
            continue

        si_do  = juso.get("siNm", "")
        sgg_nm = juso.get("sggNm", "")
        umd_nm = normalize_umd_nm(
            juso.get("emdNm", "") + juso.get("liNm", "")
        )
        bun    = juso.get("lnbrMnnm", "0")
        ji     = juso.get("lnbrSlno", "0")
        jibun_str = f"{bun}-{ji}" if ji not in ("0", "", None) else bun

        sgg_cd = bjdong.find_sgg_cd(si_do, sgg_nm)
        if not sgg_cd:
            failed += 1
            print(f"  [실패] {biz_name} — SGG 코드 없음: {si_do} {sgg_nm}")
            continue

        # ── 4. master_buildings 중복 확인 ──────────────────────
        cur.execute("""
            SELECT id FROM master_buildings
            WHERE sgg_cd=%s AND umd_nm=%s AND jibun=%s
        """, [sgg_cd, umd_nm, jibun_str])
        dup = cur.fetchone()
        if dup:
            if not dry_run:
                cur.execute(
                    "UPDATE lodging_registry SET applied_building_id=%s WHERE id=%s",
                    [dup["id"], lr_id]
                )
                conn.commit()
            skipped += 1
            print(f"  [중복] {biz_name} → #{dup['id']}")
            continue

        # ── 5. 건축HUB 표제부 조회 → lodging_type 판정 ─────────
        time.sleep(REQUEST_SLEEP)
        sgg_text = f"{si_do} {sgg_nm}".strip()
        plat_gb, bun2, ji2 = parse_jibun(jibun_str)

        try:
            bjdong_cd = bjdong.find_bjdong_cd(sgg_cd, umd_nm)
            if not bjdong_cd:
                raise ValueError(f"법정동 코드 없음: {sgg_cd} {umd_nm}")
            label, detail, subtype, title, reason = classify_lodging_type(
                sgg_cd, bjdong_cd, plat_gb, bun2, ji2
            )
            if not label:
                raise ValueError(f"건축HUB 판정불가: {reason}")
            ho_cnt = (title or {}).get("ho_cnt") or lr["room_count"] or 0
        except Exception as e:
            # 건축HUB 실패 시 영업신고 hygiene_type으로 fallback
            label, detail = hygiene_to_lodging_type(lr["hygiene_type"])
            subtype = ""
            ho_cnt = lr["room_count"] or 0
            print(f"  [건축HUB실패→fallback] {biz_name}: {e}")

        if dry_run:
            print(f"  [DRY] {biz_name} | {sgg_text} {umd_nm} {jibun_str} | {label}")
            continue

        # ── 6. master_buildings 등록 ───────────────────────────
        cur.execute("""
            INSERT INTO master_buildings
                (building_name, sgg_cd, sgg_text, umd_nm, jibun,
                 road_address, lodging_type, lodging_type_detail,
                 lodging_subtype, total_ho_cnt, match_source, name_pending)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'lodging_registry',TRUE)
            RETURNING id
        """, [
            biz_name, sgg_cd, sgg_text, umd_nm, jibun_str,
            road_addr, label, detail, subtype, ho_cnt
        ])
        mb_id = cur.fetchone()["id"]

        cur.execute(
            "UPDATE lodging_registry SET applied_building_id=%s WHERE id=%s",
            [mb_id, lr_id]
        )
        conn.commit()
        mark_master_stats_invalidated()
        registered += 1
        print(f"  [등록] {biz_name} → #{mb_id} ({label})")

    cur.close()
    conn.close()
    print(f"\n완료 — 신규등록: {registered} / 기존매핑: {skipped} / 실패: {failed}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sgg", help="특정 시군구 코드만 실행 (예: 28110)")
    parser.add_argument("--dry-run", action="store_true",
                        help="실제 등록 없이 후보만 출력")
    args = parser.parse_args()
    sgg_filter = {args.sgg} if args.sgg else None
    run(sgg_filter=sgg_filter, dry_run=args.dry_run)