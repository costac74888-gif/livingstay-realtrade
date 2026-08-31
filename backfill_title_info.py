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

import psycopg2

from db import get_conn, init_db
from address_utils import BjdongMap, parse_jibun
from building_registry import (
    _fetch_title_rows,
    _hocnt,
    BLD_SERVICE_KEY,
    resolve_api_building_name,
)
from lodging_matching import refresh_auto_building_names
from stats_cache import mark_master_stats_invalidated
# 관리자 버튼용 상태 기록(run_id 펜싱 + 하트비트)은 sync_lodgings와 동일한 로직 재사용
from sync_lodgings import _read_status, _write_status, _touch, _still_owner, HEARTBEAT_SEC

BJDONG_CSV = os.environ.get("BJDONG_CODE_CSV", "법정동코드_전체자료.zip")


class _RowHandled(Exception):
    """현재 행 처리는 정상 종료됐고 공통 commit 단계로 이동한다."""


class _RunOwnershipLost(RuntimeError):
    """재접속 중 app_meta 실행 lease가 다른 run_id로 넘어갔다."""


def _mask_key(text):
    """로그/상태에 서비스키(원문·URL인코딩 변형)가 노출되지 않도록 마스킹."""
    text = str(text)
    if BLD_SERVICE_KEY:
        from urllib.parse import quote
        for variant in (BLD_SERVICE_KEY, quote(BLD_SERVICE_KEY, safe=""), quote(BLD_SERVICE_KEY)):
            text = text.replace(variant, "***")
    return text


def _is_connection_error(exc):
    """DB 연결이 끊겨 기존 connection/cursor를 재사용할 수 없는 오류인지 판별."""
    if isinstance(exc, (psycopg2.InterfaceError, psycopg2.OperationalError)):
        return True
    text = str(exc).lower()
    return any(
        marker in text
        for marker in (
            "ssl connection has been closed",
            "connection already closed",
            "server closed the connection",
            "connection not open",
        )
    )


def _reconnect(conn, cur, attempts=5, base_delay=1):
    """죽은 연결을 정리하고 제한된 backoff로 새 연결/cursor를 반환한다."""
    try:
        conn.rollback()
    except Exception:
        pass
    try:
        cur.close()
    except Exception:
        pass
    try:
        conn.close()
    except Exception:
        pass
    last_error = None
    for attempt in range(1, attempts + 1):
        new_conn = None
        try:
            new_conn = get_conn()
            try:
                new_cur = new_conn.cursor()
            except Exception:
                new_conn.close()
                raise
            return new_conn, new_cur
        except Exception as e:
            last_error = e
            if attempt >= attempts or not _is_connection_error(e):
                raise
            delay = min(base_delay * (2 ** (attempt - 1)), 10)
            print(
                f"[DB 재접속] 새 연결 실패({attempt}/{attempts}) — "
                f"{delay}초 후 재시도: {type(e).__name__}: {_mask_key(e)}",
                flush=True,
            )
            time.sleep(delay)
    raise last_error


def _reconnect_and_verify(
    conn, cur, db_state, status_key, run_id, attempts=5, base_delay=1
):
    """재접속과 run_id 소유권 확인을 하나의 제한된 복구 루프로 수행."""
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            conn, cur = _reconnect(conn, cur, attempts=1)
            db_state.update(conn=conn, cur=cur)
            if status_key and run_id:
                try:
                    owner = _still_owner(cur, status_key, run_id)
                except Exception as e:
                    if not _is_connection_error(e):
                        raise
                    raise e
                if not owner:
                    raise _RunOwnershipLost(
                        "DB 재접속 중 건축정보 채우기 실행 소유권이 변경되어 중단합니다."
                    )
            return conn, cur
        except _RunOwnershipLost:
            raise
        except Exception as e:
            last_error = e
            if attempt >= attempts or not _is_connection_error(e):
                raise
            delay = min(base_delay * (2 ** (attempt - 1)), 10)
            print(
                f"[DB 재접속] 연결 또는 실행 소유권 확인 실패({attempt}/{attempts}) — "
                f"{delay}초 후 재시도: {type(e).__name__}: {_mask_key(e)}",
                flush=True,
            )
            time.sleep(delay)
    raise last_error


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
    cur = None
    db_state = {"conn": conn, "cur": cur}
    try:
        cur = conn.cursor()
        db_state["cur"] = cur
        return _run_with_open_connection(
            limit=limit,
            ids=ids,
            only_missing=only_missing,
            sleep=sleep,
            pk_only=pk_only,
            status_key=status_key,
            run_id=run_id,
            bjdong=bjdong,
            conn=conn,
            cur=cur,
            db_state=db_state,
        )
    finally:
        if db_state["cur"] is not None:
            db_state["cur"].close()
        db_state["conn"].close()


