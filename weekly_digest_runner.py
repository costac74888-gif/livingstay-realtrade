"""관리자 화면의 '이번 주 전체 발송' 버튼용 백그라운드 러너."""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime

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
    args = parser.parse_args()

    started_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    errors = []
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, f"weekly_digest_{args.run_id}.log")
    for cohort in ("tue", "thu"):
        with open(log_path, "a", encoding="utf-8") as log_file:
            result = subprocess.run(
                [sys.executable, "-u", "weekly_digest.py", "--cohort", cohort],
                cwd=os.path.dirname(os.path.abspath(__file__)),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                timeout=45 * 60,
                check=False,
            )
        if result.returncode:
            errors.append(f"{cohort} 그룹 발송 실패")

    counts = delivery_counts()
    payload = {
        "run_id": args.run_id,
        "state": "failed" if errors else "done",
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