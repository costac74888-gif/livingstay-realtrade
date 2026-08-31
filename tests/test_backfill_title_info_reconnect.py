import unittest
from unittest.mock import patch

import psycopg2

import backfill_title_info as backfill


class _Cursor:
    def __init__(self, targets=None, fail_update=False):
        self.targets = targets or []
        self.fail_update = fail_update
        self.rowcount = 1
        self.closed = False
        self.update_attempts = 0

    def execute(self, sql, _params=None):
        if "UPDATE master_buildings" in sql:
            self.update_attempts += 1
            if self.fail_update:
                self.fail_update = False
                raise psycopg2.OperationalError(
                    "SSL connection has been closed unexpectedly"
                )

    def fetchall(self):
        return self.targets

    def close(self):
        self.closed = True


class _Connection:
    def __init__(self, cursor, fail_commit=False):
        self._cursor = cursor
        self.fail_commit = fail_commit
        self.commits = 0
        self.closed = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.commits += 1
        if self.fail_commit:
            self.fail_commit = False
            raise psycopg2.OperationalError(
                "SSL connection has been closed unexpectedly"
            )

    def rollback(self):
        pass

    def close(self):
        self.closed = True


class _CursorFailConnection(_Connection):
    def cursor(self):
        raise psycopg2.OperationalError("server closed the connection")


class _Bjdong:
    def find_bjdong_cd(self, _sgg_cd, _umd_nm):
        return "10100"


