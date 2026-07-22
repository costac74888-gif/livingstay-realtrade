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
import threading
import time
import argparse
from datetime import datetime

from db import get_conn, init_db
from address_utils import BjdongMap, parse_jibun
from building_registry import _fetch_title_rows, _hocnt, BLD_SERVICE_KEY
# 관리자 버튼용 상태 기록(run_id 펜싱 + 하트비트)은 sync_lodgings와 동일한 로직 재사용
from sync_lodgings import _read_status, _write_status, _touch, _still_owner, HEARTBEAT_SEC

BJDONG_CSV = os.environ.get("BJDONG_CODE_CSV", "법정동코드_전체자료.zip")


def _mask_key(text):
    """로그/상태에 서비스키(원문·URL인코딩 변형)가 노출되지 않도록 마스킹."""
    text = str(text)
    if BLD_SERVICE_KEY:
        from urllib.parse import quote
        for variant in (BLD_SERVICE_KEY, quote(BLD_SERVICE_KEY, safe=""), quote(BLD_SERVICE_KEY)):
            text = text.replace(variant, "***")
    return text


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
        # 관리건축물대장PK(건물관리번호) — 상가업소정보(storeListInBuilding) 조회 키
        "mgm_bldrgst_pk": (rep.get("mgmBldrgstPk") or "").strip() or None,
    }


