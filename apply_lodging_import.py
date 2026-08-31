#!/usr/bin/env python3
"""Apply one claimed lodging-import staging record in a detached process."""

import argparse
import os
import tempfile
import threading
from contextlib import contextmanager

import psycopg2.extras

from db import get_conn
from lodging_import_staging import run_import
from sync_lodgings import _lodging_sync_lock
from sync_rural_hanok import _source_lock_ids


@contextmanager
def _import_lock(source):
    """Use the same lock contract as the collector that owns this source."""
    if source not in {"rural", "hanok"}:
        with _lodging_sync_lock() as acquired:
            yield acquired
        return

    conn = get_conn()
    cur = conn.cursor()
    lock_id = _source_lock_ids([source])[0]
    acquired = False
    try:
        cur.execute("SELECT pg_try_advisory_lock(%s) AS acquired", (lock_id,))
        acquired = bool(cur.fetchone()["acquired"])
        yield acquired
    finally:
        if acquired:
            try:
                cur.execute("SELECT pg_advisory_unlock(%s) AS released", (lock_id,))
                cur.fetchone()
            except Exception:
                pass
        cur.close()
        conn.close()


def _finish(token, run_id, status, *, result=None, error=None):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE lodging_import_staging
               SET status=%s, result=%s, error=%s, finished_at=NOW(),
                   heartbeat_at=NOW(),
                   file_data=CASE WHEN %s='done' THEN decode('', 'hex') ELSE file_data END
             WHERE token=%s AND status='applying' AND run_id=%s
            """,
            (status, psycopg2.extras.Json(result) if result is not None else None,
             error, status, token, run_id),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def _heartbeat(token, run_id, stop):
    while not stop.wait(30):
        conn = get_conn()
        cur = conn.cursor()
        try:
            cur.execute(
                """
                UPDATE lodging_import_staging SET heartbeat_at=NOW()
                 WHERE token=%s AND status='applying' AND run_id=%s
                """,
                (token, run_id),
            )
            conn.commit()
        except Exception:
            conn.rollback()
        finally:
            cur.close()
            conn.close()


def main(token, run_id):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT source, file_ext, file_data
              FROM lodging_import_staging
             WHERE token=%s AND status='applying' AND run_id=%s
            """,
            (token, run_id),
        )
        row = cur.fetchone()
    finally:
        cur.close()
        conn.close()
    if not row:
        return 2

    path = None
    stop = threading.Event()
    threading.Thread(target=_heartbeat, args=(token, run_id, stop), daemon=True).start()
    try:
        with tempfile.NamedTemporaryFile(
            prefix="lodging-import-", suffix=f".{row['file_ext']}", delete=False
        ) as handle:
            handle.write(bytes(row["file_data"]))
            path = handle.name
        with _import_lock(row["source"]) as acquired:
            if not acquired:
                raise RuntimeError(
                    "같은 숙박 원본의 API 동기화 또는 파일 반영이 실행 중입니다. "
                    "완료 후 다시 승인해 주세요."
                )
            result = run_import(row["source"], path)
        if int((result or {}).get("failed") or 0) > 0:
            _finish(
                token, run_id,
                "failed",
                result=result,
                error=f"{result['failed']}개 행 반영 실패",
            )
            return 1
        _finish(token, run_id, "done", result=result)
        return 0
    except Exception as exc:
        _finish(token, run_id, "failed", error=str(exc)[:1000])
        return 1
    finally:
        stop.set()
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("token")
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    raise SystemExit(main(args.token, args.run_id))