class BackfillTitleInfoReconnectTests(unittest.TestCase):
    def setUp(self):
        self.target = {
            "id": 1,
            "building_name": "재접속 테스트",
            "sgg_cd": "11110",
            "umd_nm": "테스트동",
            "jibun": "1-1",
        }

    def test_ssl_disconnect_is_classified_as_connection_error(self):
        self.assertTrue(backfill._is_connection_error(
            psycopg2.OperationalError("SSL connection has been closed unexpectedly")
        ))
        self.assertFalse(backfill._is_connection_error(RuntimeError("API quota")))

    def test_reconnect_retries_temporary_connection_failure(self):
        old_cursor = _Cursor()
        old_conn = _Connection(old_cursor)
        new_cursor = _Cursor()
        new_conn = _Connection(new_cursor)

        with (
            patch.object(
                backfill,
                "get_conn",
                side_effect=[
                    psycopg2.OperationalError("server closed the connection"),
                    new_conn,
                ],
            ) as get_conn_mock,
            patch.object(backfill.time, "sleep") as sleep_mock,
        ):
            conn, cursor = backfill._reconnect(
                old_conn, old_cursor, attempts=2, base_delay=0.01
            )

        self.assertIs(conn, new_conn)
        self.assertIs(cursor, new_cursor)
        self.assertEqual(get_conn_mock.call_count, 2)
        sleep_mock.assert_called_once_with(0.01)

    def test_reconnect_releases_connection_when_cursor_creation_fails(self):
        old_cursor = _Cursor()
        old_conn = _Connection(old_cursor)
        bad_conn = _CursorFailConnection(_Cursor())
        good_cursor = _Cursor()
        good_conn = _Connection(good_cursor)

        with (
            patch.object(backfill, "get_conn", side_effect=[bad_conn, good_conn]),
            patch.object(backfill.time, "sleep"),
        ):
            conn, cursor = backfill._reconnect(
                old_conn, old_cursor, attempts=2, base_delay=0
            )

        self.assertTrue(bad_conn.closed)
        self.assertIs(conn, good_conn)
        self.assertIs(cursor, good_cursor)

    def test_retries_current_row_after_update_connection_drop(self):
        first_cursor = _Cursor([self.target], fail_update=True)
        first_conn = _Connection(first_cursor)
        second_cursor = _Cursor()
        second_conn = _Connection(second_cursor)
        state = {"conn": first_conn, "cur": first_cursor}

        with (
            patch.object(backfill, "get_conn", return_value=second_conn),
            patch.object(backfill, "_fetch_title_rows", return_value=[]),
            patch.object(backfill, "refresh_auto_building_names", return_value=0),
            patch.object(backfill.time, "sleep"),
        ):
            result = backfill._run_with_open_connection(
                bjdong=_Bjdong(),
                conn=first_conn,
                cur=first_cursor,
                db_state=state,
                sleep=0,
            )

        self.assertEqual(result, (0, 1, 0, 0))
        self.assertEqual(first_cursor.update_attempts, 1)
        self.assertEqual(second_cursor.update_attempts, 1)
        self.assertIs(state["conn"], second_conn)

    def test_replays_current_row_after_commit_connection_drop(self):
        first_cursor = _Cursor([self.target])
        first_conn = _Connection(first_cursor, fail_commit=True)
        second_cursor = _Cursor()
        second_conn = _Connection(second_cursor)
        state = {"conn": first_conn, "cur": first_cursor}

        with (
            patch.object(backfill, "get_conn", return_value=second_conn),
            patch.object(backfill, "_fetch_title_rows", return_value=[]),
            patch.object(backfill, "refresh_auto_building_names", return_value=0),
            patch.object(backfill.time, "sleep"),
        ):
            result = backfill._run_with_open_connection(
                bjdong=_Bjdong(),
                conn=first_conn,
                cur=first_cursor,
                db_state=state,
                sleep=0,
            )

        self.assertEqual(result, (0, 1, 0, 0))
        self.assertEqual(first_cursor.update_attempts, 1)
        self.assertEqual(second_cursor.update_attempts, 1)
        self.assertIs(state["conn"], second_conn)

    def test_does_not_resume_writes_after_reconnect_loses_run_ownership(self):
        first_cursor = _Cursor([self.target], fail_update=True)
        first_conn = _Connection(first_cursor)
        second_cursor = _Cursor()
        second_conn = _Connection(second_cursor)
        state = {"conn": first_conn, "cur": first_cursor}

        with (
            patch.object(backfill, "get_conn", return_value=second_conn),
            patch.object(backfill, "_fetch_title_rows", return_value=[]),
            patch.object(backfill, "_still_owner", return_value=False),
            patch.object(backfill.time, "sleep"),
        ):
            with self.assertRaisesRegex(RuntimeError, "실행 소유권이 변경"):
                backfill._run_with_open_connection(
                    bjdong=_Bjdong(),
                    conn=first_conn,
                    cur=first_cursor,
                    db_state=state,
                    sleep=0,
                    status_key="title_info_sync_status",
                    run_id="old-run",
                )

        self.assertEqual(second_cursor.update_attempts, 0)

    def test_retries_when_post_reconnect_owner_query_connection_drops(self):
        first_cursor = _Cursor([self.target], fail_update=True)
        first_conn = _Connection(first_cursor)
        second_cursor = _Cursor()
        second_conn = _Connection(second_cursor)
        third_cursor = _Cursor()
        third_conn = _Connection(third_cursor)
        state = {"conn": first_conn, "cur": first_cursor}

        with (
            patch.object(
                backfill, "get_conn", side_effect=[second_conn, third_conn]
            ),
            patch.object(backfill, "_fetch_title_rows", return_value=[]),
            patch.object(
                backfill,
                "_still_owner",
                side_effect=[
                    psycopg2.OperationalError("server closed the connection"),
                    True,
                ],
            ),
            patch.object(backfill, "refresh_auto_building_names", return_value=0),
            patch.object(backfill.time, "sleep"),
        ):
            result = backfill._run_with_open_connection(
                bjdong=_Bjdong(),
                conn=first_conn,
                cur=first_cursor,
                db_state=state,
                sleep=0,
                status_key="title_info_sync_status",
                run_id="same-run",
            )

        self.assertEqual(result, (0, 1, 0, 0))
        self.assertTrue(second_conn.closed)
        self.assertEqual(second_cursor.update_attempts, 0)
        self.assertEqual(third_cursor.update_attempts, 1)
        self.assertIs(state["conn"], third_conn)

    def test_run_closes_final_replacement_connection(self):
        first_cursor = _Cursor([self.target], fail_update=True)
        first_conn = _Connection(first_cursor)
        second_cursor = _Cursor()
        second_conn = _Connection(second_cursor)

        with (
            patch.object(backfill, "init_db"),
            patch.object(backfill, "BjdongMap", return_value=_Bjdong()),
            patch.object(backfill, "get_conn", side_effect=[first_conn, second_conn]),
            patch.object(backfill, "_fetch_title_rows", return_value=[]),
            patch.object(backfill, "refresh_auto_building_names", return_value=0),
            patch.object(backfill.time, "sleep"),
        ):
            result = backfill.run(sleep=0)

        self.assertEqual(result, (0, 1, 0, 0))
        self.assertTrue(first_conn.closed)
        self.assertTrue(second_conn.closed)
        self.assertTrue(second_cursor.closed)


if __name__ == "__main__":
    unittest.main()