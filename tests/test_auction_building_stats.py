"""공매 건물 집계·범례 권한: 공급자 호출·DB 쓰기 없이 검사."""
import os
import unittest
from unittest.mock import MagicMock, patch

import app as web
from auction_domain import CURRENT_SQL
from auction_service import auction_building_stats


class AuctionBuildingStatsTests(unittest.TestCase):
    def test_shared_query_counts_distinct_existing_buildings(self):
        cur = MagicMock()
        cur.fetchall.return_value = [
            {"t": "생활", "n": 15, "item_count": 45},
            {"t": "일반", "n": 21, "item_count": 50},
            {"t": None, "n": 0, "item_count": 168},
        ]
        self.assertEqual(auction_building_stats(cur), {
            "count": 36, "by_type": {"생활": 15, "일반": 21}, "item_count": 263,
        })
        sql = cur.execute.call_args.args[0]
        self.assertTrue(sql.startswith(CURRENT_SQL))
        self.assertIn("COUNT(DISTINCT b.id)", sql)
        self.assertIn("LEFT JOIN master_buildings b ON b.id=a.master_building_id", sql)
        self.assertIn("COUNT(*) AS item_count", sql)
        self.assertIn("WHEN b.id IS NULL THEN NULL", sql)
        self.assertIn("b.lodging_type IN ('생활','생숙')", sql)
        self.assertEqual(cur.execute.call_count, 1)

    def test_empty_is_zero_not_unknown(self):
        cur = MagicMock()
        cur.fetchall.return_value = []
        self.assertEqual(auction_building_stats(cur), {"count": 0, "by_type": {}, "item_count": 0})

    def test_all_unlinked_items_are_counted_without_inventing_buildings(self):
        cur = MagicMock()
        cur.fetchall.return_value = [{"t": None, "n": 0, "item_count": 263}]
        self.assertEqual(auction_building_stats(cur), {
            "count": 0, "by_type": {}, "item_count": 263,
        })

    def test_preview_and_admin_only_not_query_string(self):
        cases = [
            ("localhost", "0", False, "", True),
            ("example.replit.dev", "0", False, "", True),
            ("homenstay.com", "0", False, "", False),
            ("localhost", "1", False, "", False),
            ("homenstay.com", "1", False, "", False),
            ("homenstay.com", "1", True, "", False),
            ("homenstay.com", "1", True, "admin=1", True),
            ("homenstay.com", "1", False, "admin=1", False),
            ("homenstay.com", "1", True, "admin=true&preview=1", False),
        ]
        for host, deployment, admin, query, expected in cases:
            with self.subTest(host=host, deployment=deployment, admin=admin, query=query), \
                    patch.dict(os.environ, {"REPLIT_DEPLOYMENT": deployment}), \
                    web.app.test_request_context("/?" + query, base_url="https://" + host):
                web.session["admin"] = admin
                self.assertEqual(web._show_unclassified_legend(), expected)

    def test_admin_column_does_not_change_master_totals_or_cached_rows(self):
        source = {"ok": True, "rows": [
            {"type": "전체", "building_count": 10},
            {"type": "생활", "building_count": 7},
            {"type": "일반", "building_count": 3},
        ]}
        connection = MagicMock()
        connection.__enter__.return_value = connection
        client = web.app.test_client()
        with client.session_transaction() as session:
            session["admin"] = True
        with patch.object(web, "get_conn", return_value=connection), \
                patch.object(web, "_cached_master_building_count", return_value=10), \
                patch.object(web, "_live_master_building_count", return_value=10), \
                patch.object(web, "_lodging_full_stats_payload", side_effect=lambda: web.jsonify(source)), \
                patch("auction_service.auction_building_stats", return_value={
                    "count": 2, "by_type": {"생활": 2}, "item_count": 263,
                }), patch.object(web.limiter, "enabled", False):
            response = client.get("/api/admin/buildings/full-stats")
        self.assertEqual(response.status_code, 200)
        rows = response.get_json()["rows"]
        self.assertEqual([r["auction_building_count"] for r in rows], [2, 2, 0, 2])
        self.assertEqual([r["building_count"] for r in rows], [10, 7, 3, 2])
        self.assertEqual(rows[-1]["type"], "공매")
        self.assertEqual(rows[-1]["auction_item_count"], 263)
        self.assertTrue(rows[-1]["reference_only"])
        self.assertNotIn("auction_building_count", source["rows"][0])

    def test_production_api_uses_mode_and_auth_not_admin_cookie_alone(self):
        client = web.app.test_client()
        client.environ_base["HTTP_USER_AGENT"] = "Mozilla/5.0"
        connection = MagicMock()
        connection.cursor.return_value.fetchall.return_value = [{"t": "생활", "c": 10}]
        connection.cursor.return_value.fetchone.return_value = {"c": 19}
        with patch.dict(os.environ, {"REPLIT_DEPLOYMENT": "1"}), \
                patch.object(web, "get_conn", return_value=connection), \
                patch("auction_service.auction_building_stats", return_value={
                    "count": 2, "by_type": {"생활": 2}, "item_count": 263,
                }), patch.object(web.limiter, "enabled", False):
            for authenticated, query, expected in [
                (True, "", False), (True, "?admin=1", True),
                (False, "?admin=1", False), (False, "", False),
            ]:
                with client.session_transaction() as session:
                    session["admin"] = authenticated
                result = client.get("/api/building-count" + query)
                self.assertEqual(result.status_code, 200)
                self.assertEqual(result.get_json()["show_unclassified_legend"], expected)
                self.assertEqual(result.get_json()["auction_building_count"], 2)
                self.assertEqual(result.get_json()["auction_item_count"], 263)
                self.assertEqual(result.headers["Cache-Control"], "no-store")


if __name__ == "__main__":
    unittest.main()
