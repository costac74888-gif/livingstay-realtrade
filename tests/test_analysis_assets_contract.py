import pathlib
import unittest


class AnalysisAssetsContractTests(unittest.TestCase):
    """Guard the public analysis endpoint's conservative data contract."""

    @classmethod
    def setUpClass(cls):
        cls.source = pathlib.Path("app.py").read_text(encoding="utf-8")
        start = cls.source.index('@app.route("/api/analysis/assets")')
        end = cls.source.index('@app.route("/api/tourism/heatmap/foreign")', start)
        cls.endpoint = cls.source[start:end]

    def test_route_rejects_periods_outside_the_public_contract(self):
        self.assertIn("_ANALYSIS_PERIODS = (6, 12, 24)", self.source)
        self.assertIn("period_months는 6, 12, 24 중 하나여야 합니다.", self.endpoint)
        self.assertIn('"period_options"', self.endpoint)

    def test_price_linkage_is_exact_and_unit_only(self):
        self.assertIn("AND duplicate_mb.id <> mb.id", self.endpoint)
        self.assertIn("AND NOT EXISTS (", self.endpoint)
        self.assertIn("t.sgg_cd = s.sgg_cd", self.endpoint)
        self.assertIn("t.umd_nm = s.umd_nm AND t.jibun = s.jibun", self.endpoint)
        self.assertIn("t.transaction_scope = 'unit'", self.endpoint)
        self.assertIn("t.match_confidence = 'exact'", self.endpoint)
        self.assertIn("t.price > 0 AND t.area > 0", self.endpoint)
        self.assertNotIn("building_name ILIKE", self.endpoint)

    def test_missing_comparable_samples_remain_null(self):
        # Price change requires a positive previous observation and cannot
        # manufacture a percentage from a missing or zero denominator.
        self.assertIn("previous_value <= 0", self.source)
        self.assertIn('"price_change": price_change', self.endpoint)

    def test_tourism_axis_uses_real_visitor_percentile_not_fake_growth(self):
        self.assertIn("metric_name = '기초지자체 방문자 수'", self.source)
        self.assertIn("JOIN latest_file lf ON lf.source_file = t.source_file", self.source)
        self.assertIn("percent_rank() OVER (ORDER BY visitor_count)", self.source)
        self.assertIn('"tourism_demand_index": demand_index', self.endpoint)

    def test_public_population_excludes_mixed_use_and_is_capped(self):
        self.assertIn("lodging_type IS DISTINCT FROM 'mixed_use_excluded'", self.endpoint)
        self.assertIn("LIMIT %s", self.endpoint)
        self.assertIn("_ANALYSIS_MAX_ITEMS", self.endpoint)
        self.assertLess(
            self.endpoint.index("LIMIT %s"),
            self.endpoint.index("), exact_tx AS ("),
            "current-period candidates must be capped before historical aggregation",
        )


if __name__ == "__main__":
    unittest.main()