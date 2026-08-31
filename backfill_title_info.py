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
python backfill_title_info.py --ids 2654,2655    # 특정 id 중 미백필분만
python backfill_title_info.py --ids 2654 --all   # 특정 id 강제 재조회
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
MAX_DB_RECONNECT_ATTEMPTS = 3
DB_RECONNECT_DELAY_SEC = 5.0


class _DatabaseReconnectExhausted(RuntimeError):
    """표제부 백필이 DB 재접속 한도를 모두 소진했을 때의 오류."""


class _RunOwnershipLost(RuntimeError):
    """재접속 중 app_meta 실행 lease가 다른 run_id로 넘어갔다."""


def _is_connection_lost(exc, conn):
    """API 오류와 DB 연결 단절을 구분한다.

    PostgreSQL의 SSL 단절은 보통 OperationalError로 오지만, 이미 닫힌
    연결에서 후속 cursor/commit이 실패하면 InterfaceError가 될 수 있다.
    """
    if isinstance(exc, (psycopg2.OperationalError, psycopg2.InterfaceError)):
        return True
    closed = getattr(conn, "closed", 0)
    if isinstance(closed, bool) and closed:
        return True
    if isinstance(closed, int) and closed != 0:
        return True
    message = str(exc).lower()
    return any(
        marker in message
        for marker in (
            "ssl connection has been closed",
            "server closed the connection",
            "connection already closed",
            "connection is closed",
            "connection not open",
        )
    )


def _close_connection(conn, cur):
    for resource in (cur, conn):
        if resource is None:
            continue
        try:
            resource.close()
        except Exception:
            pass


def _update_reconnect_status(status_key, run_id, updates):
    """재접속 상태를 best-effort로 기록한다.

    연결이 끊긴 순간에는 이 기록 자체도 실패할 수 있으므로, 상태 기록
    실패가 백필 재시도를 방해하지 않게 한다. 새 연결이 확보된 뒤에는
    다시 기록하여 관리자 화면의 최종 상태를 보정한다.
    """
    if not status_key or run_id is None:
        return
    try:
        status = _read_status(status_key) or {}
        if status.get("run_id") != run_id:
            return
        status.update(updates)
        _write_status(status_key, status, run_id)
    except Exception as e:
        print(f"[title-info] 재접속 상태 저장 실패: {_mask_key(e)[:300]}", flush=True)


