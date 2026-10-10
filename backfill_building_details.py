"""Detailed architecture backfill; shares the existing title-info job lease.

No DDL and no original-record deletion. Retry checkpoints live in app_meta.
Run with --ids for verification; --continuous resumes after KST day changes.
"""
import argparse
import json
import threading
import time
import uuid
from datetime import datetime

from address_utils import BjdongMap
from building_detail_enrichment import PREFIX, STAGES, enrich, due_stages
from db import get_conn
from quota_policy import QuotaExhausted, korea_today
from building_detail_budget import reserve, BATCH_KEY
from sync_lodgings import _read_status, _write_status, _still_owner, _touch, HEARTBEAT_SEC

STATUS_KEY = "title_info_sync_status"


def claim_run(key, run_id):
    conn = get_conn()
    cur = conn.cursor()
    try:
        initial = {
            "state": "running", "mode": "details", "run_id": run_id,
            "started_at": datetime.now().isoformat(), "processed": 0, "ok": 0,
            "empty": 0, "err": 0, "skip": 0,
        }
        cur.execute("""
            INSERT INTO app_meta(key,value,updated_at) VALUES(%s,%s,NOW())
            ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value,updated_at=NOW()
            WHERE app_meta.value::jsonb->>'state' IS DISTINCT FROM 'running'
               OR app_meta.updated_at < NOW()-INTERVAL '5 minutes'
            RETURNING key
        """, [key, json.dumps(initial)])
        success = bool(cur.fetchone())
        conn.commit()
        return success
    finally:
        cur.close()
        conn.close()


def still_owner(key, run_id):
    conn = get_conn()
    cur = conn.cursor()
    try:
        return _still_owner(cur, key, run_id)
    finally:
        cur.close()
        conn.close()


def candidate_page(after=0, ids=None):
    conn = get_conn()
    cur = conn.cursor()
    try:
        condition = "AND mb.id=ANY(%s)" if ids else ""
        cur.execute(f"""
            SELECT mb.id, meta.value
            FROM master_buildings mb
            LEFT JOIN app_meta meta ON meta.key=%s || mb.id::text
            WHERE mb.id>%s AND mb.sgg_cd IS NOT NULL AND mb.umd_nm IS NOT NULL
              AND mb.jibun IS NOT NULL {condition}
            ORDER BY mb.id LIMIT 100
        """, [PREFIX, after, *([ids] if ids else [])])
        return list(cur.fetchall())
    finally:
        cur.close()
        conn.close()


