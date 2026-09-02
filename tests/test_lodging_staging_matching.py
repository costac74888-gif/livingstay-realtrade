import unittest

from analyze_lodging_staging_matches import SOURCE_KEYS, classify_match
from lodging_data_contract import GOVERNMENT_LODGING_SOURCES


class LodgingStagingMatchingTest(unittest.TestCase):
    def setUp(self):
        self.road = {"road-a": {1}, "road-many": {2, 3}, "road-conflict": {4}}
        self.jibun = {"jibun-a": {1}, "jibun-b": {5}, "jibun-many": {6, 7}}

    def test_unique_road_match_wins_when_addresses_agree(self):
        self.assertEqual(
            classify_match("road-a", "jibun-a", self.road, self.jibun),
            ("road_unique", (1,), 1),
        )

    def test_default_analysis_sources_follow_the_eight_source_contract(self):
        self.assertEqual(SOURCE_KEYS, tuple(GOVERNMENT_LODGING_SOURCES))
        self.assertEqual(len(SOURCE_KEYS), 8)

    def test_unique_road_and_jibun_disagreement_is_not_auto_matched(self):
        state, candidates, building_id = classify_match(
            "road-conflict", "jibun-b", self.road, self.jibun
        )
        self.assertEqual(state, "address_conflict")
        self.assertEqual(candidates, (4, 5))
        self.assertIsNone(building_id)

    def test_ambiguous_road_is_not_hidden_by_unique_jibun(self):
        state, candidates, building_id = classify_match(
            "road-many", "jibun-a", self.road, self.jibun
        )
        self.assertEqual(state, "road_ambiguous")
        self.assertEqual(candidates, (2, 3))
        self.assertIsNone(building_id)

    def test_jibun_is_used_only_when_road_has_no_candidate(self):
        self.assertEqual(
            classify_match("road-missing", "jibun-b", self.road, self.jibun),
            ("jibun_unique", (5,), 5),
        )

    def test_missing_and_unmatched_are_distinct(self):
        self.assertEqual(
            classify_match(None, None, self.road, self.jibun),
            ("no_address", (), None),
        )
        self.assertEqual(
            classify_match("none", "none", self.road, self.jibun),
            ("unmatched", (), None),
        )


if __name__ == "__main__":
    unittest.main()