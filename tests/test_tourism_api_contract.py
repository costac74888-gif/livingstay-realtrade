import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()