"""db 연결 풀의 재사용·정리·fork 안전성을 DB 없이 검증한다."""

import os
import sys
import unittest
import gc
from unittest.mock import MagicMock, patch

from psycopg2.pool import PoolError

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import db


def _reset_pool_state():
    with db._connection_pool_lock:
        db._connection_pool = None
        db._connection_pool_pid = None
        db._borrowed_connections.clear()


class ConnectionPoolTests(unittest.TestCase):
    def setUp(self):
        _reset_pool_state()

    def tearDown(self):
        _reset_pool_state()

    def _raw_connection(self):
        raw = MagicMock()
        raw.closed = 0
        return raw

    def test_checkout_is_lazy_and_close_returns_connection_to_pool(self):
        raw = self._raw_connection()
        pool = MagicMock()
        pool.getconn.return_value = raw

        with patch("db.ThreadedConnectionPool", return_value=pool) as pool_class:
            conn = db.get_conn()
            conn.close()  # 기존 호출부 호환 경로

        pool_class.assert_called_once()
        raw.rollback.assert_called_once_with()
        pool.putconn.assert_called_once_with(raw, close=False)
        raw.close.assert_not_called()

    def test_release_is_idempotent(self):
        raw = self._raw_connection()
        pool = MagicMock()
        pool.getconn.return_value = raw

        with patch("db.ThreadedConnectionPool", return_value=pool):
            conn = db.get_conn()
            db.release_conn(conn)
            db.release_conn(conn)

        self.assertEqual(pool.putconn.call_count, 1)

    def test_stale_wrapper_cannot_return_a_newer_lease(self):
        raw = self._raw_connection()
        pool = MagicMock()
        pool.getconn.return_value = raw

        with patch("db.ThreadedConnectionPool", return_value=pool):
            stale_conn = db.get_conn()
            newer_conn = db._PooledConnection(raw)
            with db._connection_pool_lock:
                _, pid, _ = db._borrowed_connections[id(raw)]
                db._borrowed_connections[id(raw)] = (pool, pid, newer_conn._lease_token)

            db.release_conn(stale_conn)
            pool.putconn.assert_not_called()
            db.release_conn(newer_conn)

        pool.putconn.assert_called_once_with(raw, close=False)

    def test_unclosed_request_connection_is_released_at_teardown(self):
        from flask import Flask

        raw = self._raw_connection()
        pool = MagicMock()
        pool.getconn.return_value = raw
        app = Flask(__name__)
        app.teardown_request(lambda _error: db.release_request_connections())

        with patch("db.ThreadedConnectionPool", return_value=pool):
            with app.test_request_context("/"):
                db.get_conn()  # legacy handler omitted close()

        pool.putconn.assert_called_once_with(raw, close=False)

    def test_legacy_unclosed_batch_connection_is_released_safely(self):
        raw = self._raw_connection()
        pool = MagicMock()
        pool.getconn.return_value = raw

        with patch("db.ThreadedConnectionPool", return_value=pool):
            conn = db.get_conn()
            del conn
            gc.collect()

        pool.putconn.assert_called_once_with(raw, close=False)

    def test_failed_rollback_discards_connection(self):
        raw = self._raw_connection()
        raw.rollback.side_effect = RuntimeError("broken connection")
        pool = MagicMock()
        pool.getconn.return_value = raw

        with patch("db.ThreadedConnectionPool", return_value=pool):
            conn = db.get_conn()
            db.release_conn(conn)

        pool.putconn.assert_called_once_with(raw, close=True)

    def test_release_restores_transaction_mode_before_reuse(self):
        raw = self._raw_connection()
        raw.autocommit = True
        pool = MagicMock()
        pool.getconn.return_value = raw

        with patch("db.ThreadedConnectionPool", return_value=pool):
            ddl_conn = db.get_conn()
            ddl_conn.close()
            next_conn = db.get_conn()
            try:
                self.assertFalse(next_conn.autocommit)
            finally:
                next_conn.close()

        self.assertFalse(raw.autocommit)
        self.assertEqual(pool.putconn.call_count, 2)

    def test_pool_exhaustion_is_raised_to_the_caller(self):
        pool = MagicMock()
        pool.getconn.side_effect = PoolError("connection pool exhausted")

        with patch("db.ThreadedConnectionPool", return_value=pool):
            with self.assertRaises(PoolError):
                db.get_conn()

    def test_child_process_reset_never_reuses_parent_pool(self):
        parent_pool = MagicMock()
        child_pool = MagicMock()
        parent_raw = self._raw_connection()
        child_raw = self._raw_connection()
        parent_pool.getconn.return_value = parent_raw
        child_pool.getconn.return_value = child_raw

        with patch("db.os.getpid", side_effect=[101, 101, 101, 202, 202]), patch(
            "db.ThreadedConnectionPool", side_effect=[parent_pool, child_pool]
        ) as pool_class:
            parent_conn = db.get_conn()
            parent_conn.close()
            db._reset_connection_pool_after_fork()
            child_conn = db.get_conn()

        self.assertIsNot(parent_conn._raw_connection, child_conn._raw_connection)
        self.assertEqual(pool_class.call_count, 2)
        parent_pool.closeall.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)