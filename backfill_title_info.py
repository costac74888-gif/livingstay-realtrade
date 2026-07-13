# -*- coding: utf-8 -*-
"""
backfill_title_info.py — 건축물대장 표제부(getBrTitleInfo) 값을
                         master_buildings 의 표제부 컬럼에 채운다.

채우는 컬럼 (건물 상세 화면 "건축정보" 섹션에 표시):
  use_apr_day   ← useAprDay   (사용승인일/준공, YYYY-MM-DD 로 포맷 저장)
  tot_pkng_cnt  ← totPkngCnt  (총주차대수)
  grnd_flr_cnt  ← grndFlrCnt  (지상층수)
  ugrnd_flr_cnt ← ugrndFlrCnt (지하층수)
  tot_area      ← totArea     (연면적 ㎡)
  plat_area     ← platArea    (대지면적 ㎡)
  hhld_cnt      ← hhldCnt     (세대수)
  strct_nm      ← strctCdNm   (구조)
  title_backfilled_at ← NOW() (백필 시각)

주소 → API 파라미터 변환은 기존 파이프라인과 동일:
  sigunguCd = master_buildings.sgg_cd
  bjdongCd  = BjdongMap.find_bjdong_cd(sgg_cd, umd_nm)
  platGb/bun/ji = parse_jibun(jibun)
표제부 API 호출은 building_registry._fetch_title_rows 재사용(BLD_SERVICE_KEY).

사용법
------------------------------------------------------------
python backfill_title_info.py --limit 5          # 앞 5건만 (샘플 확인)
python backfill_title_info.py --ids 2654,2655    # 특정 id만
python backfill_title_info.py                    # 미백필분 전체
python backfill_title_info.py --all              # 이미 채운 것도 재조회
"""

import os
import sys
import time
import argparse

from db import get_conn, init_db
from address_utils import BjdongMap, parse_jibun
from building_registry import _fetch_title_rows, _hocnt

BJDONG_CSV = os.environ.get("BJDONG_CODE_CSV", "법정동코드_전체자료.zip")


def _to_int(v):
    if v is None or str(v).strip() == "":
        return None
    try:
        return int(float(str(v).replace(",", "").strip()))
    except (ValueError, TypeError):
        return None


