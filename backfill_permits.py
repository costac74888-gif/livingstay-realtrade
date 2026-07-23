# -*- coding: utf-8 -*-
"""
backfill_permits.py — 이미 저장된 permit_pipeline 건물 중 건물명이 "-"이거나
면적 정보(tot_area)가 비어 있는 건만 골라, 해당 법정동만 인허가 API로 다시
조회해서 UPDATE로 보강하는 일회성 배치.

- 신규 INSERT 없음, 전국 재수집 아님 (대상 건물이 속한 법정동만 재조회)
- sync_permits.py의 _fetch_page() / _jibun_from_bunji() / FIELD_MAP 재사용

사용:
  python backfill_permits.py --dry-run   # 먼저 확인 (DB 안 씀)
  python backfill_permits.py             # 실제 보강
"""

import argparse
import os
import re
import time

from db import get_conn
from address_utils import normalize_umd_nm
from sync_permits import _fetch_page, _jibun_from_bunji, _load_codes, KEY_ENV


def _parse_bun_ji(jibun):
    """jibun('321-19' 또는 '321') → (bun, ji) 정수 튜플. 파싱 불가면 None."""
    if not jibun:
        return None
    m = re.match(r"^\s*(\d+)(?:-(\d+))?\s*$", str(jibun))
    if not m:
        return None
    return int(m.group(1)), int(m.group(2) or 0)


def _bun_ji_from_item(it):
    """API 응답 항목의 bun/ji → 정수 튜플. 없거나 비정상이면 None."""
    try:
        b = int(str(it.get("bun") or "0"))
        j = int(str(it.get("ji") or "0"))
    except ValueError:
        return None
    if b <= 0:
        return None
    return b, j


