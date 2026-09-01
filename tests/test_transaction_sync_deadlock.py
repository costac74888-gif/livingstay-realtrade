import unittest
from pathlib import Path
from unittest.mock import patch

import psycopg2

import db
import sync_batch


class _Connection:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class _LockCursor:
    def __init__(self, acquired):
        self.results = iter([
            {"acquired": acquired},
            {"acquired": None},
        ])
        self.queries = []

    def execute(self, query, params):
        self.queries.append((query, params))

    def fetchone(self):
        return next(self.results)


class TransactionSyncDeadlockTests(unittest.TestCase):
    def test_writer_lock_starts_immediately_when_available(self):
        cur = _LockCursor(True)

        sync_batch._acquire_rtms_writer_lock(cur)

        self.assertEqual(len(cur.queries), 1)
        self.assertIn("pg_try_advisory_lock", cur.queries[0][0])

    def test_writer_lock_waits_instead_of_failing_when_busy(self):
        cur = _LockCursor(False)

        sync_batch._acquire_rtms_writer_lock(cur)

        self.assertEqual(len(cur.queries), 2)
        self.assertIn("pg_try_advisory_lock", cur.queries[0][0])
        self.assertIn("pg_advisory_lock", cur.queries[1][0])

    def test_recent_sync_runner_skips_address_prepare_only_for_recent_status(self):
        source = Path("sync_runner.py").read_text(encoding="utf-8")
        self.assertIn('if META_KEY == "tx_sync_status":', source)
        self.assertIn('cmd.append("--skip-address-prepare")', source)

    def test_transaction_scope_uses_rtms_building_type(self):
        self.assertEqual(
            sync_batch.transaction_scope_for_trade({"buildingType": "일반"}),
            "whole_building",
        )
        self.assertEqual(
            sync_batch.transaction_scope_for_trade({"buildingType": "집합"}),
            "unit",
        )
        self.assertEqual(sync_batch.transaction_scope_for_trade({}), "unit")

    def test_whole_building_requires_one_exact_general_lodging_master(self):
        exact = [{"lodging_type": "일반"}]
        self.assertIsNone(sync_batch.whole_building_match_reason(exact))
        self.assertEqual(
            sync_batch.whole_building_match_reason([]),
            "no_exact_master",
        )
        self.assertEqual(
            sync_batch.whole_building_match_reason([*exact, *exact]),
            "ambiguous_exact_master",
        )
        self.assertEqual(
            sync_batch.whole_building_match_reason([{"lodging_type": "생활"}]),
            "not_general_lodging",
        )

    def test_unit_trade_keeps_legacy_first_master_behavior(self):
        matches = [{"lodging_type": "생활"}, {"lodging_type": "일반"}]
        first_match = matches[0] if matches else None
        self.assertEqual(first_match["lodging_type"], "생활")
        self.assertEqual(
            sync_batch.whole_building_match_reason(matches),
            "ambiguous_exact_master",
        )

    def test_schema_init_retries_deadlock_with_backoff(self):
        with (
            patch.object(
                db,
                "_init_db_once",
                side_effect=[
                    psycopg2.errors.DeadlockDetected("deadlock detected"),
                    None,
                ],
            ) as init_mock,
            patch.object(db.time, "sleep") as sleep_mock,
        ):
            db.init_db()

        self.assertEqual(init_mock.call_count, 2)
        sleep_mock.assert_called_once_with(2)

    def test_trade_month_rolls_back_and_retries_without_refetch(self):
        conn = _Connection()
        stats = {
            "inserted": 0,
            "matched_master": 0,
            "matched_bld": 0,
            "unmatched": 0,
        }
        attempts = {"count": 0}

        def process(
            _cur, _sgg, _ymd, _trades, _bjdong, current_stats,
            pending_emails=None,
        ):
            attempts["count"] += 1
            current_stats["inserted"] += 1
            pending_emails.append(
                ("test@example.com", "테스트", "중개거래", 10, 1000, "3", "2026-09-01")
            )
            if attempts["count"] == 1:
                raise psycopg2.errors.DeadlockDetected("deadlock detected")

        with (
            patch.object(sync_batch, "_process_trades", side_effect=process),
            patch.object(sync_batch, "_clear_failure"),
            patch.object(sync_batch, "_send_tx_email") as email_mock,
            patch.object(sync_batch.time, "sleep") as sleep_mock,
        ):
            sync_batch._apply_trade_month(
                object(), conn, "11110", "202609", [{}], None, stats
            )

        self.assertEqual(attempts["count"], 2)
        self.assertEqual(stats["inserted"], 1)
        self.assertEqual(conn.rollbacks, 1)
        self.assertEqual(conn.commits, 1)
        self.assertEqual(email_mock.call_count, 1)
        sleep_mock.assert_called_once_with(2)

    def test_non_deadlock_database_error_is_not_swallowed(self):
        class Cursor:
            def execute(self, *_args, **_kwargs):
                raise psycopg2.OperationalError("connection closed")

        with self.assertRaises(psycopg2.OperationalError):
            sync_batch._process_trades(
                Cursor(),
                "11110",
                "202609",
                [{
                    "umdNm": "테스트동",
                    "jibun": "1-1",
                    "dealYear": "2026",
                    "dealMonth": "9",
                    "dealDay": "1",
                    "dealAmount": "1000",
                }],
                None,
                {
                    "inserted": 0,
                    "matched_master": 0,
                    "matched_bld": 0,
                    "unmatched": 0,
                },
            )

    def test_notification_database_error_reaches_transaction_retry(self):
        class Cursor:
            def execute(self, *_args, **_kwargs):
                raise psycopg2.errors.DeadlockDetected("deadlock detected")

        with self.assertRaises(psycopg2.errors.DeadlockDetected):
            sync_batch._notify_subscribers(
                Cursor(), 1, "테스트", "서울 테스트동 1-1",
                1000, "2026-09-01", "3",
            )


if __name__ == "__main__":
    unittest.main()