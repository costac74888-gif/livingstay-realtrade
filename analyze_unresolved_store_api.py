"""One-off read-only store API analysis for unresolved general-lodging PNU targets."""
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import psycopg2

from store_info_util import get_stores_by_pnu

TARGETS = "/tmp/unresolved_store_targets.json"
OUTPUT = "/tmp/unresolved_store_results.jsonl"
DAILY_CAP = 6000
WORKERS = 3
lock = threading.Lock()


def reserve_call():
    today = datetime.now().strftime("%Y-%m-%d")
    fresh = json.dumps({"date": today, "count": 1})
    conn = psycopg2.connect(os.environ["PROD_DATABASE_URL"])
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO app_meta (key,value,updated_at)
                VALUES ('store_daily_calls_batch',%s,NOW())
                ON CONFLICT (key) DO UPDATE SET
                  value=CASE WHEN app_meta.value::jsonb->>'date'=%s
                    THEN jsonb_set(app_meta.value::jsonb,'{count}',
                      to_jsonb((app_meta.value::jsonb->>'count')::int+1))
                    ELSE %s::jsonb END,
                  updated_at=NOW()
                RETURNING (value::jsonb->>'count')::int
                """,
                (fresh, today, fresh),
            )
            count = cur.fetchone()[0]
            if count > DAILY_CAP:
                conn.rollback()
                return None
        conn.commit()
        return count
    finally:
        conn.close()


def fetch(pnu, ids):
    count = reserve_call()
    if count is None:
        return {"pnu": pnu, "ids": ids, "error": "daily_cap"}
    error = None
    for wait in (0, 10, 30):
        if wait:
            time.sleep(wait)
        try:
            stores = get_stores_by_pnu(pnu)
            return {"pnu": pnu, "ids": ids, "stores": stores, "call_count": count}
        except Exception as exc:
            error = str(exc)
    return {"pnu": pnu, "ids": ids, "error": error, "call_count": count}


def main():
    with open(TARGETS, encoding="utf-8") as f:
        targets = json.load(f)
    done = set()
    if os.path.exists(OUTPUT):
        with open(OUTPUT, encoding="utf-8") as f:
            for line in f:
                try:
                    done.add(json.loads(line)["pnu"])
                except Exception:
                    pass
    pending = [(pnu, ids) for pnu, ids in targets.items() if pnu not in done]
    print(f"[start] total={len(targets)} done={len(done)} pending={len(pending)}", flush=True)
    completed = len(done)
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(fetch, pnu, ids) for pnu, ids in pending]
        for future in as_completed(futures):
            row = future.result()
            with lock:
                with open(OUTPUT, "a", encoding="utf-8") as f:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
                completed += 1
                if completed % 25 == 0 or completed == len(targets):
                    print(f"[progress] {completed}/{len(targets)}", flush=True)
            time.sleep(0.25)
    print(f"[done] {completed}/{len(targets)} output={OUTPUT}", flush=True)


if __name__ == "__main__":
    main()