def _reconnect_connection(conn, cur, *, status_key=None, run_id=None,
                          reconnect_state=None):
    """끊긴 연결을 실행 전체의 제한된 예산 안에서 교체한다."""
    _close_connection(conn, cur)
    try:
        status = _read_status(status_key) if status_key and run_id is not None else None
    except Exception as e:
        # 원래 연결이 끊긴 직후에는 상태 조회도 같은 장애를 만날 수 있다.
        # 재접속 자체는 계속 시도하고, 연결을 얻은 뒤 상태를 다시 기록한다.
        status = None
        print(
            f"[title-info] 재접속 전 상태 조회 실패: {_mask_key(e)[:300]}",
            flush=True,
        )
    if reconnect_state is None:
        reconnect_state = {}
    if "attempts" not in reconnect_state:
        try:
            reconnect_state["attempts"] = int(
                (status or {}).get("reconnect_attempts") or 0
            )
        except (TypeError, ValueError):
            reconnect_state["attempts"] = 0
    if "successes" not in reconnect_state:
        try:
            reconnect_state["successes"] = int(
                (status or {}).get("reconnect_count") or 0
            )
        except (TypeError, ValueError):
            reconnect_state["successes"] = 0
    if "failures" not in reconnect_state:
        try:
            reconnect_state["failures"] = int(
                (status or {}).get("reconnect_failures") or 0
            )
        except (TypeError, ValueError):
            reconnect_state["failures"] = 0

    last_error = None
    while reconnect_state["attempts"] < MAX_DB_RECONNECT_ATTEMPTS:
        reconnect_state["attempts"] += 1
        attempt = reconnect_state["attempts"]
        _update_reconnect_status(
            status_key,
            run_id,
            {
                "connection_state": "reconnecting",
                "reconnect_attempts": reconnect_state["attempts"],
                "last_reconnect_error": (
                    None if last_error is None else _mask_key(last_error)[:500]
                ),
            },
        )
        new_conn = None
        new_cur = None
        try:
            new_conn = get_conn()
            new_cur = new_conn.cursor()
            if status_key and run_id is not None:
                owner = _still_owner(new_cur, status_key, run_id)
                if not owner:
                    raise _RunOwnershipLost(
                        "DB 재접속 중 건축정보 채우기 실행 소유권이 변경되어 중단합니다."
                    )
            reconnect_state["successes"] += 1
            _update_reconnect_status(
                status_key,
                run_id,
                {
                    "connection_state": "connected",
                    "reconnect_count": reconnect_state["successes"],
                    "reconnect_attempts": reconnect_state["attempts"],
                    "last_reconnect_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "last_reconnect_error": None,
                },
            )
            print(
                f"[title-info] DB 재접속 성공 ({attempt}/{MAX_DB_RECONNECT_ATTEMPTS})",
                flush=True,
            )
            return new_conn, new_cur
        except _RunOwnershipLost:
            _close_connection(new_conn, new_cur)
            raise
        except Exception as e:
            last_error = e
            reconnect_state["failures"] += 1
            _close_connection(new_conn, new_cur)
            _update_reconnect_status(
                status_key,
                run_id,
                {
                    "connection_state": "reconnecting",
                    "reconnect_attempts": reconnect_state["attempts"],
                    "reconnect_failures": reconnect_state["failures"],
                    "last_reconnect_error": _mask_key(e)[:500],
                },
            )
            print(
                f"[title-info] DB 재접속 실패 ({attempt}/{MAX_DB_RECONNECT_ATTEMPTS}): "
                f"{_mask_key(e)[:300]}",
                flush=True,
            )
            if attempt < MAX_DB_RECONNECT_ATTEMPTS:
                time.sleep(DB_RECONNECT_DELAY_SEC)

    reason = (
        "새 연결도 다시 끊겨 실행 전체 재접속 예산을 모두 사용했습니다."
        if last_error is None
        else _mask_key(last_error)[:300]
    )
    message = (
        f"DB 재접속 시도 한도 {MAX_DB_RECONNECT_ATTEMPTS}회 소진 "
        f"(성공 {reconnect_state['successes']}회, 실패 "
        f"{reconnect_state['failures']}회): {reason}"
    )
    _update_reconnect_status(
        status_key,
        run_id,
        {
            "connection_state": "failed",
            "reconnect_attempts": reconnect_state["attempts"],
            "reconnect_failures": reconnect_state["failures"],
            "last_reconnect_error": message[:500],
            "error": message[:500],
        },
    )
    raise _DatabaseReconnectExhausted(message) from last_error


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
    reconnect_state = {"attempts": 0, "successes": 0, "failures": 0}
    conn = None
    cur = None
    connection_state = {"conn": conn, "cur": cur}
    try:
        try:
            conn = get_conn()
            cur = conn.cursor()
        except Exception as e:
            if not _is_connection_lost(e, conn):
                raise
            conn, cur = _reconnect_connection(
                conn,
                cur,
                status_key=status_key,
                run_id=run_id,
                reconnect_state=reconnect_state,
            )
        connection_state["conn"] = conn
        connection_state["cur"] = cur
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
            connection_state=connection_state,
            reconnect_state=reconnect_state,
        )
    finally:
        _close_connection(connection_state.get("conn"), connection_state.get("cur"))


