"""
sync_runner.py — 관리자 '실거래 동기화' 버튼용 백그라운드 러너.

app.py 의 POST /api/admin/sync-transactions 가 app_meta('tx_sync_status')에
running 상태를 기록한 뒤 이 스크립트를 '독립 프로세스'로 띄운다.
(웹 워커가 재시작/강제종료되어도 이 프로세스는 계속 살아서 완료/실패를 기록)

동작
- sync_batch.py --master-only 를 하위 프로세스로 실행
- 실행 중 30초마다 app_meta.updated_at 을 갱신(하트비트) → 상태 API가
  하트비트 끊김으로 비정상 종료를 감지할 수 있게 함
- 종료 후 신규 적재 건수(count 차이)와 성공/실패를 app_meta 에 기록
- 에러 메시지에 공공데이터 API 키가 노출되지 않도록 가린다
"""

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from collections import deque
from datetime import datetime

from db import get_conn

META_KEY = "tx_sync_status"  # --meta-key 인자로 변경 가능(과거 데이터 백필은 tx_backfill_status)
TIMEOUT_SEC = 3 * 3600      # 최대 실행 3시간
HEARTBEAT_SEC = 30


def _redact(text):
    for key in (os.environ.get("RTMS_SERVICE_KEY", ""), os.environ.get("BLD_SERVICE_KEY", "")):
        if key:
            text = text.replace(key, "***")
    return text


def _write_status(payload, run_id):
    """최종 상태 기록 — run_id 가 일치할 때만(다른/새 실행 상태를 덮어쓰지 않도록 펜싱)."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE app_meta SET value = %s, updated_at = NOW()
            WHERE key = %s AND (value::jsonb ->> 'run_id') = %s
        """, (json.dumps(payload, ensure_ascii=False), META_KEY, run_id))
        fenced_out = cur.rowcount == 0
        conn.commit()
    finally:
        cur.close()
        conn.close()
    if fenced_out:
        print(f"[runner] run_id 불일치(새 실행이 시작됨) — 상태 기록 생략")


def _touch(run_id):
    """실행 중 하트비트 — 같은 run_id 일 때만 updated_at 갱신."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE app_meta SET updated_at = NOW()
            WHERE key = %s AND (value::jsonb ->> 'run_id') = %s
        """, (META_KEY, run_id))
        conn.commit()
    finally:
        cur.close()
        conn.close()


def _read_status():
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT value FROM app_meta WHERE key = %s", (META_KEY,))
        row = cur.fetchone()
    finally:
        cur.close()
        conn.close()
    if not row or not row["value"]:
        return None
    try:
        return json.loads(row["value"])
    except (TypeError, ValueError):
        return None


def _tx_count():
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) AS c FROM transactions")
        return cur.fetchone()["c"]
    finally:
        cur.close()
        conn.close()


def main():
    global META_KEY
    parser = argparse.ArgumentParser()
    parser.add_argument("--meta-key", default=META_KEY,
                        help="상태를 기록할 app_meta 키 (기본 tx_sync_status)")
    parser.add_argument("--months", type=int, default=None,
                        help="sync_batch.py 에 전달할 --months (미지정 시 전달 안 함 → 기본 3개월)")
    args = parser.parse_args()
    META_KEY = args.meta_key

    status = _read_status()
    if not status or status.get("state") != "running":
        print("[runner] running 상태가 아니므로 종료합니다.")
        return
    run_id = status.get("run_id") or ""

    base_dir = os.path.dirname(os.path.abspath(__file__))
    tail = deque(maxlen=60)  # 실패 시 보여줄 마지막 출력 일부
    error = None

    try:
        cmd = [sys.executable, "-u", "sync_batch.py", "--master-only"]
        if args.months and args.months > 0:
            cmd += ["--months", str(int(args.months))]
        proc = subprocess.Popen(
            cmd,
            cwd=base_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )

        def _reader():
            for line in proc.stdout:
                line = line.rstrip()
                tail.append(line)
                # 하위 프로세스 출력을 그대로 러너 stdout으로 흘려보낸다.
                # (app.py가 러너 stdout을 logs/backfill_{run_id}.log 로 리다이렉트하면
                #  실패 원인 추적용 전체 로그가 파일로 남는다.)
                print(_redact(line), flush=True)
        t = threading.Thread(target=_reader, daemon=True)
        t.start()

        started = time.time()
        while proc.poll() is None:
            if time.time() - started > TIMEOUT_SEC:
                proc.kill()
                error = f"제한 시간({TIMEOUT_SEC // 3600}시간) 초과로 중단되었습니다."
                break
            try:
                _touch(run_id)
            except Exception:
                pass  # 하트비트 실패는 무시(다음 주기에 재시도)
            time.sleep(HEARTBEAT_SEC)
        proc.wait()
        t.join(timeout=10)

        if error is None and proc.returncode != 0:
            error = f"종료 코드 {proc.returncode}: " + _redact("\n".join(list(tail)[-8:]))[:600]
    except Exception as e:
        error = _redact(str(e))[:600]

    inserted = None
    try:
        before = status.get("tx_before")
        if before is not None:
            inserted = max(0, _tx_count() - before)
    except Exception:
        pass

    status.update({
        "state": "failed" if error else "done",
        "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "inserted": inserted,
        "error": error,
    })
    for attempt in range(3):  # DB 순간 장애 대비 재시도
        try:
            _write_status(status, run_id)
            break
        except Exception as e:
            print(f"[runner] 상태 저장 실패({attempt + 1}/3): {e}")
            time.sleep(5)
    print(f"[runner] 완료 — state={status['state']}, inserted={inserted}")


if __name__ == "__main__":
    main()
