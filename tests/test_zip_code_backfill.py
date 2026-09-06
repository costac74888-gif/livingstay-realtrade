import unittest
from unittest import mock

import zip_code_backfill as zip_backfill


class ZipCodeBackfillProgressTests(unittest.TestCase):
    def test_progress_parses_app_meta_text_json(self):
        raw = (
            '{"date":"2026-09-06","calls_today":27,"last_id":91,'
            '"state":"running","run_id":"lease-1"}'
        )
        result = zip_backfill._normalise_progress(raw, "2026-09-06")
        self.assertEqual(result["calls_today"], 27)
        self.assertEqual(result["last_id"], 91)
        self.assertEqual(result["run_id"], "lease-1")

    def test_progress_keeps_checkpoint_and_resets_only_daily_calls(self):
        old = {
            "date": "2026-09-05",
            "calls_today": 5000,
            "last_id": 12345,
            "completed": 321,
            "state": "failed",
            "last_error": "timeout",
        }
        result = zip_backfill._normalise_progress(old, "2026-09-06")
        self.assertEqual(result["calls_today"], 0)
        self.assertEqual(result["last_id"], 12345)
        self.assertEqual(result["completed"], 321)
        self.assertEqual(result["last_error"], "timeout")

    def test_progress_preserves_same_day_api_budget(self):
        current = {"date": "2026-09-06", "calls_today": 419, "last_id": 88}
        result = zip_backfill._normalise_progress(current, "2026-09-06")
        self.assertEqual(result["calls_today"], 419)
        self.assertEqual(result["last_id"], 88)

    def test_db_failure_after_provider_success_counts_attempt_once_and_advances(self):
        class FailingCursor:
            rowcount = 0

            def execute(self, _sql, _params):
                raise RuntimeError("database write failed")

        class Connection:
            def __init__(self):
                self.rollbacks = 0

            def commit(self):
                raise AssertionError("commit must not be reached")

            def rollback(self):
                self.rollbacks += 1

        provider_calls = []

        def provider(address):
            provider_calls.append(address)
            return {"zipNo": "12345"}

        progress = {
            "calls_today": 8, "last_id": 10, "completed": 2,
            "run_id": "worker-1", "in_flight_id": None,
        }
        row = {"id": 11, "road_address": "서울 테스트로 1"}
        conn = Connection()
        with mock.patch.object(zip_backfill, "save_progress") as save:
            self.assertTrue(zip_backfill._reserve_attempt(conn, progress, 11, 5000))
            save.assert_called_once_with(conn, progress)
            outcome, error, changed = zip_backfill._attempt_address(
                conn, FailingCursor(), progress, row, provider
            )

        self.assertEqual(outcome, "error")
        self.assertIsInstance(error, RuntimeError)
        self.assertFalse(changed)
        self.assertEqual(provider_calls, ["서울 테스트로 1"])
        self.assertEqual(progress["calls_today"], 9)
        self.assertEqual(progress["last_id"], 11)
        self.assertEqual(progress["completed"], 2)
        self.assertEqual(conn.rollbacks, 1)
        self.assertIsNone(progress["in_flight_id"])

    def test_crash_after_reservation_leaves_quota_charged_for_takeover(self):
        durable = {}
        progress = {
            "date": "2026-09-06",
            "calls_today": 4998,
            "last_id": 40,
            "completed": 10,
            "run_id": "old-worker",
            "in_flight_id": None,
        }

        def persist(_conn, value):
            # Simulate the committed app_meta TEXT document immediately before
            # a process crash and before road_to_jibun is called.
            durable["value"] = zip_backfill.json.dumps(value)

        with mock.patch.object(zip_backfill, "save_progress", side_effect=persist):
            self.assertTrue(zip_backfill._reserve_attempt(object(), progress, 41, 5000))

        takeover = zip_backfill._normalise_progress(
            durable["value"], "2026-09-06"
        )
        self.assertEqual(takeover["calls_today"], 4999)
        self.assertEqual(takeover["last_id"], 40)
        self.assertEqual(takeover["in_flight_id"], 41)

        # Retrying the unresolved ID consumes the final reservation, and a
        # further dispatch is refused rather than exceeding the cap.
        takeover["run_id"] = "new-worker"
        with mock.patch.object(zip_backfill, "save_progress", side_effect=persist):
            self.assertTrue(zip_backfill._reserve_attempt(object(), takeover, 41, 5000))
            self.assertFalse(zip_backfill._reserve_attempt(object(), takeover, 42, 5000))
        self.assertEqual(takeover["calls_today"], 5000)

    def test_progress_write_is_rejected_after_lease_takeover(self):
        class LostLeaseCursor:
            rowcount = 0

            def execute(self, sql, params):
                self.sql = sql
                self.params = params

        cur = LostLeaseCursor()
        with self.assertRaises(zip_backfill.LeaseLost):
            zip_backfill._save_progress_cursor(cur, {
                "run_id": "old-worker",
                "state": "done",
            })
        self.assertIn("value::jsonb ->> 'run_id' = %s", cur.sql)
        self.assertEqual(cur.params[-1], "old-worker")


if __name__ == "__main__":
    unittest.main()