def run(limit=None, ids=None, only_missing=True, sleep=0.2, pk_only=False,
        status_key=None, run_id=None):
    """pk_only=True — 보강 모드: 이미 표제부가 채워진 건물도 포함해
    mgm_bldrgst_pk IS NULL 인 건물만 대상으로 그 컬럼 하나만 채운다.
    (전체 표제부 재조회 없이 건물관리번호만 추가 확보하는 용도)"""
    init_db()
    bjdong = BjdongMap(BJDONG_CSV)
    conn = get_conn()
    cur = conn.cursor()

    where = ["sgg_cd IS NOT NULL", "umd_nm IS NOT NULL", "jibun IS NOT NULL"]
    params = []
    if ids:
        where.append("id = ANY(%s)")
        params.append(ids)
    elif pk_only:
        where.append("mgm_bldrgst_pk IS NULL")
    elif only_missing:
        where.append("title_backfilled_at IS NULL")
    sql = f"SELECT id, building_name, sgg_cd, umd_nm, jibun FROM master_buildings WHERE {' AND '.join(where)} ORDER BY id"
    if limit:
        sql += f" LIMIT {int(limit)}"
    cur.execute(sql, params)
    targets = cur.fetchall()

    total = len(targets)
    mode = "pk_only" if pk_only else f"only_missing={only_missing and not ids}"
    print(f"[시작] 대상 {total}건 ({mode}, limit={limit})", flush=True)

    n_ok = n_empty = n_skip = n_err = 0
    consec_err = 0

    for i, b in enumerate(targets, 1):
        # run_id 펜싱: 다른 실행이 상태를 가져갔으면 즉시 중단 (split-brain 방지)
        if status_key and run_id and i % 20 == 0 and not _still_owner(cur, status_key, run_id):
            print("[중단] 상태 소유권을 잃었습니다(다른 실행 감지). 종료합니다.", flush=True)
            break
        bid, name = b["id"], b["building_name"]
        try:
            bjd = bjdong.find_bjdong_cd(b["sgg_cd"], b["umd_nm"])
            if not bjd:
                n_skip += 1
                if not pk_only:
                    # pk_only 보강 모드에선 title_backfilled_at을 건드리지 않는다
                    # (표제부 미백필 건물을 '백필 완료'로 오기록하지 않기 위함)
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
                if not pk_only:
                    cur.execute(
                        "UPDATE master_buildings SET title_backfilled_at=NOW() WHERE id=%s", (bid,)
                    )
                print(f"  [{i}/{total}] EMPTY id={bid} {name} — 표제부 없음", flush=True)
                continue
            vals = _extract(rep)
            if pk_only:
                if vals["mgm_bldrgst_pk"]:
                    cur.execute(
                        "UPDATE master_buildings SET mgm_bldrgst_pk=%s WHERE id=%s",
                        (vals["mgm_bldrgst_pk"], bid),
                    )
                    n_ok += 1
                    print(f"  [{i}/{total}] OK   id={bid} {name} — pk={vals['mgm_bldrgst_pk']}", flush=True)
                else:
                    n_empty += 1
                    print(f"  [{i}/{total}] EMPTY id={bid} {name} — 표제부에 mgmBldrgstPk 없음", flush=True)
            else:
                cur.execute(
                    """UPDATE master_buildings SET
                         use_apr_day=%(use_apr_day)s, tot_pkng_cnt=%(tot_pkng_cnt)s,
                         grnd_flr_cnt=%(grnd_flr_cnt)s, ugrnd_flr_cnt=%(ugrnd_flr_cnt)s,
                         tot_area=%(tot_area)s, plat_area=%(plat_area)s,
                         hhld_cnt=%(hhld_cnt)s, strct_nm=%(strct_nm)s,
                         mgm_bldrgst_pk=COALESCE(%(mgm_bldrgst_pk)s, mgm_bldrgst_pk),
                         title_backfilled_at=NOW()
                       WHERE id=%(id)s""",
                    {**vals, "id": bid},
                )
                n_ok += 1
                print(
                    f"  [{i}/{total}] OK   id={bid} {name} — 준공={vals['use_apr_day']} "
                    f"연면적={vals['tot_area']} 대지={vals['plat_area']} 세대={vals['hhld_cnt']} "
                    f"지상/지하={vals['grnd_flr_cnt']}/{vals['ugrnd_flr_cnt']} 주차={vals['tot_pkng_cnt']} "
                    f"구조={vals['strct_nm']} pk={vals['mgm_bldrgst_pk']}",
                    flush=True,
                )
        except Exception as e:
            n_err += 1
            consec_err += 1
            print(f"  [{i}/{total}] ERR  id={bid} {name} — {type(e).__name__}: {_mask_key(e)}", flush=True)
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
    ap.add_argument("--fill-pk", action="store_true",
                    help="보강 모드: mgm_bldrgst_pk가 NULL인 건물만 대상으로 건물관리번호만 채움")
    ap.add_argument("--sleep", type=float, default=0.2)
    ap.add_argument("--status-key", default=None,
                    help="관리자 버튼 실행용 app_meta 상태 키")
    args = ap.parse_args()
    ids = [int(x) for x in args.ids.split(",") if x.strip()] if args.ids else None

    run_id = None
    stop_beat = threading.Event()
    if args.status_key:
        status = _read_status(args.status_key)
        if not status or status.get("state") != "running":
            print("[title-info] running 상태가 아니므로 종료합니다.")
            return
        run_id = status.get("run_id") or ""

        def _beat():
            while not stop_beat.wait(HEARTBEAT_SEC):
                try:
                    _touch(args.status_key, run_id)
                except Exception:
                    pass
        threading.Thread(target=_beat, daemon=True).start()

    error = None
    n_ok = n_empty = n_skip = n_err = None
    try:
        n_ok, n_empty, n_skip, n_err = run(
            limit=args.limit, ids=ids, only_missing=not args.all, sleep=args.sleep,
            pk_only=args.fill_pk, status_key=args.status_key, run_id=run_id)
    except Exception as e:
        error = _mask_key(e)[:500]
        print(f"[title-info] 실패: {error}")

    if args.status_key and run_id is not None:
        stop_beat.set()
        status = _read_status(args.status_key) or {}
        status.update({
            "state": "failed" if error else "done",
            "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "ok": n_ok,
            "empty": n_empty,
            "skip": n_skip,
            "err": n_err,
            "error": error,
        })
        for attempt in range(3):
            try:
                _write_status(args.status_key, status, run_id)
                break
            except Exception as e:
                print(f"[title-info] 상태 저장 실패({attempt + 1}/3): {e}")
                time.sleep(5)
    if error and not args.status_key:
        sys.exit(1)


if __name__ == "__main__":
    main()
