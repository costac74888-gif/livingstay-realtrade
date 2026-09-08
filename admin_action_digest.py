#!/usr/bin/env python3
"""Cron entry point for the KST administrator action-centre daily digest."""
import logging
from db import get_conn
from admin_action_center import dispatch_pending_immediate, send_daily_digest

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def main():
    conn = cur = None
    try:
        conn = get_conn()
        cur = conn.cursor()
        dispatched, failures = dispatch_pending_immediate(conn, cur)
        logging.info("admin immediate outbox: dispatched=%s failures=%s", dispatched, failures)
        sent, message = send_daily_digest(conn, cur)
        logging.info("admin action digest: sent=%s (%s)", sent, message)
        digest_failed = not sent and message not in {"no actionable items", "already delivered"}
        return 1 if failures or digest_failed else 0
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

if __name__ == "__main__":
    raise SystemExit(main())