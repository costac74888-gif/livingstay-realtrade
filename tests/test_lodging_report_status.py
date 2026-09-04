import unittest

from lodging_report_status import summarize_building_report_status


class LodgingReportStatusTest(unittest.TestCase):
    def test_active_report_counts_in_numerator_and_denominator(self):
        self.assertEqual(
            summarize_building_report_status(
                [{"hygiene_type": "여관업", "biz_status_name": "영업/정상"}],
                "일반",
            ),
            (True, True),
        )

    def test_inactive_only_counts_in_denominator_only(self):
        self.assertEqual(
            summarize_building_report_status(
                [{"hygiene_type": "여관업", "biz_status_name": "폐업"}],
                "일반",
            ),
            (False, True),
        )

    def test_active_wins_when_active_and_inactive_coexist(self):
        self.assertEqual(
            summarize_building_report_status(
                [
                    {"hygiene_type": "여관업", "biz_status_name": "폐업"},
                    {"hygiene_type": "여관업", "biz_status_name": "영업/정상"},
                ],
                "일반",
            ),
            (True, True),
        )

    def test_unrelated_or_unmatched_report_is_excluded(self):
        self.assertEqual(summarize_building_report_status([], "일반"), (False, False))
        self.assertEqual(
            summarize_building_report_status(
                [{"hygiene_type": "농어촌민박", "biz_status_name": "영업/정상"}],
                "일반",
            ),
            (False, False),
        )


if __name__ == "__main__":
    unittest.main()