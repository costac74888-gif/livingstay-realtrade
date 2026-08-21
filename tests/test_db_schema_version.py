"""db.init_db()의 스키마 버전 빠른 경로와 동시 기동 보호를 검증한다."""

from contextlib import contextmanager
import os
import sys
import unittest
from unittest.mock import MagicMock, call, patch

import psycopg2

# `python tests/test_db_schema_version.py`로 실행해도 프로젝트 모듈을 찾는다.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import db


def _connection_with_row(row=None):
    conn = MagicMock()
    cur = MagicMock()
    cur.fetchone.return_value = row
    conn.cursor.return_value = cur
    return conn, cur


class SchemaVersionGateTests(unittest.TestCase):
    def test_current_version_skips_lock_and_full_initialization(self):
        conn, cur = _connection_with_row({"value": db.SCHEMA_VERSION})
        with (
            patch("db.get_conn", return_value=conn),
            patch("db._schema_initialization_lock") as lock,
            patch("db._run_init_db") as run_full,
        ):
            db.init_db()

        lock.assert_not_called()
        run_full.assert_not_called()
        conn.rollback.assert_called_once()
        cur.close.assert_called_once()
        conn.close.assert_called_once()

    def test_missing_app_meta_is_treated_as_outdated_schema(self):
        conn, cur = _connection_with_row()
        cur.execute.side_effect = psycopg2.ProgrammingError("relation app_meta does not exist")

        self.assertFalse(db._schema_version_is_current(conn, cur))
        conn.rollback.assert_called_once()

    def test_waiting_worker_rechecks_version_before_running_full_ddl(self):
        first_conn, first_cur = _connection_with_row()
        lock_conn, lock_cur = _connection_with_row()

        @contextmanager
        def held_lock():
            yield lock_conn

        with (
            patch("db.get_conn", return_value=first_conn),
            patch("db._schema_initialization_lock", held_lock),
            patch("db._schema_version_is_current", side_effect=[False, True]),
            patch("db._run_init_db") as run_full,
        ):
            db.init_db()

        run_full.assert_not_called()
        first_cur.close.assert_called_once()
        lock_cur.close.assert_called_once()

    def test_outdated_schema_runs_full_initialization_once_under_lock(self):
        first_conn, first_cur = _connection_with_row()
        lock_conn, lock_cur = _connection_with_row()

        @contextmanager
        def held_lock():
            yield lock_conn

        with (
            patch("db.get_conn", return_value=first_conn),
            patch("db._schema_initialization_lock", held_lock),
            patch("db._schema_version_is_current", side_effect=[False, False]),
            patch("db._run_init_db") as run_full,
        ):
            db.init_db()

        run_full.assert_called_once_with()
        first_cur.close.assert_called_once()
        lock_cur.close.assert_called_once()

    def test_advisory_lock_is_released_after_initialization(self):
        conn, cur = _connection_with_row()
        with patch("db.get_conn", return_value=conn):
            with db._schema_initialization_lock():
                pass

        self.assertEqual(
            cur.execute.call_args_list,
            [
                call("SELECT pg_advisory_lock(%s)", (db._SCHEMA_INIT_ADVISORY_LOCK_KEY,)),
                call("SELECT pg_advisory_unlock(%s)", (db._SCHEMA_INIT_ADVISORY_LOCK_KEY,)),
            ],
        )
        self.assertEqual(conn.commit.call_count, 2)
        cur.close.assert_called_once()
        conn.close.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)