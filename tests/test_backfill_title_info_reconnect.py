"""건축정보 백필의 PostgreSQL 연결 단절 복구를 DB 없이 검증한다."""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

import psycopg2

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import backfill_title_info as title_info


def _building(building_id):
    return {
        "id": building_id,
        "building_name": f"테스트건물{building_id}",
        "sgg_cd": "11110",
        "umd_nm": "청운효자동",
        "jibun": "1",
    }


def _title_row():
    return {
        "bldNm": "테스트건물",
        "dongNm": "",
        "mainPurpsCdNm": "숙박시설",
        "hoCnt": "1",
        "useAprDay": "20240101",
        "totArea": "100",
        "mgmBldrgstPk": "11110-10000-1",
    }


class BackfillReconnectTests(unittest.TestCase):
    def test_disconnect_retries_current_building_without_reprocessing_checkpoint(self):
        """건물 1 커밋 뒤 단절되면 건물 2부터 재시도하고 정상 완료한다."""
        initial_conn = MagicMock()
        initial_conn.closed = 0
        initial_cur = MagicMock()
        replacement_conn = MagicMock()
        replacement_conn.closed = 0
        replacement_cur = MagicMock()
        replacement_conn.cursor.return_value = replacement_cur

        targets = [_building(1), _building(2)]
        initial_cur.fetchall.return_value = targets
        update_attempts = []
        initial_update_count = 0

        def initial_execute(sql, params=None):
            nonlocal initial_update_count
            if sql.lstrip().startswith("SELECT id, building_name"):
                return
            building_id = params["id"]
            update_attempts.append(building_id)
            initial_update_count += 1
            if building_id == 2:
                initial_conn.closed = 1
                raise psycopg2.OperationalError(
                    "SSL connection has been closed unexpectedly"
                )
            initial_cur.rowcount = 1

        def replacement_execute(sql, params=None):
            building_id = params["id"]
            update_attempts.append(building_id)
            replacement_cur.rowcount = 1

        initial_cur.execute.side_effect = initial_execute
        replacement_cur.execute.side_effect = replacement_execute
        bjdong = MagicMock()
        bjdong.find_bjdong_cd.return_value = "10100"
        connection_state = {"conn": initial_conn, "cur": initial_cur}

        with (
            patch.object(title_info, "get_conn", return_value=replacement_conn),
            patch.object(title_info, "_fetch_title_rows", return_value=[_title_row()]) as fetch,
            patch.object(title_info, "resolve_api_building_name", return_value="테스트건물"),
            patch.object(title_info, "refresh_auto_building_names", return_value=0),
            patch.object(title_info, "mark_master_stats_invalidated"),
            patch.object(title_info.time, "sleep"),
        ):
            result = title_info._run_with_open_connection(
                only_missing=True,
                sleep=0,
                bjdong=bjdong,
                conn=initial_conn,
                cur=initial_cur,
                connection_state=connection_state,
            )

        self.assertEqual(result, (2, 0, 0, 0))
        self.assertEqual(update_attempts, [1, 2, 2])
        self.assertEqual(fetch.call_count, 3)
        self.assertEqual(initial_conn.commit.call_count, 1)
        self.assertEqual(replacement_conn.commit.call_count, 1)
        self.assertIs(connection_state["conn"], replacement_conn)
        initial_conn.close.assert_called()

    def test_reconnect_success_is_recorded_after_transient_failures(self):
        status = {
            "run_id": "run-1",
            "state": "running",
            "reconnect_count": 0,
            "reconnect_attempts": 0,
        }
        replacement_conn = MagicMock()
        replacement_cur = MagicMock()
        replacement_conn.cursor.return_value = replacement_cur
        writes = []

        def capture_status(_key, payload, _run_id):
            writes.append(dict(payload))

        with (
            patch.object(title_info, "MAX_DB_RECONNECT_ATTEMPTS", 3),
            patch.object(
                title_info,
                "get_conn",
                side_effect=[
                    psycopg2.OperationalError("temporary outage"),
                    replacement_conn,
                ],
            ),
            patch.object(title_info, "_read_status", return_value=status),
            patch.object(title_info, "_write_status", side_effect=capture_status),
            patch.object(title_info, "_still_owner", return_value=True),
            patch.object(title_info.time, "sleep"),
        ):
            conn, cur = title_info._reconnect_connection(
                MagicMock(),
                MagicMock(),
                status_key="title-info-status",
                run_id="run-1",
            )

        self.assertIs(conn, replacement_conn)
        self.assertIs(cur, replacement_cur)
        self.assertEqual(writes[-1]["connection_state"], "connected")
        self.assertEqual(writes[-1]["reconnect_count"], 1)
        self.assertEqual(writes[-1]["reconnect_attempts"], 2)
        self.assertIsNone(writes[-1]["last_reconnect_error"])

    def test_reconnect_exhaustion_records_final_failure(self):
        status = {
            "run_id": "run-2",
            "state": "running",
            "reconnect_count": 0,
            "reconnect_attempts": 0,
        }
        writes = []

        def capture_status(_key, payload, _run_id):
            writes.append(dict(payload))

        with (
            patch.object(title_info, "MAX_DB_RECONNECT_ATTEMPTS", 2),
            patch.object(
                title_info,
                "get_conn",
                side_effect=psycopg2.OperationalError("database unavailable"),
            ),
            patch.object(title_info, "_read_status", return_value=status),
            patch.object(title_info, "_write_status", side_effect=capture_status),
            patch.object(title_info.time, "sleep"),
        ):
            with self.assertRaises(title_info._DatabaseReconnectExhausted):
                title_info._reconnect_connection(
                    MagicMock(),
                    MagicMock(),
                    status_key="title-info-status",
                    run_id="run-2",
                )

        self.assertEqual(writes[-1]["connection_state"], "failed")
        self.assertEqual(writes[-1]["reconnect_attempts"], 2)
        self.assertEqual(writes[-1]["reconnect_failures"], 2)
        self.assertIn("성공 0회, 실패 2회", writes[-1]["last_reconnect_error"])
        self.assertEqual(writes[-1]["error"], writes[-1]["last_reconnect_error"])

    def test_reconnect_stops_when_run_ownership_changed(self):
        status = {"run_id": "old-run", "state": "running"}
        replacement_conn = MagicMock()
        replacement_cur = MagicMock()
        replacement_conn.cursor.return_value = replacement_cur

        with (
            patch.object(title_info, "get_conn", return_value=replacement_conn),
            patch.object(title_info, "_read_status", return_value=status),
            patch.object(title_info, "_write_status"),
            patch.object(title_info, "_still_owner", return_value=False),
        ):
            with self.assertRaisesRegex(
                title_info._RunOwnershipLost, "실행 소유권이 변경"
            ):
                title_info._reconnect_connection(
                    MagicMock(),
                    MagicMock(),
                    status_key="title-info-status",
                    run_id="old-run",
                )

        replacement_conn.close.assert_called_once_with()

    def test_reconnect_budget_is_shared_across_multiple_disconnects(self):
        reconnect_state = {"attempts": 0, "successes": 0, "failures": 0}
        replacement_connections = [MagicMock(), MagicMock()]
        for connection in replacement_connections:
            connection.cursor.return_value = MagicMock()

        with (
            patch.object(title_info, "MAX_DB_RECONNECT_ATTEMPTS", 2),
            patch.object(
                title_info,
                "get_conn",
                side_effect=replacement_connections,
            ) as get_conn,
        ):
            title_info._reconnect_connection(
                MagicMock(),
                MagicMock(),
                reconnect_state=reconnect_state,
            )
            title_info._reconnect_connection(
                replacement_connections[0],
                replacement_connections[0].cursor.return_value,
                reconnect_state=reconnect_state,
            )
            with self.assertRaises(title_info._DatabaseReconnectExhausted):
                title_info._reconnect_connection(
                    replacement_connections[1],
                    replacement_connections[1].cursor.return_value,
                    reconnect_state=reconnect_state,
                )

        self.assertEqual(get_conn.call_count, 2)
        self.assertEqual(
            reconnect_state,
            {"attempts": 2, "successes": 2, "failures": 0},
        )

    def test_commit_response_loss_does_not_rewrite_completed_checkpoint(self):
        initial_conn = MagicMock()
        initial_conn.closed = 0
        initial_cur = MagicMock()
        initial_cur.fetchall.return_value = [_building(1)]
        replacement_conn = MagicMock()
        replacement_conn.closed = 0
        replacement_cur = MagicMock()
        replacement_conn.cursor.return_value = replacement_cur
        update_sql = []

        def initial_execute(sql, params=None):
            if sql.lstrip().startswith("SELECT id, building_name"):
                return
            update_sql.append(sql)
            initial_cur.rowcount = 1

        def replacement_execute(sql, params=None):
            update_sql.append(sql)
            # 첫 commit이 서버에는 반영됐으므로 조건부 재시도는 0건이어야 한다.
            replacement_cur.rowcount = 0

        initial_cur.execute.side_effect = initial_execute
        replacement_cur.execute.side_effect = replacement_execute
        initial_conn.commit.side_effect = psycopg2.OperationalError(
            "SSL connection has been closed unexpectedly"
        )
        bjdong = MagicMock()
        bjdong.find_bjdong_cd.return_value = "10100"

        with (
            patch.object(title_info, "get_conn", return_value=replacement_conn),
            patch.object(title_info, "_fetch_title_rows", return_value=[_title_row()]),
            patch.object(title_info, "resolve_api_building_name", return_value="테스트건물"),
            patch.object(title_info, "refresh_auto_building_names", return_value=0),
            patch.object(title_info, "mark_master_stats_invalidated"),
            patch.object(title_info.time, "sleep"),
        ):
            result = title_info._run_with_open_connection(
                ids=[1],
                only_missing=True,
                sleep=0,
                bjdong=bjdong,
                conn=initial_conn,
                cur=initial_cur,
            )

        self.assertEqual(result, (1, 0, 0, 0))
        self.assertEqual(len(update_sql), 2)
        self.assertTrue(
            all("title_backfilled_at IS NULL" in sql for sql in update_sql)
        )
        replacement_conn.commit.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()