def _run_with_open_connection(limit=None, ids=None, only_missing=True, sleep=0.2, pk_only=False,
                              status_key=None, run_id=None, *, bjdong, conn, cur,
                              db_state=None):
    if db_state is None:
        db_state = {"conn": conn, "cur": cur}
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
    changed = 0
    consec_err = 0
    db_reconnect_streak = 0
    max_db_reconnect_streak = 5

    # 연결이 끊긴 현재 건은 완료 처리하지 않고 새 연결로 같은 건부터
    # 다시 시도한다. UPDATE는 동일 값에 대한 멱등 연산이므로 commit 응답이
    # 유실된 경우에도 중복 반영이 되지 않는다.
    i = 1
    while i <= total:
        b = targets[i - 1]
        # run_id 펜싱: 다른 실행이 상태를 가져갔으면 즉시 중단 (split-brain 방지)
        if status_key and run_id and i % 20 == 0:
            try:
                owner = _still_owner(cur, status_key, run_id)
            except Exception as e:
                if not _is_connection_error(e):
                    raise
                db_reconnect_streak += 1
                if db_reconnect_streak > max_db_reconnect_streak:
                    raise RuntimeError(
                        f"DB 연결이 {max_db_reconnect_streak}회 연속 끊겨 "
                        "이번 실행을 중단합니다. 다시 실행하면 미완료 건부터 이어갑니다."
                    ) from e
                print(
                    f"[DB 재접속] 상태 확인 중 연결 단절 — 현재 건부터 재시도: "
                    f"{type(e).__name__}: {_mask_key(e)}",
                    flush=True,
                )
                conn, cur = _reconnect_and_verify(
                    conn, cur, db_state, status_key, run_id
                )
                continue
            if not owner:
                print("[중단] 상태 소유권을 잃었습니다(다른 실행 감지). 종료합니다.", flush=True)
                break
        bid, name = b["id"], b["building_name"]
        item_counts = (n_ok, n_empty, n_skip, n_err, changed, consec_err)
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
                    changed += cur.rowcount
                print(f"  [{i}/{total}] SKIP id={bid} {name} — bjdong_cd 못찾음(umd={b['umd_nm']})", flush=True)
                raise _RowHandled
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
                    changed += cur.rowcount
                print(f"  [{i}/{total}] EMPTY id={bid} {name} — 표제부 없음", flush=True)
                raise _RowHandled
            vals = _extract(rep)
            official_name = resolve_api_building_name({
                "bld_nm": rep.get("bldNm"),
                "dong_nm": rep.get("dongNm"),
            })
            if pk_only:
                if vals["mgm_bldrgst_pk"]:
                    cur.execute(
                        """
                        UPDATE master_buildings
                           SET mgm_bldrgst_pk=%s,
                               building_name=CASE
                                   WHEN name_pending IS TRUE AND %s <> '' THEN %s
                                   ELSE building_name
                               END,
                               name_pending=CASE
                                   WHEN name_pending IS TRUE AND %s <> '' THEN FALSE
                                   ELSE name_pending
                               END,
                               building_name_source=CASE
                                   WHEN name_pending IS TRUE AND %s <> '' THEN 'official'
                                   ELSE building_name_source
                               END,
                               building_name_candidate_count=CASE
                                   WHEN name_pending IS TRUE AND %s <> '' THEN 0
                                   ELSE building_name_candidate_count
                               END
                         WHERE id=%s
                        """,
                        (
                            vals["mgm_bldrgst_pk"], official_name, official_name,
                            official_name, official_name, official_name, bid,
                        ),
                    )
                    changed += cur.rowcount
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
                         building_name=CASE
                             WHEN name_pending IS TRUE AND %(official_name)s <> ''
                             THEN %(official_name)s ELSE building_name
                         END,
                         name_pending=CASE
                             WHEN name_pending IS TRUE AND %(official_name)s <> ''
                             THEN FALSE ELSE name_pending
                         END,
                         building_name_source=CASE
                             WHEN name_pending IS TRUE AND %(official_name)s <> ''
                             THEN 'official' ELSE building_name_source
                         END,
                         building_name_candidate_count=CASE
                             WHEN name_pending IS TRUE AND %(official_name)s <> ''
                             THEN 0 ELSE building_name_candidate_count
                         END,
                         title_backfilled_at=NOW(),
                         building_status=CASE
                             WHEN %(use_apr_day)s IS NOT NULL AND %(use_apr_day)s != ''
                                  AND building_status IN ('허가','착공')
                             THEN '완공'
                             ELSE building_status
                         END
                       WHERE id=%(id)s""",
                    {**vals, "id": bid, "official_name": official_name},
                )
                changed += cur.rowcount
                n_ok += 1
                print(
                    f"  [{i}/{total}] OK   id={bid} {name} — 준공={vals['use_apr_day']} "
                    f"연면적={vals['tot_area']} 대지={vals['plat_area']} 세대={vals['hhld_cnt']} "
                    f"지상/지하={vals['grnd_flr_cnt']}/{vals['ugrnd_flr_cnt']} 주차={vals['tot_pkng_cnt']} "
                    f"구조={vals['strct_nm']} pk={vals['mgm_bldrgst_pk']}",
                    flush=True,
                )
        except _RowHandled:
            pass
        except Exception as e:
            if _is_connection_error(e):
                n_ok, n_empty, n_skip, n_err, changed, consec_err = item_counts
                db_reconnect_streak += 1
                if db_reconnect_streak > max_db_reconnect_streak:
                    raise RuntimeError(
                        f"DB 연결이 {max_db_reconnect_streak}회 연속 끊겨 "
                        "이번 실행을 중단합니다. 다시 실행하면 미완료 건부터 이어갑니다."
                    ) from e
                print(
                    f"  [{i}/{total}] DB 연결 단절 — 현재 건부터 새 연결로 재시도: "
                    f"{type(e).__name__}: {_mask_key(e)}",
                    flush=True,
                )
                conn, cur = _reconnect_and_verify(
                    conn, cur, db_state, status_key, run_id
                )
                continue
            n_err += 1
            consec_err += 1
            print(f"  [{i}/{total}] ERR  id={bid} {name} — {type(e).__name__}: {_mask_key(e)}", flush=True)
            if consec_err >= 10:
                print("[중단] 연속 오류 10건 — API 쿼터 소진/장애 추정. 남은 건은 나중에 재실행하세요.", flush=True)
                break

        try:
            # API 호출 간격(기본 0.2초)당 한 번만 commit하므로 과도한 부하 없이
            # 연결 단절 시 재처리 범위를 현재 한 건으로 제한할 수 있다.
            conn.commit()
        except Exception as e:
            if not _is_connection_error(e):
                raise
            n_ok, n_empty, n_skip, n_err, changed, consec_err = item_counts
            db_reconnect_streak += 1
            if db_reconnect_streak > max_db_reconnect_streak:
                raise RuntimeError(
                    f"DB commit 연결이 {max_db_reconnect_streak}회 연속 끊겨 "
                    "이번 실행을 중단합니다. 다시 실행하면 미완료 건부터 이어갑니다."
                ) from e
            print(
                f"  [{i}/{total}] DB commit 연결 단절 — 현재 건부터 새 연결로 재시도: "
                f"{type(e).__name__}: {_mask_key(e)}",
                flush=True,
            )
            conn, cur = _reconnect_and_verify(
                conn, cur, db_state, status_key, run_id
            )
            continue
        if i % 20 == 0:
            print(f"  ...진행 {i}/{total} (OK={n_ok} EMPTY={n_empty} SKIP={n_skip} ERR={n_err})", flush=True)
        db_reconnect_streak = 0
        time.sleep(sleep)
        i += 1

    try:
        conn.commit()
    except Exception as e:
        if not _is_connection_error(e):
            raise
        print(
            f"[DB 재접속] 최종 commit 연결 단절 — 새 연결에서 commit 재시도: "
            f"{type(e).__name__}: {_mask_key(e)}",
            flush=True,
        )
        conn, cur = _reconnect_and_verify(
            conn, cur, db_state, status_key, run_id
        )
        conn.commit()
    try:
        renamed = refresh_auto_building_names(conn)
    except Exception as e:
        if not _is_connection_error(e):
            raise
        print(
            f"[DB 재접속] 자동명칭 정리 중 연결 단절 — 새 연결로 재시도: "
            f"{type(e).__name__}: {_mask_key(e)}",
            flush=True,
        )
        conn, cur = _reconnect_and_verify(
            conn, cur, db_state, status_key, run_id
        )
        renamed = refresh_auto_building_names(conn)
    changed += renamed
    if changed > 0:
        try:
            mark_master_stats_invalidated("backfill_title_info")
            print("[title-info] 통계 원본 캐시 무효화 표식을 갱신했습니다.", flush=True)
        except Exception as e:
            # 표식 기록 실패는 이미 커밋된 백필 결과를 실패로 바꾸지 않는다.
            print(f"[title-info] 통계 원본 캐시 표식 갱신 실패: {_mask_key(e)[:300]}", flush=True)
    print(
        f"[완료] 처리 {n_ok + n_empty + n_skip + n_err}건 / OK={n_ok} EMPTY={n_empty} "
        f"SKIP={n_skip} ERR={n_err} / 신고 기준 자동명칭 변경={renamed}건",
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
