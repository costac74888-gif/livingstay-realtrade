"""프로세스 밖 통계 원본 캐시 무효화 신호."""

import json
from datetime import datetime

import psycopg2
import psycopg2.extras

from db import get_conn


MASTER_STATS_INVALIDATION_KEY = "master_stats_invalidation"


def mark_master_stats_invalidated(source, *, database_url=None):
    """커밋된 통계 원본 변경을 모든 앱 워커에 알린다."""
    conn = cur = None
    try:
        conn = (
            psycopg2.connect(database_url, cursor_factory=psycopg2.extras.RealDictCursor)
            if database_url else get_conn()
        )
        cur = conn.cursor()
        payload = json.dumps({
            "source": source,
            "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
        cur.execute("""
            INSERT INTO app_meta (key, value, updated_at) VALUES (%s, %s, NOW())
            ON CONFLICT (key) DO UPDATE
              SET value = EXCLUDED.value, updated_at = NOW()
        """, (MASTER_STATS_INVALIDATION_KEY, payload))
        conn.commit()
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()