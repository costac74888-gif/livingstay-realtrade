import os
import unittest


class RegionTransactionStatsTests(unittest.TestCase):
    def test_region_aliases_are_merged_and_sorted(self):
        os.environ["SKIP_STARTUP_SCHEMA_INIT"] = "1"
        import app as server

        class Cursor:
            def __init__(self):
                self.sql = ""

            def execute(self, sql, args=None):
                self.sql = sql

            def fetchall(self):
                return [
                    {"si_do": "서울", "deal_count": 2, "latest_date": "2026-09-01"},
                    {"si_do": "서울특별시", "deal_count": 3, "latest_date": "2026-09-03"},
                    {"si_do": "경기도", "deal_count": 4, "latest_date": "2026-09-02"},
                    {"si_do": "경상남도", "deal_count": 1, "latest_date": "2026-09-01"},
                ]

            def close(self):
                pass

        class Connection:
            def __init__(self):
                self.cur = Cursor()

            def cursor(self):
                return self.cur

            def close(self):
                pass

        connection = Connection()
        original = server.get_conn
        server.get_conn = lambda: connection
        try:
            response = server.app.test_client().get("/api/stats/transactions-by-sido")
        finally:
            server.get_conn = original

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["period_days"], 30)
        self.assertEqual(
            data["items"],
            [
                {"region": "서울", "deal_count": 5, "latest_date": "2026-09-03"},
                {"region": "경기", "deal_count": 4, "latest_date": "2026-09-02"},
                {"region": "경남", "deal_count": 1, "latest_date": "2026-09-01"},
            ],
        )
        self.assertIn("transaction_scope = 'unit'", connection.cur.sql)
        self.assertIn("INTERVAL '30 days'", connection.cur.sql)


if __name__ == "__main__":
    unittest.main()