def _find_dong_codes(dongs, sgg_cd, umd_nm):
    """bjdong_codes.json에서 (sgg_cd, umd_nm)에 해당하는 법정동코드 후보들."""
    key = normalize_umd_nm(umd_nm or "")
    out = []
    for code, dong_name in dongs:
        if code[:5] != sgg_cd:
            continue
        tail = dong_name.split()[-1] if dong_name else ""
        if normalize_umd_nm(tail) == key:
            out.append(code[5:])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="DB에 안 쓰고 보강 예정 내역만 출력")
    ap.add_argument("--sleep", type=float, default=1.5)
    args = ap.parse_args()

    key = os.environ.get(KEY_ENV)
    if not key:
        raise RuntimeError(f"환경변수 {KEY_ENV} 가 설정되어 있지 않습니다.")

    sgg_map, dongs = _load_codes()
    conn = get_conn()
    cur = conn.cursor()

    # 1) 보강 대상 조회
    cur.execute("""
        SELECT id, building_name, road_address, jibun_address, sgg_cd, umd_nm, jibun
        FROM master_buildings
        WHERE source = 'permit_pipeline'
          AND (building_name = '-' OR tot_area IS NULL)
        ORDER BY id
    """)
    targets = cur.fetchall()
    print(f"[대상] 보강 필요 건물 {len(targets)}건")
    if not targets:
        return

    # 2) (sgg_cd, bjdongCd) 단위로 묶어 중복 호출 최소화
    groups = {}      # (sgg_cd, bjd_cd) -> [target row, ...]
    no_dong = []     # 법정동코드를 못 찾은 대상
    for t in targets:
        if not t["sgg_cd"] or not t["umd_nm"]:
            no_dong.append(t)
            continue
        bjds = _find_dong_codes(dongs, t["sgg_cd"], t["umd_nm"])
        if not bjds:
            no_dong.append(t)
            continue
        for bjd in bjds:
            groups.setdefault((t["sgg_cd"], bjd), []).append(t)
    print(f"[그룹] 재조회할 법정동 {len(groups)}곳")

    updated_ids = set()
    calls = 0

    # 3) 법정동별 재조회 (페이지네이션 + 재시도는 sync_permits와 동일 정책)
    for (sgg_cd, bjd_cd), rows in groups.items():
        pending = [t for t in rows if t["id"] not in updated_ids]
        if not pending:
            continue
        # 대상 건물의 (bun, ji) 키 맵
        want = {}
        for t in pending:
            bj = _parse_bun_ji(t["jibun"])
            if bj is None:
                # jibun이 없으면 지번주소/도로명주소 끝의 번지 파싱 폴백
                for addr in (t["jibun_address"], t["road_address"]):
                    if not addr:
                        continue
                    m = re.search(r"(\d+)(?:-(\d+))?\s*(?:번지)?\s*$", str(addr))
                    if m:
                        bj = (int(m.group(1)), int(m.group(2) or 0))
                        break
            if bj is not None:
                want.setdefault(bj, []).append(t)
            else:
                no_dong.append(t)

        if not want:
            continue

        page = 1
        while True:
            items = None
            for attempt, wait_sec in enumerate([15, 30, 60], start=1):
                try:
                    items = _fetch_page(key, sgg_cd, bjd_cd, page)
                    break
                except Exception as e:
                    print(f"  [{sgg_cd}/{bjd_cd}] p{page} 오류(시도 {attempt}/3): "
                          f"{repr(e)[:160]} — {wait_sec}초 후 재시도")
                    time.sleep(wait_sec)
            if items is None:
                print(f"  [{sgg_cd}/{bjd_cd}] 3회 재시도 모두 실패 — 이 법정동 건너뜀")
                break
            calls += 1

            for it in items:
                bj = _bun_ji_from_item(it)
                if bj is None or bj not in want:
                    continue
                for t in want[bj]:
                    if t["id"] in updated_ids:
                        continue
                    bld_nm = (it.get("bldNm") or "").strip()
                    # 건물명: 실제 bldNm이 새로 확인되면 교체, 아니면 기존 값 유지
                    #         ("-"였던 건물도 bldNm이 없으면 도로명주소로 대체)
                    if bld_nm:
                        new_name = bld_nm
                    elif t["building_name"] and t["building_name"] != "-":
                        new_name = t["building_name"]
                    else:
                        new_name = t["road_address"] or t["jibun_address"] or t["building_name"]

                    if args.dry_run:
                        print(f"  [보강예정] id={t['id']} | {t['building_name']} → {new_name} | "
                              f"연면적={it.get('totArea')} 대지={it.get('platArea')} "
                              f"건축={it.get('archArea')} 건폐율={it.get('bcRat')} "
                              f"용적률={it.get('vlRat')} 세대={it.get('hhldCnt')} "
                              f"주차={it.get('totPkngCnt')}")
                    else:
                        cur.execute("""
                            UPDATE master_buildings
                            SET building_name = %s,
                                tot_area = %s, plat_area = %s, arch_area = %s,
                                bc_rat = %s, vl_rat = %s,
                                hhld_cnt = %s, tot_pkng_cnt = %s
                            WHERE id = %s
                        """, (new_name,
                              it.get("totArea") or None,
                              it.get("platArea") or None,
                              it.get("archArea") or None,
                              it.get("bcRat") or None,
                              it.get("vlRat") or None,
                              it.get("hhldCnt") or None,
                              it.get("totPkngCnt") or None,
                              t["id"]))
                        conn.commit()
                        print(f"  [보강완료] id={t['id']} | {new_name}")
                    updated_ids.add(t["id"])

            if len(items) < 10:  # sync_permits.NUM_ROWS와 동일 — 마지막 페이지
                break
            page += 1
            time.sleep(args.sleep)
        time.sleep(args.sleep)

    # 5) 결과 요약
    matched = len(updated_ids)
    unmatched = [t for t in targets if t["id"] not in updated_ids]
    print(f"\n[요약] 총 대상 {len(targets)}건 | "
          f"{'보강 예정' if args.dry_run else '보강 완료'} {matched}건 | "
          f"미매칭 {len(unmatched)}건 | API 호출 {calls}회")
    if unmatched:
        print("[수동 확인 필요 목록]")
        for t in unmatched:
            print(f"  - id={t['id']} | {t['building_name']} | sgg_cd={t['sgg_cd']} "
                  f"umd_nm={t['umd_nm']} jibun={t['jibun']} | {t['road_address'] or t['jibun_address'] or ''}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
