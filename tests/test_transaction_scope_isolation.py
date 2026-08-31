import pathlib
import unittest


class TransactionScopeIsolationTests(unittest.TestCase):
    def test_public_ranking_queries_are_unit_only(self):
        source = pathlib.Path("app.py").read_text(encoding="utf-8")
        ranking = source[source.index("def get_ranking"):source.index("@app.route(\"/api/buildings-geo\")")]

        self.assertIn(
            "WHERE deal_date < TO_CHAR(CURRENT_DATE - INTERVAL '7 days', 'YYYY-MM-DD')\n"
            "                      AND transaction_scope = 'unit'",
            ranking,
        )
        self.assertIn(
            "WHERE deal_date >= TO_CHAR(CURRENT_DATE - INTERVAL '7 days', 'YYYY-MM-DD')\n"
            "                  AND transaction_scope = 'unit'",
            ranking,
        )

    def test_default_public_apis_are_unit_scoped(self):
        source = pathlib.Path("app.py").read_text(encoding="utf-8")
        transactions = source[source.index("def get_transactions"):source.index("_geo_cache: dict")]
        trend = source[source.index("def get_monthly_trend"):source.index("@app.route(\"/api/tx-count\")")]

        self.assertIn('request.args.get("transaction_scope") or "unit"', transactions)
        self.assertIn('request.args.get("transaction_scope") or "unit"', trend)
        self.assertIn('"transaction_scope = %s"', transactions)
        self.assertIn('"transaction_scope = %s"', trend)


if __name__ == "__main__":
    unittest.main()