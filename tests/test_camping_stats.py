import unittest

from camping_stats import summarize_active_camping_facilities


def _row(permit, **overrides):
    row = {
        "permit_number": permit,
        "applied_building_id": None,
        "road_norm": "서울시중구캠핑로1",
        "jibun_norm": None,
        "biz_name_norm": "테스트캠핑장",
        "camping_general_site_count": 0,
        "camping_auto_site_count": 0,
        "camping_glamping_site_count": 0,
        "camping_caravan_site_count": 0,
        "camping_classification": "unknown",
    }
    row.update(overrides)
    return row


class CampingFacilityStatsTests(unittest.TestCase):
    def test_linked_and_matching_unlinked_sources_count_one_facility(self):
        result = summarize_active_camping_facilities([
            _row(
                "CAMPING:1", applied_building_id=10,
                camping_general_site_count=4, camping_classification="general_only",
            ),
            _row(
                "CAMPING:3000:legacy", camping_general_site_count=7,
                camping_classification="general_only",
            ),
        ])

        self.assertEqual(result["camping_facility_count"], 1)
        # The linked record remains authoritative; a matching unlinked source is not double counted.
        self.assertEqual(result["camping_general_site_count"], 4)
        self.assertEqual(result["camping_matched_facility_count"], 1)
        self.assertEqual(result["camping_matched_site_count"], 4)
        self.assertEqual(result["camping_report_rate"], 100.0)
        detail = result["camping_classification_details"]["general_only"]
        self.assertEqual(detail["matched_facility_count"], 1)
        self.assertEqual(detail["matched_site_count"], 4)

    def test_unlinked_rows_dedupe_only_with_reliable_location_and_business_key(self):
        result = summarize_active_camping_facilities([
            _row("CAMPING:1", camping_auto_site_count=8, camping_classification="auto_only"),
            _row("CAMPING:2", camping_auto_site_count=9, camping_classification="auto_only"),
            _row(
                "CAMPING:3", road_norm=None, biz_name_norm=None,
                camping_glamping_site_count=2, camping_classification="glamping_only",
            ),
            _row(
                "CAMPING:4", road_norm=None, biz_name_norm=None,
                camping_glamping_site_count=3, camping_classification="glamping_only",
            ),
        ])

        self.assertEqual(result["camping_facility_count"], 3)
        self.assertEqual(result["camping_auto_site_count"], 9)
        self.assertEqual(result["camping_glamping_site_count"], 5)
        self.assertEqual(result["camping_classification_breakdown"]["auto_only"], 1)
        self.assertEqual(result["camping_classification_breakdown"]["glamping_only"], 2)
        self.assertEqual(result["camping_matched_facility_count"], 0)
        self.assertEqual(result["camping_report_rate"], 0.0)

    def test_classification_and_subtype_aggregates_include_confirmed_mixed(self):
        result = summarize_active_camping_facilities([
            _row(
                "CAMPING:5", road_norm="부산시캠핑로2", biz_name_norm="복합",
                camping_general_site_count=2, camping_caravan_site_count=3,
                camping_classification="confirmed_mixed",
            ),
        ])

        self.assertEqual(result["camping_site_count"], 5)
        self.assertEqual(result["camping_caravan_site_count"], 3)
        self.assertEqual(result["camping_classification_breakdown"]["confirmed_mixed"], 1)
        detail = result["camping_classification_details"]["confirmed_mixed"]
        self.assertEqual(detail["site_count"], 5)
        self.assertEqual(detail["matched_facility_count"], 0)
        self.assertEqual(detail["report_rate"], 0.0)


if __name__ == "__main__":
    unittest.main()