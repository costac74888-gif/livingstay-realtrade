"""db 연결 풀의 재사용·정리·fork 안전성을 DB 없이 검증한다."""

import os
import sys
import unittest
import gc
from unittest.mock import MagicMock, patch

from psycopg2.pool import PoolError

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import db

os.environ.setdefault("FLASK_SECRET_KEY", "connection-pool-test-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://invalid/test")
with patch.object(db, "init_db"), patch("threading.Thread.start"):
    import app as app_module


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


class _ClusterCursor:
    def __init__(self, pool):
        self.pool = pool
        self.close_count = 0
        self.executed = False

    def execute(self, _sql, _params=None):
        self.executed = True
        if self.pool.fail_sql:
            raise RuntimeError("simulated cluster SQL failure")

    def fetchall(self):
        return [{
            "region_name": "서울특별시",
            "sgg_text_full": None,
            "lat": 37.5,
            "lng": 127.0,
            "total": 1,
            "cnt_live": 1,
            "cnt_tour": 0,
            "cnt_gen": 0,
            "cnt_mixed": 0,
            "cnt_pre_completion": 0,
            "cnt_unknown": 0,
        }]

    def close(self):
        self.close_count += 1
        if self.close_count > 1:
            raise AssertionError("cluster cursor was closed more than once")
        if self.pool.cursor_close_failures:
            self.pool.cursor_close_failures -= 1
            raise RuntimeError("simulated cluster cursor close failure")


class _BoundedClusterConnection:
    def __init__(self, pool):
        self.pool = pool
        self.closed = 0
        self.autocommit = False
        self.rollback_count = 0
        self.cursors = []

    def cursor(self):
        cursor = _ClusterCursor(self.pool)
        self.cursors.append(cursor)
        return cursor

    def rollback(self):
        self.rollback_count += 1


class _BoundedClusterPool:
    """최대 1개 대여만 허용해 반환 누락을 즉시 드러내는 모의 풀."""

    def __init__(self, *, fail_sql=False, cursor_close_failures=0):
        self.fail_sql = fail_sql
        self.cursor_close_failures = cursor_close_failures
        self.connection = _BoundedClusterConnection(self)
        self.available = [self.connection]
        self.checked_out = 0
        self.peak_checked_out = 0
        self.get_count = 0
        self.put_count = 0

    def getconn(self):
        if not self.available:
            raise PoolError("simulated connection pool exhausted")
        self.get_count += 1
        connection = self.available.pop()
        self.checked_out += 1
        self.peak_checked_out = max(self.peak_checked_out, self.checked_out)
        return connection

    def putconn(self, connection, close=False):
        self.put_count += 1
        self.checked_out -= 1
        if self.checked_out < 0:
            raise AssertionError("connection returned more than once")
        if not close:
            self.available.append(connection)


class ClusterConnectionCleanupTests(unittest.TestCase):
    def setUp(self):
        _reset_pool_state()
        app_module._cluster_cache.clear()
        app_module.app.config.update(
            TESTING=False,
            SECRET_KEY="connection-pool-test-secret",
            RATELIMIT_ENABLED=False,
        )
        app_module.limiter.reset()

    def tearDown(self):
        app_module._cluster_cache.clear()
        _reset_pool_state()

    def _run_cluster_request(self, pool, **query_string):
        with patch.object(db, "ThreadedConnectionPool", return_value=pool):
            with app_module.app.test_client() as client:
                return client.get(
                    "/api/buildings-cluster",
                    query_string={"level": "sido", **query_string},
                )

    def test_normal_cluster_query_closes_cursor_and_returns_connection_once(self):
        pool = _BoundedClusterPool()

        response = self._run_cluster_request(pool, q="normal-query")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(pool.get_count, 1)
        self.assertEqual(pool.put_count, 1)
        self.assertEqual(pool.checked_out, 0)
        self.assertEqual(pool.connection.cursors[0].close_count, 1)
        self.assertEqual(pool.connection.rollback_count, 1)

    def test_sql_error_closes_cursor_and_returns_connection_once(self):
        pool = _BoundedClusterPool(fail_sql=True)

        response = self._run_cluster_request(pool, q="sql-error-query")

        self.assertEqual(response.status_code, 500)
        self.assertEqual(pool.get_count, 1)
        self.assertEqual(pool.put_count, 1)
        self.assertEqual(pool.checked_out, 0)
        self.assertEqual(pool.connection.cursors[0].close_count, 1)
        self.assertEqual(pool.connection.rollback_count, 1)

    def test_cursor_close_failure_returns_connection_before_request_teardown(self):
        pool = _BoundedClusterPool(cursor_close_failures=1)

        with patch.object(db, "ThreadedConnectionPool", return_value=pool):
            with app_module.app.test_request_context(
                "/api/buildings-cluster",
                query_string={"level": "sido", "q": "cursor-close-failure"},
            ):
                with self.assertRaisesRegex(RuntimeError, "cursor close failure"):
                    app_module.get_buildings_cluster()
                # 요청 teardown의 보조 회수에 기대지 않고 라우트 finally에서 즉시 반환한다.
                self.assertEqual(pool.put_count, 1)
                self.assertEqual(pool.checked_out, 0)

            with app_module.app.test_request_context(
                "/api/buildings-cluster",
                query_string={"level": "sido", "q": "recovered-after-close-failure"},
            ):
                recovered = app_module.get_buildings_cluster()

        self.assertEqual(recovered.status_code, 200)
        self.assertEqual(pool.get_count, 2)
        self.assertEqual(pool.put_count, 2)
        self.assertEqual(pool.checked_out, 0)
        self.assertEqual(pool.peak_checked_out, 1)
        self.assertTrue(all(cursor.close_count == 1 for cursor in pool.connection.cursors))

    def test_repeated_cache_misses_do_not_exhaust_bounded_pool(self):
        pool = _BoundedClusterPool()

        with patch.object(db, "ThreadedConnectionPool", return_value=pool):
            with app_module.app.test_client() as client:
                responses = [
                    client.get(
                        "/api/buildings-cluster",
                        query_string={"level": "sido", "q": f"unique-query-{index}"},
                    )
                    for index in range(8)
                ]

        self.assertTrue(all(response.status_code == 200 for response in responses))
        self.assertEqual(pool.get_count, 8)
        self.assertEqual(pool.put_count, 8)
        self.assertEqual(pool.checked_out, 0)
        self.assertEqual(pool.peak_checked_out, 1)
        self.assertTrue(all(cursor.close_count == 1 for cursor in pool.connection.cursors))
        self.assertEqual(pool.connection.rollback_count, 8)


if __name__ == "__main__":
    unittest.main(verbosity=2)