def run(args):
    previous = _read_status(args.status_key) or {}
    run_id = previous.get("run_id") if args.adopt else uuid.uuid4().hex
    if args.adopt:
        if not run_id or previous.get("state") != "running":
            raise RuntimeError("실행 예약 없음")
    elif not claim_run(args.status_key, run_id):
        raise RuntimeError("다른 건축정보 수집이 실행 중입니다.")
    done = threading.Event()

    def heartbeat():
        while not done.wait(HEARTBEAT_SEC):
            try:
                _touch(args.status_key, run_id)
            except Exception:
                pass  # Writes remain fenced; temporary disconnect cannot steal a run.

    threading.Thread(target=heartbeat, daemon=True).start()
    state = _read_status(args.status_key) or {}
    state.update(mode="details", stages={s: {"ok": 0, "empty": 0, "failed": 0} for s in STAGES})
    bjd = BjdongMap("법정동코드_전체자료.zip")
    ids = [int(s) for s in args.ids.split(",")] if args.ids else None
    counts = {"processed": 0, "ok": 0, "empty": 0, "err": 0, "skip": 0}
    after = 0
    today = korea_today()
    day_processed = 0
    failures = dict.fromkeys(STAGES, 0)
    try:
        while True:
            if not still_owner(args.status_key, run_id):
                return
            if korea_today() != today:
                today, day_processed, after = korea_today(), 0, 0
                failures = dict.fromkeys(STAGES, 0)
            if day_processed >= args.batch_limit:
                state.update(counts, provider_state="daily_batch_limit")
                _write_status(args.status_key, state, run_id)
                if not args.continuous:
                    break
                time.sleep(60)
                continue
            page = candidate_page(after, ids)
            if not page:
                if args.continuous:
                    state.update(counts, provider_state="retry_wait")
                    _write_status(args.status_key, state, run_id)
                    # Revisit due failures and new buildings without requerying
                    # successful or confirmed-empty stages.
                    for _ in range(60):
                        if not still_owner(args.status_key, run_id):
                            return
                        time.sleep(60)
                    after = 0
                    continue
                break
            for row in page:
                after = row["id"]
                if not still_owner(args.status_key, run_id):
                    return
                record = json.loads(row["value"]) if row["value"] else {}
                eligible = [s for s in due_stages(record) if failures[s] < 3]
                if not eligible:
                    continue
                try:
                    # Stored reservation survives restarts and competing runners.
                    day_processed = reserve(BATCH_KEY, args.batch_limit)
                    result = enrich(row["id"], bjd, purpose="batch", allowed_stages=eligible)
                except QuotaExhausted:
                    state.update(counts, provider_state="quota_wait")
                    _write_status(args.status_key, state, run_id)
                    if not args.continuous:
                        return
                    # Leave this row open; continue after the shared daily budget resets.
                    after = row["id"] - 1
                    while korea_today() == today:
                        if not still_owner(args.status_key, run_id):
                            return
                        time.sleep(60)
                    break
                stages = result.get("stages", {})
                statuses = [stages.get(s, {}).get("status") for s in eligible]
                if result.get("busy"):
                    counts["skip"] += 1
                else:
                    counts["processed"] += 1
                    counts["err" if "failed" in statuses else "empty" if all(s == "empty" for s in statuses) else "ok"] += 1
                    for stage in eligible:
                        outcome = stages.get(stage, {}).get("status")
                        if outcome in ("ok", "empty", "failed"):
                            state["stages"][stage][outcome] += 1
                            failures[stage] = (
                                failures[stage] + 1
                                if outcome == "failed" and stages[stage].get("failure_kind") != "data"
                                else 0
                            )
                state.update(counts, last_building_id=row["id"], provider_state=None)
                state["blocked_stages"] = [s for s in STAGES if failures[s] >= 3]
                _write_status(args.status_key, state, run_id)
                print(json.dumps({"id": row["id"], **result}, ensure_ascii=False), flush=True)
                if all(failures[s] >= 3 for s in STAGES):
                    raise RuntimeError("세 API 모두 연속 실패: 전체 수집 중단, 연결 점검 필요")
                if args.limit and counts["processed"] >= args.limit:
                    return
                if day_processed >= args.batch_limit:
                    break
                time.sleep(args.sleep)
        if any(failures[s] >= 3 for s in STAGES):
            state["warning"] = "일부 API 연속 실패로 해당 단계는 보류했습니다."
    except Exception as exc:
        state.update(state="failed", error=type(exc).__name__ + ": 상세 수집 중단")
        raise
    finally:
        done.set()
        # Never let an expired runner overwrite the new owner's finish status.
        if still_owner(args.status_key, run_id):
            state.update(counts, finished_at=datetime.now().isoformat())
            state["state"] = "failed" if state.get("state") == "failed" else "done"
            _write_status(args.status_key, state, run_id)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--batch-limit", type=int, default=1000, help="일별 처리 건수 운영 제한(공급자 공식 한도 아님)")
    parser.add_argument("--continuous", action="store_true")
    parser.add_argument("--adopt", action="store_true")
    parser.add_argument("--sleep", type=float, default=1.0)
    parser.add_argument("--status-key", default=STATUS_KEY)
    args = parser.parse_args()
    if args.batch_limit <= 0:
        parser.error("--batch-limit must be positive")
    run(args)


if __name__ == "__main__":
    main()
