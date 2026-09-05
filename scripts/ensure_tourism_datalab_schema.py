#!/usr/bin/env python3
"""Create only the shared Tourism Data Lab staging schema for production boot."""
import os
import sys
import psycopg2

LOCK_KEY = 719240392
DDL = """
CREATE TABLE IF NOT EXISTS tourism_datalab_stages (
 token TEXT PRIMARY KEY,
 admin_user_id INTEGER NOT NULL REFERENCES admin_users(id) ON DELETE CASCADE,
 manifest JSONB NOT NULL,
 manifest_hash TEXT NOT NULL,
 expires_at TIMESTAMPTZ NOT NULL,
 state TEXT NOT NULL CHECK (state IN ('previewed','applying','applied','failed')),
 attempt_count INTEGER NOT NULL DEFAULT 0,
 error_message TEXT,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 applied_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_tourism_datalab_stages_expiry
 ON tourism_datalab_stages (expires_at) WHERE state IN ('previewed','failed');
"""
VERIFY = """
SELECT
 (SELECT COUNT(*) = 10 FROM information_schema.columns
  WHERE table_schema=current_schema() AND table_name='tourism_datalab_stages'
    AND column_name = ANY(ARRAY['token','admin_user_id','manifest','manifest_hash','expires_at',
                                'state','attempt_count','error_message','created_at','applied_at']))
 AND EXISTS (
  SELECT 1 FROM pg_constraint
  WHERE conrelid='tourism_datalab_stages'::regclass AND contype='f'
    AND confrelid='admin_users'::regclass AND pg_get_constraintdef(oid) LIKE '%ON DELETE CASCADE%')
 AND EXISTS (
  SELECT 1 FROM pg_constraint
  WHERE conrelid='tourism_datalab_stages'::regclass AND contype='c'
    AND pg_get_constraintdef(oid) LIKE '%previewed%'
    AND pg_get_constraintdef(oid) LIKE '%applying%'
    AND pg_get_constraintdef(oid) LIKE '%applied%'
    AND pg_get_constraintdef(oid) LIKE '%failed%')
 AND to_regclass(current_schema() || '.idx_tourism_datalab_stages_expiry') IS NOT NULL
"""
def main():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is required")
    conn = psycopg2.connect(url)
    try:
        cur=conn.cursor()
        cur.execute("SELECT pg_advisory_xact_lock(%s)",(LOCK_KEY,))
        cur.execute(DDL)
        cur.execute(VERIFY)
        if not cur.fetchone()[0]: raise RuntimeError("tourism_datalab_stages verification failed")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
if __name__ == "__main__":
    try: main()
    except Exception as exc:
        print(f"tourism Data Lab schema failed: {exc}",file=sys.stderr); sys.exit(1)