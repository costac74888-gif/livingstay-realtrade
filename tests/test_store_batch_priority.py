"""Shared store-key budget and per-HTTP-attempt reservation regressions."""
import json
import unittest
from unittest.mock import Mock, patch

import quota_policy as quotas
import store_info_util as stores


class StorePriorityTests(unittest.TestCase):
    def claim(self, rows, collector="realty", cap=7500):
        cursor = Mock()
        cursor.fetchall.return_value = [
            {"key": key, "value": json.dumps(value)} for key, value in rows.items()
        ]
        conn = Mock()
        conn.cursor.return_value = cursor
        with patch("db.get_conn", return_value=conn), patch.object(
                quotas, "korea_today", return_value="2026-10-03"):
            result = quotas.claim_store_batch_request(collector, cap)
        value = json.loads(cursor.execute.call_args.args[1][1])
        self.assertTrue(conn.commit.called)
        self.assertTrue(conn.close.called)
        return result, value

    def test_allocation_and_shared_bucket(self):
        self.assertEqual(quotas.regular_cap("realty_store"), 7500)
        self.assertEqual(quotas.regular_cap("store_info"), 500)
        self.assertEqual(quotas.quota_bucket_for_stage("realty"),
                         quotas.quota_bucket_for_stage("stores"))
        self.assertEqual(quotas.quota_for_stage("stores")["realtime"], 1500)
        self.assertEqual(quotas.quota_for_stage("stores")["manual"], 500)

    def test_seed_preserves_calls_made_before_upgrade_without_double_count(self):
        result, value = self.claim({
            "realty_stores_progress": {"calls_date": "2026-10-03", "calls_today": 230},
            "stores_progress": {"calls_date": "2026-10-03", "calls_today": 40},
            "store_daily_calls_batch": {"date": "2026-10-03", "count": 45},
        })
        self.assertEqual(result, 231)
        self.assertEqual(value["count"], 276)
        self.assertEqual(value["stores"], 45)

    def test_day_rollover_resets_both_allocations(self):
        result, value = self.claim({
            quotas.STORE_BATCH_REQUEST_KEY:
                {"date": "2026-10-02", "count": 8000, "realty": 7500, "stores": 500}
        })
        self.assertEqual(result, 1)
        self.assertEqual(value["count"], 1)

    def test_exhaustion_never_commits_or_resets_checkpoint_allowance(self):
        for realty, general, collector, cap in [
            (7500, 0, "realty", 10000),
            (1, 500, "stores", 8000),
            (7501, 499, "stores", 500),
        ]:
            cursor = Mock()
            cursor.fetchall.return_value = [{
                "key": quotas.STORE_BATCH_REQUEST_KEY,
                "value": json.dumps({"date": "2026-10-03", "count": realty + general,
                                     "realty": realty, "stores": general}),
            }]
            conn = Mock()
            conn.cursor.return_value = cursor
            with patch("db.get_conn", return_value=conn), patch.object(
                    quotas, "korea_today", return_value="2026-10-03"):
                with self.assertRaises(quotas.QuotaExhausted):
                    quotas.claim_store_batch_request(collector, cap)
            self.assertFalse(conn.commit.called)
            self.assertTrue(conn.rollback.called)

    def test_connect_timeout_retries_each_reserve_one_call(self):
        reserve = Mock()
        with patch.object(stores.requests, "get", side_effect=stores.ConnectTimeout("fixture")), \
                patch.object(stores.time, "sleep"):
            with self.assertRaises(stores.ConnectTimeout):
                stores._get_with_retry("https://example.test", {}, 1, before_request=reserve)
        self.assertEqual(reserve.call_count, 3)

    def test_quota_exhaustion_blocks_network_and_remains_typed(self):
        with patch.object(stores, "STORE_INFO_SERVICE_KEY", "fixture"), \
                patch.object(stores.requests, "get") as request:
            with self.assertRaises(quotas.QuotaExhausted):
                stores.get_stores_by_pnu("1234512345100010000",
                    before_request=Mock(side_effect=quotas.QuotaExhausted("fixture")))
            request.assert_not_called()


if __name__ == "__main__":
    unittest.main()