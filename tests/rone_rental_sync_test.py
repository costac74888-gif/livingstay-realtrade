import unittest

from sync_rone_rental_benchmarks import build_records, quarter_date


def row(period, cls_id, name, value):
    return {
        "WRTTIME_IDTFR_ID": period,
        "CLS_ID": cls_id,
        "CLS_NM": "전국" if cls_id == 500001 else "강원",
        "ITM_ID": 100001,
        "ITM_NM": name,
        "DTA_VAL": value,
    }


class RoneRentalSyncTest(unittest.TestCase):
    def test_pairs_same_period_and_annualizes_income(self):
        records = build_records(
            [row("202303", 500001, "소득수익률", 0.61),
             row("202302", 500011, "소득수익률", 0.8)],
            [row("202303", 500001, "공실률", 9.38),
             row("202301", 500011, "공실률", 12)],
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["period"], quarter_date("202303"))
        self.assertAlmostEqual(records[0]["income_yield"], 2.44)
        self.assertAlmostEqual(records[0]["vacancy_rate"], 9.38)
        self.assertEqual(records[0]["region_level"], "national")

    def test_rejects_invalid_quarter_and_vacancy(self):
        with self.assertRaises(ValueError):
            quarter_date("202305")
        with self.assertRaises(ValueError):
            build_records(
                [row("202303", 500001, "소득수익률", 0.61)],
                [row("202303", 500001, "공실률", 101)],
            )

    def test_scheduled_stage_runs_weekly(self):
        import scheduled_sync
        stage = scheduled_sync.STAGE_MAP["rone_rental"]
        self.assertEqual(stage.command, ("sync_rone_rental_benchmarks.py",))
        self.assertTrue(stage.is_due(0))
        self.assertFalse(stage.is_due(1))


if __name__ == "__main__":
    unittest.main()