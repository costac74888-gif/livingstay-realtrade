import pathlib
import unittest


class AnalysisAssetsContractTests(unittest.TestCase):
    """Guard the authenticated analysis endpoint's conservative data contract."""

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

    def test_analysis_requires_login_and_reports_total_transaction_population(self):
        self.assertIn('"requires_login": True', self.endpoint)
        self.assertIn('"agent_id", "operator_id", "loan_consultant_id"', self.endpoint)
        self.assertIn("total_transaction_count", self.endpoint)
        self.assertIn('"analysis_sample_transaction_count"', self.endpoint)
        self.assertIn("cohort.id = %s", self.endpoint)
        self.assertIn("building_id가 올바르지 않습니다.", self.endpoint)
        self.assertNotIn('where.append("mb.id = %s")', self.endpoint)

    def test_building_search_is_authenticated_and_name_first(self):
        search_start = self.source.index('@app.route("/api/analysis/building-search")')
        search_end = self.source.index('@app.route("/api/analysis/assets")', search_start)
        search = self.source[search_start:search_end]
        self.assertIn('"requires_login": True', search)
        self.assertIn("building_name", search)
        self.assertIn("road_address", search)
        self.assertIn("WHEN trim(COALESCE(building_name", search)

    def test_price_linkage_is_exact_and_unit_only(self):
        self.assertIn("NOT EXISTS (", self.endpoint)
        self.assertIn("duplicate.id<>mb.id", self.endpoint)
        self.assertIn("mb.sgg_cd=t.sgg_cd", self.endpoint)
        self.assertIn("mb.umd_nm=t.umd_nm AND mb.jibun=t.jibun", self.endpoint)
        self.assertIn("transaction_scope = 'unit'", self.endpoint)
        self.assertIn("match_confidence = 'exact'", self.endpoint)
        self.assertIn("price > 0 AND area > 0", self.endpoint)
        self.assertNotIn("building_name ILIKE", self.endpoint)

    def test_peer_price_requires_a_real_comparable_median(self):
        self.assertIn("previous_value <= 0", self.source)
        self.assertIn('"peer_price_gap": peer_price_gap', self.endpoint)
        self.assertIn('"peer_price_median": peer_median', self.endpoint)
        self.assertIn('return "관광 비교자료 부족"', self.source)
        self.assertIn('return "유사자산 비교자료 부족"', self.source)

    def test_tourism_axis_uses_real_visitor_percentile_not_fake_growth(self):
        self.assertIn("metric_name = '기초지자체 방문자 수'", self.source)
        self.assertIn("JOIN latest_file USING (source_file)", self.source)
        self.assertIn("percent_rank() OVER (ORDER BY visitor_count)", self.source)
        self.assertIn('"tourism_demand_index": demand_index', self.endpoint)

    def test_tourism_index_is_the_default_public_axis(self):
        self.assertIn('tourism_axis not in {"index", "growth"}', self.endpoint)
        self.assertIn('request.args.get("tourism_axis", "index")', self.endpoint)
        self.assertIn('tourism_key = "tourism_demand_index"', self.endpoint)

    def test_quadrants_use_the_exact_plotted_comparison_population(self):
        self.assertIn("comparable_items = [", self.endpoint)
        self.assertIn(
            'item[tourism_key] is not None and item["peer_price_gap"] is not None',
            self.endpoint,
        )
        self.assertIn("tourism_baseline = 50", self.endpoint)
        self.assertIn("price_baseline = 0", self.endpoint)
        self.assertIn('"is_representative"', self.endpoint)
        self.assertIn('item["sample_level"] == "표본 양호"', self.endpoint)

    def test_peer_hierarchy_and_sample_levels_are_explicit(self):
        self.assertIn('"시군구·동일유형"', self.endpoint)
        self.assertIn('"시도·동일유형"', self.endpoint)
        self.assertIn('"전국·동일유형"', self.endpoint)
        self.assertIn("display_rows = [", self.endpoint)
        self.assertIn(
            "WHERE mb.lodging_type IS DISTINCT FROM 'mixed_use_excluded'",
            self.endpoint,
        )
        self.assertIn('current_count >= 3', self.endpoint)
        self.assertIn('"표본 주의"', self.endpoint)
        self.assertIn('"비교자료 부족"', self.endpoint)

    def test_public_population_excludes_mixed_use_and_is_capped(self):
        self.assertIn("lodging_type IS DISTINCT FROM 'mixed_use_excluded'", self.endpoint)
        self.assertIn("LIMIT %s", self.endpoint)
        self.assertIn("_ANALYSIS_MAX_ITEMS", self.endpoint)
        self.assertIn("WITH recent_tx AS MATERIALIZED", self.endpoint)
        self.assertIn("CURRENT_DATE - make_interval(months => %s * 2)", self.endpoint)

    def test_expensive_aggregates_use_versioned_persistent_cache(self):
        self.assertIn("_analysis_cached_payload(", self.endpoint)
        self.assertIn('"transactions", transaction_cache_key', self.endpoint)
        self.assertIn("_analysis_tourism_demand_by_sgg(cur, period_months)", self.endpoint)
        self.assertIn("_analysis_source_version(", self.source)
        self.assertIn("_analysis_store_payload(", self.source)
        self.assertIn("SELECT CURRENT_DATE::text AS cache_date", self.endpoint)
        self.assertIn("transaction_cache_date, period_months, sido, sgg", self.endpoint)
        self.assertIn('"peer-price-cohort-v1"', self.endpoint)

    def test_selected_trajectory_uses_monthly_unit_price_medians_without_imputation(self):
        self.assertIn("_analysis_selected_trajectory(", self.endpoint)
        self.assertIn('"trajectory": trajectory', self.endpoint)
        self.assertIn('"price_per_sqm_median"', self.source)
        self.assertIn('"transactions": [{', self.source)
        self.assertIn("if all(value in tourism for value in current_months + previous_months)", self.source)
        self.assertIn('"tourism_value": tourism_value', self.source)


if __name__ == "__main__":
    unittest.main()
