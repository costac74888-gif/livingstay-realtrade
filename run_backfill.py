"""
run_backfill.py — 일반숙박시설 통매매 포함 과거 데이터 소급 백필 런처.

Replit Workflow "Backfill (일반숙박 소급)" 커맨드로 실행된다:
  python -u run_backfill.py

동작:
  1. app_meta 에 tx_backfill_status = running 기록 (admin UI에 실행 중 표시)
  2. sync_batch.sync_transactions() 직접 호출 (매개변수 동일: months=60, progress_key)
  3. 30초 heartbeat 스레드 — admin UI 가 stale 로 잘못 판정하지 않도록
  4. 종료 후 tx_backfill_status = done / failed 기록

체크포인트(tx_backfill_progress)가 남아있으면 이어서 진행.
일일 한도(5,000건/일)에 걸리면 중단 후 다음 날 재실행 시 자동 재개.
"""

import json
import secrets
import sys
import threading
import time
from datetime import datetime

from db import get_conn
from sync_batch import sync_transactions

META_KEY = "tx_backfill_status"
PROGRESS_KEY = "tx_backfill_progress"
MONTHS = 60
HEARTBEAT_SEC = 30


def _tx_count():
    conn = get_conn(); cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) AS c FROM transactions")
        return cur.fetchone()["c"]
    finally:
        cur.close(); conn.close()


def _write_status(payload, run_id):
    conn = get_conn(); cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE app_meta SET value=%s, updated_at=NOW() "
            "WHERE key=%s AND (value::jsonb->>'run_id')=%s",
            (json.dumps(payload, ensure_ascii=False), META_KEY, run_id))
        conn.commit()
    finally:
        cur.close(); conn.close()


def _touch(run_id):
    conn = get_conn(); cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE app_meta SET updated_at=NOW() "
            "WHERE key=%s AND (value::jsonb->>'run_id')=%s",
            (META_KEY, run_id))
        conn.commit()
    finally:
        cur.close(); conn.close()


def main():
    run_id = secrets.token_hex(8)
    tx_before = _tx_count()

    status = {
        "run_id": run_id,
        "state": "running",
        "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "finished_at": None,
        "tx_before": tx_before,
        "inserted": None,
        "error": None,
        "months": MONTHS,
        "target_from": "2020-01-01",
        "log_file": None,
    }

    # ── 잠금 획득 ──────────────────────────────────────────────────────────────
    conn = get_conn(); cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO app_meta (key,value,updated_at) VALUES(%s,%s,NOW()) "
            "ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value,updated_at=NOW() "
            "WHERE ((app_meta.value::jsonb->>'state') IS DISTINCT FROM 'running' "
            "    OR app_meta.updated_at < NOW()-INTERVAL'5 minutes') "
            "  AND ((app_meta.value::jsonb->>'state') IS DISTINCT FROM 'done' "
            "    OR app_meta.updated_at < NOW()-INTERVAL'24 hours')",
            (META_KEY, json.dumps(status, ensure_ascii=False)))
        acquired = cur.rowcount > 0
        conn.commit()
    finally:
        cur.close(); conn.close()

    if not acquired:
        conn2 = get_conn(); cur2 = conn2.cursor()
        cur2.execute("SELECT value::jsonb->>'state' AS s FROM app_meta WHERE key=%s", (META_KEY,))
        row = cur2.fetchone(); cur2.close(); conn2.close()
        prev = row["s"] if row else "unknown"
        print(f"[backfill] 잠금 획득 실패 (현재 상태: {prev}). "
              f"이미 실행 중이거나 24시간 내 완료 이력이 있습니다.", flush=True)
        sys.exit(0)

    print(f"[backfill] 시작 — run_id={run_id}, tx_before={tx_before}", flush=True)

    # ── heartbeat 스레드 ────────────────────────────────────────────────────────
    stop_hb = threading.Event()
    def _hb_worker():
        while not stop_hb.wait(HEARTBEAT_SEC):
            try:
                _touch(run_id)
            except Exception:
                pass
    hb = threading.Thread(target=_hb_worker, daemon=True)
    hb.start()

    # ── 실제 백필 실행 ──────────────────────────────────────────────────────────
    error = None
    try:
        sync_transactions(months=MONTHS, progress_key=PROGRESS_KEY)
    except Exception as e:
        error = str(e)[:600]
        print(f"[backfill] 오류: {error}", flush=True)
    finally:
        stop_hb.set()

    # ── 완료 상태 기록 ──────────────────────────────────────────────────────────
    inserted = None
    try:
        inserted = max(0, _tx_count() - tx_before)
    except Exception:
        pass

    status.update({
        "state": "failed" if error else "done",
        "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "inserted": inserted,
        "error": error,
    })
    for attempt in range(3):
        try:
            _write_status(status, run_id)
            break
        except Exception as e:
            print(f"[backfill] 상태 저장 실패({attempt+1}/3): {e}", flush=True)
            time.sleep(5)

    print(f"[backfill] 완료 — state={status['state']}, inserted={inserted}", flush=True)


if __name__ == "__main__":
    main()
