import pathlib
import unittest
from unittest import mock
from urllib.parse import parse_qs, urlsplit

import app as application


class FakeAnalysisCursor:
    def __init__(self, rows):
        self.rows = rows
        self.result = []

    def execute(self, sql, params=None):
        normalized = " ".join(sql.split())
        if normalized.startswith("SELECT DISTINCT regexp_replace"):
            self.result = [
                {"sido": row["sido"], "sgg": row["sgg"], "lodging_type": row["lodging_type"]}
                for row in self.rows
            ]
        elif normalized.startswith("SELECT COUNT(*) AS count FROM master_buildings"):
            self.result = [{"count": len(self.rows)}]
        elif normalized.startswith("SELECT COUNT(*) AS count, MIN(deal_date)"):
            self.result = [{"count": len(self.rows), "start_date": "2025-01-01"}]
        elif normalized == "SELECT CURRENT_DATE::text AS cache_date":
            self.result = [{"cache_date": "2026-09-07"}]
        elif normalized.startswith("WITH recent_tx AS MATERIALIZED"):
            if len(params or []) != 7:
                raise AssertionError("Regional filters must not narrow the nationwide peer cohort query")
            self.result = self.rows
        else:
            raise AssertionError(f"Unexpected SQL in analysis integration test: {normalized}")

    def fetchall(self):
        return self.result

    def fetchone(self):
        return self.result[0]

    def close(self):
        pass


class FakeAnalysisConnection:
    def __init__(self, rows):
        self.cursor_instance = FakeAnalysisCursor(rows)

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        pass

    def close(self):
        pass


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
        self.assertIn('_analysis_session_or_share("property"', self.endpoint)
        self.assertIn('"agent_id", "operator_id", "loan_consultant_id"', self.source)
        self.assertIn("total_transaction_count", self.endpoint)
        self.assertIn('"analysis_sample_transaction_count"', self.endpoint)
        self.assertIn("cohort.id = %s", self.endpoint)
        self.assertIn("building_id가 올바르지 않습니다.", self.endpoint)
        self.assertNotIn('where.append("mb.id = %s")', self.endpoint)

    def test_signed_share_link_allows_only_its_building_and_mode(self):
        client = application.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = 77
        response = client.post("/api/analysis/share-link", json={
            "building_id": 2753,
            "mode": "property",
        })
        self.assertEqual(response.status_code, 200)
        path = response.get_json()["path"]
        query = parse_qs(urlsplit(path).query)
        token = query["share"][0]
        with application.app.test_request_context(
            f"/api/analysis/assets?building_id=2753&share={token}"
        ):
            self.assertTrue(application._analysis_session_or_share("property", 2753))
            self.assertFalse(application._analysis_session_or_share("property", 2754))
            self.assertFalse(application._analysis_session_or_share("operation", 2753))
        with application.app.test_request_context(
            f"/api/analysis/assets?building_id=2753&share={token}x"
        ):
            self.assertFalse(application._analysis_session_or_share("property", 2753))

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


class AnalysisAssetsRegionIntegrationTests(unittest.TestCase):
    @staticmethod
    def _row(building_id, sido, sgg, price):
        return {
            "id": building_id,
            "building_name": f"건물 {building_id}",
            "road_address": f"{sido} {sgg} 테스트로 {building_id}",
            "jibun_address": None,
            "sgg_cd": str(building_id).zfill(5),
            "umd_nm": "테스트동",
            "jibun": str(building_id),
            "lodging_type": "생활숙박시설",
            "lat": 37.0,
            "lng": 127.0,
            "current_median": price,
            "previous_median": price,
            "current_count": 3,
            "previous_count": 1,
            "historical_peak": price,
            "latest_price": price * 10,
            "price_per_sqm": price,
            "last_deal_date": "2026-08-01",
            "sido": sido,
            "sgg": sgg,
        }

    def setUp(self):
        rows = [self._row(1, "경기", "가평군", 100)]
        rows.extend(self._row(i, "경기", "가평군", 110) for i in range(2, 6))
        rows.extend(self._row(i, "경기", "수원시", 120) for i in range(6, 12))
        rows.append(self._row(12, "강원", "양양군", 200))
        rows.extend(self._row(i, "충북", "제천시", 300) for i in range(13, 24))
        self.rows = rows
        self.client = application.app.test_client()
        with self.client.session_transaction() as session:
            session["user_id"] = 1

    def _get_items(self, query=""):
        connection = FakeAnalysisConnection(self.rows)
        patches = (
            mock.patch.object(application, "get_conn", return_value=connection),
            mock.patch.object(application, "_analysis_source_version", return_value="test-version"),
            mock.patch.object(application, "_analysis_cached_payload", return_value=None),
            mock.patch.object(application, "_analysis_store_payload"),
            mock.patch.object(application, "_analysis_tourism_demand_by_sgg", return_value={}),
            mock.patch.object(application, "_analysis_selected_trajectory", return_value=[]),
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            response = self.client.get(f"/api/analysis/assets?{query}")
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()["items"]

    def test_region_filter_only_limits_display_and_preserves_fallback_comparisons(self):
        unfiltered = {item["building_id"]: item for item in self._get_items()}

        filtered_sgg = self._get_items("sido=경기&sgg=가평군")
        self.assertTrue(filtered_sgg)
        self.assertEqual({item["sido"] for item in filtered_sgg}, {"경기"})
        self.assertEqual({item["sgg"] for item in filtered_sgg}, {"가평군"})
        target = next(item for item in filtered_sgg if item["building_id"] == 1)
        self.assertEqual(target["peer_scope"], "시도·동일유형")
        self.assertEqual(target["peer_building_count"], 10)
        for field in ("peer_scope", "peer_building_count", "peer_price_gap"):
            self.assertEqual(target[field], unfiltered[1][field])

        filtered_nationwide = self._get_items("sido=강원&sgg=양양군")
        self.assertEqual([item["building_id"] for item in filtered_nationwide], [12])
        sparse_target = filtered_nationwide[0]
        self.assertEqual(sparse_target["peer_scope"], "전국·동일유형")
        self.assertEqual(sparse_target["peer_building_count"], 22)
        for field in ("peer_scope", "peer_building_count", "peer_price_gap"):
            self.assertEqual(sparse_target[field], unfiltered[12][field])

    def test_selected_building_automatically_applies_its_lodging_type(self):
        self.rows[-1] = {
            **self.rows[-1],
            "lodging_type": "관광숙박시설",
        }

        items = self._get_items("building_id=1")

        self.assertTrue(items)
        self.assertIn(1, [item["building_id"] for item in items])
        self.assertEqual(
            {item["lodging_type"] for item in items},
            {"생활숙박시설"},
        )


if __name__ == "__main__":
    unittest.main()
