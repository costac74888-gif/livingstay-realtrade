import unittest

from validate_lodging_all_production_delta import classify_production_match


class AllProductionDeltaMatchingTest(unittest.TestCase):
    def test_road_unique_takes_priority_over_jibun(self):
        self.assertEqual(
            classify_production_match(
                "road-a", "jibun-a", {"road-a": {1}}, {"jibun-a": {1}}
            ),
            ("existing_building", (1,), 1),
        )

    def test_new_address_is_not_auto_created_when_ambiguous(self):
        self.assertEqual(
            classify_production_match(
                "road-many", None, {"road-many": {2, 3}}, {}
            ),
            ("ambiguous_existing_building", (2, 3), None),
        )
        self.assertEqual(
            classify_production_match(
                None, "jibun-new", {}, {}
            ),
            ("new_building_candidate", (), None),
        )


if __name__ == "__main__":
    unittest.main()