def _to_float(v):
    if v is None or str(v).strip() == "":
        return None
    try:
        return float(str(v).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def _fmt_date(v):
    """'20231130' → '2023-11-30'. 형식이 다르면 원문 그대로(공백은 None)."""
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    if len(s) == 8 and s.isdigit():
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    return s


def _pick_representative(rows):
    """지번 내 여러 동 중 대표 동: '숙박' 주용도 우선, 그중 호수(hoCnt) 최대."""
    if not rows:
        return None
    lodging = [r for r in rows if "숙박" in (r.get("mainPurpsCdNm", "") or "")]
    pool = lodging if lodging else rows
    return max(pool, key=_hocnt)


def _extract(rep):
    return {
        "use_apr_day": _fmt_date(rep.get("useAprDay")),
        "tot_pkng_cnt": _to_int(rep.get("totPkngCnt")),
        "grnd_flr_cnt": _to_int(rep.get("grndFlrCnt")),
        "ugrnd_flr_cnt": _to_int(rep.get("ugrndFlrCnt")),
        "tot_area": _to_float(rep.get("totArea")),
        "plat_area": _to_float(rep.get("platArea")),
        "hhld_cnt": _to_int(rep.get("hhldCnt")),
        "strct_nm": (rep.get("strctCdNm") or "").strip() or None,
    }


def run(limit=None, ids=None, only_missing=True, sleep=0.2):
    init_db()
    bjdong = BjdongMap(BJDONG_CSV)
    conn = get_conn()
    cur = conn.cursor()

    where = ["sgg_cd IS NOT NULL", "umd_nm IS NOT NULL", "jibun IS NOT NULL"]
    params = []
    if ids:
        where.append("id = ANY(%s)")
        params.append(ids)
    elif only_missing:
        where.append("title_backfilled_at IS NULL")
    sql = f"SELECT id, building_name, sgg_cd, umd_nm, jibun FROM master_buildings WHERE {' AND '.join(where)} ORDER BY id"
    if limit:
        sql += f" LIMIT {int(limit)}"
    cur.execute(sql, params)
    targets = cur.fetchall()

    total = len(targets)
    print(f"[시작] 대상 {total}건 (only_missing={only_missing and not ids}, limit={limit})", flush=True)

    n_ok = n_empty = n_skip = n_err = 0
    consec_err = 0

    for i, b in enumerate(targets, 1):
        bid, name = b["id"], b["building_name"]
        try:
            bjd = bjdong.find_bjdong_cd(b["sgg_cd"], b["umd_nm"])
            if not bjd:
                n_skip += 1
                cur.execute(
                    "UPDATE master_buildings SET title_backfilled_at=NOW() WHERE id=%s", (bid,)
                )
                print(f"  [{i}/{total}] SKIP id={bid} {name} — bjdong_cd 못찾음(umd={b['umd_nm']})", flush=True)
                continue
            plat_gb, bun, ji = parse_jibun(b["jibun"])
            rows = _fetch_title_rows(b["sgg_cd"], bjd, plat_gb, bun, ji)
            consec_err = 0  # 성공적으로 응답 받음
            rep = _pick_representative(rows)
            if not rep:
                n_empty += 1
                cur.execute(
                    "UPDATE master_buildings SET title_backfilled_at=NOW() WHERE id=%s", (bid,)
                )
                print(f"  [{i}/{total}] EMPTY id={bid} {name} — 표제부 없음", flush=True)
                continue
            vals = _extract(rep)
            cur.execute(
                """UPDATE master_buildings SET
                     use_apr_day=%(use_apr_day)s, tot_pkng_cnt=%(tot_pkng_cnt)s,
                     grnd_flr_cnt=%(grnd_flr_cnt)s, ugrnd_flr_cnt=%(ugrnd_flr_cnt)s,
                     tot_area=%(tot_area)s, plat_area=%(plat_area)s,
                     hhld_cnt=%(hhld_cnt)s, strct_nm=%(strct_nm)s,
                     title_backfilled_at=NOW()
                   WHERE id=%(id)s""",
                {**vals, "id": bid},
            )
            n_ok += 1
            print(
                f"  [{i}/{total}] OK   id={bid} {name} — 준공={vals['use_apr_day']} "
                f"연면적={vals['tot_area']} 대지={vals['plat_area']} 세대={vals['hhld_cnt']} "
                f"지상/지하={vals['grnd_flr_cnt']}/{vals['ugrnd_flr_cnt']} 주차={vals['tot_pkng_cnt']} "
                f"구조={vals['strct_nm']}",
                flush=True,
            )
        except Exception as e:
            n_err += 1
            consec_err += 1
            print(f"  [{i}/{total}] ERR  id={bid} {name} — {type(e).__name__}: {e}", flush=True)
            if consec_err >= 10:
                print("[중단] 연속 오류 10건 — API 쿼터 소진/장애 추정. 남은 건은 나중에 재실행하세요.", flush=True)
                break

        if i % 20 == 0:
            conn.commit()
            print(f"  ...진행 {i}/{total} (OK={n_ok} EMPTY={n_empty} SKIP={n_skip} ERR={n_err})", flush=True)
        time.sleep(sleep)

    conn.commit()
    print(
        f"[완료] 처리 {n_ok + n_empty + n_skip + n_err}건 / OK={n_ok} EMPTY={n_empty} "
        f"SKIP={n_skip} ERR={n_err}",
        flush=True,
    )
    return n_ok, n_empty, n_skip, n_err


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--ids", type=str, default=None, help="쉼표구분 id 목록")
    ap.add_argument("--all", action="store_true", help="이미 백필된 건도 재조회")
    ap.add_argument("--sleep", type=float, default=0.2)
    args = ap.parse_args()
    ids = [int(x) for x in args.ids.split(",") if x.strip()] if args.ids else None
    run(limit=args.limit, ids=ids, only_missing=not args.all, sleep=args.sleep)


if __name__ == "__main__":
    main()
