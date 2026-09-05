import unittest
from pathlib import Path
from unittest.mock import patch

import app as app_module
from app import (
    _building_tourism_region_key,
    _latest_domestic_visitor_counts,
    _search_ranking_fallback_centroid,
    _tourism_region_key,
)


ROOT = Path(__file__).resolve().parents[1]


class TourismApiContractTests(unittest.TestCase):
    """Small contract tests that do not require the tourism import to exist."""

    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "app.py").read_text(encoding="utf-8")

    def test_region_key_normalizes_sido_suffix_and_sgg_whitespace(self):
        self.assertEqual(
            _tourism_region_key("서울특별시", "강남 구"),
            _tourism_region_key("서울", "강남구"),
        )
        self.assertEqual(
            _building_tourism_region_key({"sgg_text": "강원특별자치도  속초시"}),
            ("강원", "속초시"),
        )

    def test_cluster_contract_has_null_umd_and_single_batch_lookup(self):
        self.assertIn("def _latest_domestic_visitor_counts(cur)", self.source)
        self.assertIn('item["visitor_count"] = None', self.source)
        self.assertIn("기초지자체 방문자 수", self.source)

    def test_latest_domestic_rows_are_normalized_into_a_single_lookup(self):
        class Cursor:
            def __init__(self):
                self.query = ""

            def execute(self, query):
                self.query = query

            def fetchall(self):
                return [
                    {
                        "sido_name": "인천광역시",
                        "sgg_name": "중 구",
                        "metric_value": 1234,
                    }
                ]

        cursor = Cursor()
        self.assertEqual(
            _latest_domestic_visitor_counts(cursor),
            {("인천", "중구"): 1234.0},
        )
        self.assertIn("SELECT source_file", cursor.query)
        self.assertIn("JOIN latest l ON t.source_file = l.source_file", cursor.query)

    def test_search_ranking_fallback_uses_normalized_region_key(self):
        self.assertEqual(
            _search_ranking_fallback_centroid("인천광역시", "중구"),
            (37.473660523066044, 126.62170176164001),
        )
        self.assertEqual(
            _search_ranking_fallback_centroid("강원특별자치도", "속 초시"),
            (38.206894335257, 128.591938589235),
        )
        self.assertIsNone(_search_ranking_fallback_centroid("서울특별시", "없는구"))

    def test_detail_and_attraction_route_contracts_are_type_scoped(self):
        self.assertIn('building.get("lodging_type") == "에어비앤비"', self.source)
        self.assertIn('"tourism_foreign_ratio"', self.source)
        self.assertIn('"foreign_top3"', self.source)
        self.assertIn('"/api/building/<int:building_id>/tourism-stats"', self.source)
        self.assertIn('{"캠핑", "농어촌민박", "한옥"}', self.source)
        self.assertIn('"/api/tourism/attractions/top20"', self.source)
        self.assertIn("max_rank=20", self.source)
        self.assertIn('"sgg_office_fallback"', self.source)
        self.assertIn('"coordinate_scope": "sgg_representative"', self.source)
        schema = (ROOT / "db.py").read_text(encoding="utf-8")
        self.assertIn("idx_tourism_stats_lodging_rank_latest", schema)
        self.assertIn("idx_tourism_stats_lodging_rank_source", schema)
        self.assertIn("idx_tourism_stats_lodging_rank_building_source", schema)

    def test_lodging_rank_routes_use_one_latest_source_and_safe_counts(self):
        class Cursor:
            def __init__(self):
                self.queries = []

            def execute(self, query, params=None):
                self.queries.append((query, params))

            def fetchall(self):
                if "t.master_building_id = %s" in self.queries[-1][0]:
                    return []
                return [{
                    "building_id": 17,
                    "building_name": "테스트 숙소",
                    "sido_name": "서울특별시",
                    "sgg_name": "중 구",
                    "metric_value": 1,
                    "dimensions": {
                        "place_name": "테스트 호텔",
                        "sub_category": "관광호텔",
                        "search_count": "12,345",
                    },
                    "source_period": "202601-202603",
                    "source_file": "new.zip::rank.csv",
                    "collected_at": None,
                    "lat": 37.56,
                    "lng": 126.99,
                }]

            def fetchone(self):
                return {
                    "id": 99, "building_name": "순위 없음 숙소",
                    "lat": None, "lng": None,
                }

            def close(self):
                pass

        class Connection:
            def __init__(self):
                self.cursor_value = Cursor()

            def cursor(self):
                return self.cursor_value

        connection = Connection()
        with patch.object(app_module, "get_conn", return_value=connection), \
             patch.object(app_module, "release_conn") as release:
            client = app_module.app.test_client()
            top = client.get("/api/tourism/lodging-rank/top99")
            missing = client.get("/api/building/99/lodging-rank")

        self.assertEqual(top.status_code, 200)
        self.assertEqual(top.get_json()["items"][0]["rank"], 1)
        self.assertEqual(top.get_json()["items"][0]["search_count"], 12345)
        self.assertEqual(top.get_json()["items"][0]["building_name"], "테스트 숙소")
        self.assertEqual(top.get_json()["items"][0]["place_name"], "테스트 호텔")
        self.assertEqual(top.get_json()["items"][0]["sub_category"], "관광호텔")
        self.assertEqual(top.get_json()["items"][0]["master_building_id"], 17)
        self.assertEqual(missing.status_code, 200)
        self.assertIsNone(missing.get_json()["rank"])
        self.assertEqual(release.call_count, 2)

        rank_queries = [
            query for query, _params in connection.cursor_value.queries
            if "lodging_search_rank" in query
        ]
        self.assertEqual(len(rank_queries), 2)
        self.assertTrue(all("JOIN latest l ON l.source_file = t.source_file" in q
                            for q in rank_queries))
        self.assertTrue(all("split_part(t.source_period,'-',2)" in q
                            and "t.collected_at DESC, t.source_file DESC" in q
                            for q in rank_queries))


if __name__ == "__main__":
    unittest.main()