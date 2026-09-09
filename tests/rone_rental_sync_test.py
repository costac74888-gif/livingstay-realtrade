import unittest

from sync_rone_rental_benchmarks import build_records, month_date, quarter_date


def vacancy_row(period, value):
    return {
        "WRTTIME_IDTFR_ID": period,
        "CLS_ID": 500001,
        "CLS_NM": "전국",
        "ITM_ID": 100001,
        "ITM_NM": "공실률",
        "DTA_VAL": value,
    }


def income_row(period, group, value):
    return {
        "WRTTIME_IDTFR_ID": period,
        "GRP_FULLNM": group,
        "GRP_NM": group,
        "CLS_ID": 50005,
        "CLS_NM": "전체",
        "ITM_ID": 10001,
        "ITM_NM": "수익률",
        "DTA_VAL": value,
    }


class RoneRentalSyncTest(unittest.TestCase):
    def test_packaged_snapshot_keeps_results_available_when_cache_is_empty(self):
        from app import _packaged_rone_rental_benchmark

        regional = _packaged_rone_rental_benchmark("26")
        self.assertTrue(regional["available"])
        self.assertEqual(regional["benchmark"]["region_name"], "부산")
        self.assertEqual(regional["benchmark"]["income_yield"], 6.1281)
        self.assertEqual(regional["benchmark"]["vacancy_rate"], 8.4746)
        self.assertEqual(regional["benchmark"]["period"], "2026-07-01")
        self.assertEqual(regional["benchmark"]["vacancy_period"], "2026-04-01")
        self.assertEqual(regional["source"]["status"], "verified_snapshot")

        national = _packaged_rone_rental_benchmark("42")
        self.assertEqual(national["benchmark"]["region_name"], "전국")
        self.assertEqual(national["benchmark"]["income_yield"], 5.8398)

    def test_uses_officetel_yield_and_latest_national_vacancy(self):
        records = build_records(
            [income_row("202607", "전국", 5.84)],
            [vacancy_row("202601", 7.1), vacancy_row("202602", 7.5)],
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["period"], month_date("202607"))
        self.assertEqual(records[0]["vacancy_period"], quarter_date("202602"))
        self.assertAlmostEqual(records[0]["income_yield"], 5.84)
        self.assertAlmostEqual(records[0]["vacancy_rate"], 7.5)
        self.assertEqual(records[0]["property_type"], "officetel")
        self.assertEqual(records[0]["region_level"], "national")

    def test_rejects_invalid_quarter_and_vacancy(self):
        with self.assertRaises(ValueError):
            quarter_date("202305")
        with self.assertRaises(ValueError):
            build_records(
                [income_row("202607", "전국", 5.84)],
                [vacancy_row("202602", 101)],
            )

    def test_scheduled_stage_runs_weekly(self):
        import scheduled_sync
        stage = scheduled_sync.STAGE_MAP["rone_rental"]
        self.assertEqual(stage.command, ("sync_rone_rental_benchmarks.py",))
        self.assertTrue(stage.is_due(0))
        self.assertFalse(stage.is_due(1))


if __name__ == "__main__":
    unittest.main()