"""관리자 주간 이메일 대표 테스트와 전체 발송 백그라운드 러너."""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import psycopg2
import psycopg2.extras


def get_conn():
    return psycopg2.connect(
        os.environ["DATABASE_URL"],
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


def write_status(status_key, run_id, payload):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE app_meta
               SET value=%s, updated_at=NOW()
             WHERE key=%s
               AND value::jsonb ->> 'run_id'=%s
            """,
            (json.dumps(payload, ensure_ascii=False), status_key, run_id),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def delivery_counts():
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT status, COUNT(*) AS count
              FROM weekly_email_deliveries
             WHERE week_start=date_trunc(
                       'week', (NOW() AT TIME ZONE 'Asia/Seoul')
                   )::date
             GROUP BY status
            """
        )
        return {row["status"]: int(row["count"]) for row in cur.fetchall()}
    finally:
        cur.close()
        conn.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--status-key", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()

    started_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    seoul_today = datetime.now(ZoneInfo("Asia/Seoul")).date()
    week_start = (seoul_today - timedelta(days=seoul_today.weekday())).isoformat()
    errors = []
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, f"weekly_digest_{args.run_id}.log")
    cohorts = (None,) if args.test else ("tue", "thu")
    for cohort in cohorts:
        command = [sys.executable, "-u", "weekly_digest.py"]
        command += ["--manual-test"] if cohort is None else ["--manual-all", "--cohort", cohort]
        try:
            with open(log_path, "a", encoding="utf-8") as log_file:
                result = subprocess.run(
                    command,
                    cwd=os.path.dirname(os.path.abspath(__file__)),
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    timeout=45 * 60,
                    check=False,
                )
            failed = result.returncode != 0
        except (OSError, subprocess.TimeoutExpired):
            failed = True
        if failed:
            errors.append("대표 테스트 발송 실패" if cohort is None else f"{cohort} 그룹 발송 실패")
            if args.test:
                break

    counts = delivery_counts()
    payload = {
        "run_id": args.run_id,
        "state": "failed" if errors else ("test_ready" if args.test else "done"),
        "week_start": week_start if args.test and not errors else None,
        "started_at": started_at,
        "finished_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "sent": counts.get("sent", 0),
        "failed": counts.get("failed", 0),
        "sending": counts.get("sending", 0),
        "error": "; ".join(errors) if errors else None,
    }
    write_status(args.status_key, args.run_id, payload)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())