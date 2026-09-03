"""Shared production gate for legacy lodging collectors and cutover."""

from contextlib import contextmanager
import json

from db import get_conn


CONTROL_META_KEY = "lodging_legacy_sync_control"
CUTOVER_LOCK_ID = 9_182_991


@contextmanager
def legacy_lodging_writer_gate():
    """Hold a shared lock for a collector's full lifetime.

    The admin cutover takes the exclusive form of the same advisory lock, so
    it cannot commit the disabled flag while a legacy writer is active. Once
    disabled, later writers acquire the shared lock, observe the flag, and
    exit before claiming status or mutating data.
    """
    conn = get_conn()
    cur = conn.cursor()
    locked = False
    try:
        cur.execute(
            "SELECT pg_advisory_lock_shared(%s) AS acquired",
            (CUTOVER_LOCK_ID,),
        )
        cur.fetchone()
        locked = True
        cur.execute(
            "SELECT value FROM app_meta WHERE key=%s",
            (CONTROL_META_KEY,),
        )
        row = cur.fetchone()
        disabled = False
        if row and row["value"]:
            try:
                control = json.loads(row["value"])
                disabled = (
                    isinstance(control, dict)
                    and control.get("enabled") is False
                )
            except (TypeError, ValueError):
                disabled = False
        yield not disabled
    finally:
        if locked:
            try:
                cur.execute(
                    "SELECT pg_advisory_unlock_shared(%s) AS released",
                    (CUTOVER_LOCK_ID,),
                )
                cur.fetchone()
            except Exception:
                pass
        cur.close()
        conn.close()