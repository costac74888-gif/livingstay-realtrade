"""Operational ceilings, not invented official inspection-service quotas."""
import json
from datetime import datetime, timedelta

from db import get_conn
from quota_policy import KOREA_TZ, QuotaExhausted, korea_today

INSPECTION_KEY = "building_detail_inspection_budget"
BATCH_KEY = "building_detail_batch_budget"
INSPECTION_REQUEST_LIMIT = 1000


def next_reset():
    return (datetime.now(KOREA_TZ).replace(hour=0, minute=0, second=0, microsecond=0)
            + timedelta(days=1)).timestamp()


def reserve(key, cap):
    """Reserve before work, across restarts and workers. Failed attempts count."""
    if key not in (INSPECTION_KEY, BATCH_KEY) or cap <= 0:
        raise ValueError("Invalid detail budget")
    conn = get_conn()
    cur = conn.cursor()
    try:
        today = korea_today()
        cur.execute("""
            INSERT INTO app_meta(key,value,updated_at) VALUES(%s,%s,NOW())
            ON CONFLICT(key) DO UPDATE SET value=CASE
              WHEN app_meta.value::jsonb->>'date'=%s
              THEN jsonb_build_object('date',%s,'count',
                 COALESCE((app_meta.value::jsonb->>'count')::int,0)+1)::text
              ELSE EXCLUDED.value END, updated_at=NOW()
            WHERE app_meta.value::jsonb->>'date' IS DISTINCT FROM %s
               OR COALESCE((app_meta.value::jsonb->>'count')::int,0)<%s
            RETURNING (value::jsonb->>'count')::int AS count
        """, [key, json.dumps({"date": today, "count": 1}), today, today, today, cap])
        row = cur.fetchone()
        conn.commit()
        if not row:
            raise QuotaExhausted("상세 보강 일별 운영 예산 도달")
        return row["count"]
    finally:
        cur.close()
        conn.close()