def _run_with_open_connection(limit=None, ids=None, only_missing=True, sleep=0.2, pk_only=False,
                              status_key=None, run_id=None, *, bjdong, conn, cur,
                              connection_state=None, reconnect_state=None):
    if connection_state is None:
        connection_state = {"conn": conn, "cur": cur}
    if reconnect_state is None:
        reconnect_state = {"attempts": 0, "successes": 0, "failures": 0}

    def reconnect_after(exc):
        nonlocal conn, cur
        print(
            f"[title-info] DB 연결 단절 감지: {type(exc).__name__}: "
            f"{_mask_key(exc)[:300]} — 현재 건물부터 이어갑니다.",
            flush=True,
        )
        conn, cur = _reconnect_connection(
            conn,
            cur,
            status_key=status_key,
            run_id=run_id,
            reconnect_state=reconnect_state,
        )
        connection_state.update({"conn": conn, "cur": cur})

    where = ["sgg_cd IS NOT NULL", "umd_nm IS NOT NULL", "jibun IS NOT NULL"]
    params = []
    if ids:
        where.append("id = ANY(%s)")
        params.append(ids)
        if only_missing:
            where.append("title_backfilled_at IS NULL")
    elif pk_only:
        where.append("mgm_bldrgst_pk IS NULL")
    elif only_missing:
        where.append("title_backfilled_at IS NULL")
    if pk_only:
        checkpoint_condition = " AND mgm_bldrgst_pk IS NULL"
    elif only_missing:
        checkpoint_condition = " AND title_backfilled_at IS NULL"
    else:
        checkpoint_condition = ""
    sql = f"SELECT id, building_name, sgg_cd, umd_nm, jibun FROM master_buildings WHERE {' AND '.join(where)} ORDER BY id"
    if limit:
        sql += f" LIMIT {int(limit)}"
    while True:
        try:
            cur.execute(sql, params)
            targets = cur.fetchall()
            break
        except Exception as e:
            if not _is_connection_lost(e, conn):
                raise
            reconnect_after(e)

    total = len(targets)
    mode = "pk_only" if pk_only else f"only_missing={only_missing}"
    print(f"[시작] 대상 {total}건 ({mode}, limit={limit})", flush=True)

    n_ok = n_empty = n_skip = n_err = 0
    changed = 0
    consec_err = 0
    stop_for_errors = False

    for i, b in enumerate(targets, 1):
        # run_id 펜싱: 다른 실행이 상태를 가져갔으면 즉시 중단 (split-brain 방지)
        if status_key and run_id and i % 20 == 0:
            while True:
                try:
                    owner = _still_owner(cur, status_key, run_id)
                    break
                except Exception as e:
                    if not _is_connection_lost(e, conn):
                        raise
                    reconnect_after(e)
            if not owner:
                print("[중단] 상태 소유권을 잃었습니다(다른 실행 감지). 종료합니다.", flush=True)
                break
        bid, name = b["id"], b["building_name"]
        item_done = False
        while not item_done:
            try:
                bjd = bjdong.find_bjdong_cd(b["sgg_cd"], b["umd_nm"])
                if not bjd:
                    outcome_detail = f"bjdong_cd 못찾음(umd={b['umd_nm']})"
                    row_changed = 0
                    if not pk_only:
                        # pk_only 보강 모드에선 title_backfilled_at을 건드리지 않는다
                        # (표제부 미백필 건물을 '백필 완료'로 오기록하지 않기 위함)
                        cur.execute(
                            "UPDATE master_buildings SET title_backfilled_at=NOW() "
                            f"WHERE id=%s{checkpoint_condition}",
                            (bid,),
                        )
                        row_changed = cur.rowcount
                    conn.commit()
                    item_done = True
                    changed += row_changed
                    n_skip += 1
                    print(f"  [{i}/{total}] SKIP id={bid} {name} — {outcome_detail}", flush=True)
                    continue
                plat_gb, bun, ji = parse_jibun(b["jibun"])
                rows = _fetch_title_rows(b["sgg_cd"], bjd, plat_gb, bun, ji)
                consec_err = 0  # 성공적으로 응답 받음
                rep = _pick_representative(rows)
                if not rep:
                    row_changed = 0
                    if not pk_only:
                        cur.execute(
                            "UPDATE master_buildings SET title_backfilled_at=NOW() "
                            f"WHERE id=%s{checkpoint_condition}",
                            (bid,),
                        )
                        row_changed = cur.rowcount
                    conn.commit()
                    item_done = True
                    changed += row_changed
                    n_empty += 1
                    print(f"  [{i}/{total}] EMPTY id={bid} {name} — 표제부 없음", flush=True)
                    continue
                vals = _extract(rep)
                official_name = resolve_api_building_name({
                    "bld_nm": rep.get("bldNm"),
                    "dong_nm": rep.get("dongNm"),
                })
                if pk_only:
                    if vals["mgm_bldrgst_pk"]:
                        cur.execute(
                            f"""
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
                             WHERE id=%s{checkpoint_condition}
                            """,
                            (
                                vals["mgm_bldrgst_pk"], official_name, official_name,
                                official_name, official_name, official_name, bid,
                            ),
                        )
                    conn.commit()
                    item_done = True
                    if vals["mgm_bldrgst_pk"]:
                        changed += cur.rowcount
                        n_ok += 1
                        print(f"  [{i}/{total}] OK   id={bid} {name} — pk={vals['mgm_bldrgst_pk']}", flush=True)
                    else:
                        n_empty += 1
                        print(f"  [{i}/{total}] EMPTY id={bid} {name} — 표제부에 mgmBldrgstPk 없음", flush=True)
                else:
                    cur.execute(
                        f"""UPDATE master_buildings SET
                             use_apr_day=%(use_apr_day)s, tot_pkng_cnt=%(tot_pkng_cnt)s,
                             grnd_flr_cnt=%(grnd_flr_cnt)s, ugrnd_flr_cnt=%(ugrnd_flr_cnt)s,
                             tot_area=%(tot_area)s, plat_area=%(plat_area)s,
                             hhld_cnt=%(hhld_cnt)s, strct_nm=%(strct_nm)s,
                             mgm_bldrgst_pk=COALESCE(%(mgm_bldrgst_pk)s, mgm_bldrgst_pk),
                             building_name=CASE
                                 WHEN %(official_name)s <> '' AND name_pending IS TRUE
                                 THEN %(official_name)s ELSE building_name
                             END,
                             name_pending=CASE
                                 WHEN %(official_name)s <> '' AND name_pending IS TRUE
                                 THEN FALSE ELSE name_pending
                             END,
                             building_name_source=CASE
                                 WHEN %(official_name)s <> '' AND name_pending IS TRUE
                                 THEN 'official' ELSE building_name_source
                             END,
                             building_name_candidate_count=CASE
                                 WHEN %(official_name)s <> '' AND name_pending IS TRUE
                                 THEN 0 ELSE building_name_candidate_count
                             END,
                             title_backfilled_at=NOW(),
                             building_status=CASE
                                 WHEN %(use_apr_day)s IS NOT NULL AND %(use_apr_day)s != ''
                                      AND building_status IN ('허가','착공')
                                 THEN '완공'
                                 ELSE building_status
                             END
                           WHERE id=%(id)s{checkpoint_condition}""",
                        {**vals, "id": bid, "official_name": official_name},
                    )
                    row_changed = cur.rowcount
                    conn.commit()
                    item_done = True
                    changed += row_changed
                    n_ok += 1
                    print(
                        f"  [{i}/{total}] OK   id={bid} {name} — 준공={vals['use_apr_day']} "
                        f"연면적={vals['tot_area']} 대지={vals['plat_area']} 세대={vals['hhld_cnt']} "
                        f"지상/지하={vals['grnd_flr_cnt']}/{vals['ugrnd_flr_cnt']} 주차={vals['tot_pkng_cnt']} "
                        f"구조={vals['strct_nm']} pk={vals['mgm_bldrgst_pk']}",
                        flush=True,
                    )
            except Exception as e:
                if _is_connection_lost(e, conn):
                    reconnect_after(e)
                    continue
                try:
                    conn.rollback()
                except Exception:
                    pass
                n_err += 1
                consec_err += 1
                item_done = True
                print(f"  [{i}/{total}] ERR  id={bid} {name} — {type(e).__name__}: {_mask_key(e)}", flush=True)
                if consec_err >= 10:
                    print("[중단] 연속 오류 10건 — API 쿼터 소진/장애 추정. 남은 건은 나중에 재실행하세요.", flush=True)
                    stop_for_errors = True

        if i % 20 == 0:
            print(f"  ...진행 {i}/{total} (OK={n_ok} EMPTY={n_empty} SKIP={n_skip} ERR={n_err})", flush=True)
        if stop_for_errors:
            break
        time.sleep(sleep)

    while True:
        try:
            renamed = refresh_auto_building_names(conn)
            break
        except Exception as e:
            if not _is_connection_lost(e, conn):
                raise
            reconnect_after(e)
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
    connection_failed = False
    n_ok = n_empty = n_skip = n_err = None
    try:
        n_ok, n_empty, n_skip, n_err = run(
            limit=args.limit, ids=ids, only_missing=not args.all, sleep=args.sleep,
            pk_only=args.fill_pk, status_key=args.status_key, run_id=run_id)
    except Exception as e:
        connection_failed = isinstance(e, _DatabaseReconnectExhausted)
        error = _mask_key(e)[:500]
        print(f"[title-info] 실패: {error}")

    if args.status_key and run_id is not None:
        stop_beat.set()
        final_status = {
            "state": "failed" if error else "done",
            "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "ok": n_ok,
            "empty": n_empty,
            "skip": n_skip,
            "err": n_err,
            "error": error,
        }
        for attempt in range(3):
            try:
                status = _read_status(args.status_key) or {}
                status.update(final_status)
                if connection_failed:
                    status["connection_state"] = "failed"
                else:
                    status["connection_state"] = status.get(
                        "connection_state", "connected"
                    )
                _write_status(args.status_key, status, run_id)
                break
            except Exception as e:
                print(f"[title-info] 상태 저장 실패({attempt + 1}/3): {e}")
                time.sleep(5)
    if error and not args.status_key:
        sys.exit(1)


if __name__ == "__main__":
    main()
