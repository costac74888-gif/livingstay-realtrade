import unittest

from validate_lodging_production_delta import classify_production_match


class ProductionDeltaMatchingTest(unittest.TestCase):
    def setUp(self):
        self.road = {"road-a": {1}, "road-many": {2, 3}}
        self.jibun = {"jibun-a": {1}, "jibun-new": {4}}

    def test_unique_address_matches_existing_production_building(self):
        self.assertEqual(
            classify_production_match("road-a", "jibun-a", self.road, self.jibun),
            ("existing_building", (1,), 1),
        )

    def test_unmatched_address_is_new_building_candidate(self):
        self.assertEqual(
            classify_production_match(
                "road-new", "jibun-new", self.road, self.jibun
            ),
            ("existing_building", (4,), 4),
        )
        self.assertEqual(
            classify_production_match(
                "road-new", "jibun-missing", self.road, self.jibun
            ),
            ("new_building_candidate", (), None),
        )

    def test_multiple_production_candidates_are_not_created_automatically(self):
        self.assertEqual(
            classify_production_match(
                "road-many", None, self.road, self.jibun
            ),
            ("ambiguous_existing_building", (2, 3), None),
        )


if __name__ == "__main__":
    unittest.main()