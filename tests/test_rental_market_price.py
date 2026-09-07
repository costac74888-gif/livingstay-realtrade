import unittest
from unittest.mock import patch

import app as application


class _Cursor:
    def __init__(self, rows):
        self.rows = iter(rows)
        self.executions = []

    def execute(self, query, params=None):
        self.executions.append((query, params or []))

    def fetchone(self):
        return next(self.rows)

    def close(self):
        pass


class _Connection:
    def __init__(self, rows):
        self.cursor_instance = _Cursor(rows)

    def cursor(self):
        return self.cursor_instance

    def close(self):
        pass


class RentalMarketPriceTest(unittest.TestCase):
    def test_returns_exact_area_median_with_evidence(self):
        connection = _Connection([
            {"building_name": "테스트", "sgg_cd": "11110", "umd_nm": "청운동", "jibun": "1", "parcel_building_count": 1},
            {
                "median_price": 9876,
                "latest_deal_date": "2026-08-19",
                "sample_count": 3,
                "min_area": 32.45,
                "max_area": 32.51,
                "transactions": [
                    {"deal_date": "2026-08-19", "area_sqm": 32.5, "price": 10000},
                    {"deal_date": "2026-07-01", "area_sqm": 32.45, "price": 9876},
                    {"deal_date": "2026-06-01", "area_sqm": 32.51, "price": 9000},
                ],
            },
        ])
        with patch.object(application, "get_conn", return_value=connection):
            response = application.app.test_client().get(
                "/api/analysis/rental-market-price?building_id=101&area_sqm=32.5"
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["match_type"], "exact")
        self.assertEqual(payload["median_price"], 9876)
        self.assertEqual(payload["latest_deal_date"], "2026-08-19")
        self.assertEqual(payload["sample_count"], 3)
        self.assertEqual(len(payload["transactions"]), payload["sample_count"])
        self.assertEqual(
            set(payload["transactions"][0]),
            {"deal_date", "area_sqm", "price", "area_match"},
        )
        self.assertTrue(all(row["area_match"] == "exact" for row in payload["transactions"]))
        query, params = connection.cursor_instance.executions[1]
        self.assertIn("percentile_cont(0.5)", query)
        self.assertIn("INTERVAL '36 months'", query)
        self.assertIn("deal_date <= TO_CHAR(CURRENT_DATE", query)
        self.assertIn("transaction_scope = 'unit'", query)
        self.assertNotIn("deal_type = '매매'", query)
        self.assertEqual(params[-2:], [32.0, 33.0])

    def test_brokerage_classification_does_not_exclude_sale_feed_rows(self):
        """실제 deal_type 값(중개거래/직거래)은 매매 여부 필터로 쓰지 않는다."""
        connection = _Connection([
            {"building_name": "테스트", "sgg_cd": "11110", "umd_nm": "청운동", "jibun": "1", "parcel_building_count": 1},
            {
                "median_price": 7500,
                "latest_deal_date": "2026-08-20",
                "sample_count": 2,
                "min_area": 40,
                "max_area": 40,
                "transactions": [
                    {"deal_date": "2026-08-20", "area_sqm": 40, "price": 7000},
                    {"deal_date": "2026-08-19", "area_sqm": 40, "price": 8000},
                ],
            },
        ])
        with patch.object(application, "get_conn", return_value=connection):
            response = application.app.test_client().get(
                "/api/analysis/rental-market-price?building_id=101&area_sqm=40"
            )
        self.assertTrue(response.get_json()["ok"])
        market_query = connection.cursor_instance.executions[1][0]
        self.assertNotIn("deal_type", market_query)

    def test_similar_area_sample_labels_each_transaction(self):
        connection = _Connection([
            {"building_name": "테스트", "sgg_cd": "11110", "umd_nm": "청운동", "jibun": "1", "parcel_building_count": 1},
            {"median_price": None, "latest_deal_date": None, "sample_count": 1, "min_area": 40, "max_area": 40},
            {
                "median_price": 7200, "latest_deal_date": "2026-08-20",
                "sample_count": 3, "min_area": 40, "max_area": 43.5,
                "transactions": [
                    {"deal_date": "2026-08-20", "area_sqm": 40, "price": 7000},
                    {"deal_date": "2026-08-19", "area_sqm": 42, "price": 7200},
                    {"deal_date": "2026-08-18", "area_sqm": 43.5, "price": 7400},
                ],
            },
        ])
        with patch.object(application, "get_conn", return_value=connection):
            response = application.app.test_client().get(
                "/api/analysis/rental-market-price?building_id=101&area_sqm=40"
            )

        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["match_type"], "similar")
        self.assertEqual(
            [row["area_match"] for row in payload["transactions"]],
            ["exact", "similar", "similar"],
        )

    def test_fails_closed_when_evidence_count_does_not_match_calculation_sample(self):
        connection = _Connection([
            {"building_name": "테스트", "sgg_cd": "11110", "umd_nm": "청운동", "jibun": "1", "parcel_building_count": 1},
            {
                "median_price": 7200, "latest_deal_date": "2026-08-20",
                "sample_count": 2, "min_area": 40, "max_area": 40,
                "transactions": [
                    {"deal_date": "2026-08-20", "area_sqm": 40, "price": 7200},
                ],
            },
        ])
        with patch.object(application, "get_conn", return_value=connection):
            response = application.app.test_client().get(
                "/api/analysis/rental-market-price?building_id=101&area_sqm=40"
            )

        self.assertEqual(response.status_code, 500)
        self.assertFalse(response.get_json()["ok"])
        self.assertNotIn("median_price", response.get_json())

    def test_expands_to_similar_area_and_reports_no_data(self):
        connection = _Connection([
            {"building_name": "테스트", "sgg_cd": "11110", "umd_nm": "청운동", "jibun": "1", "parcel_building_count": 1},
            {"median_price": None, "latest_deal_date": None, "sample_count": 0, "min_area": None, "max_area": None},
            {"median_price": None, "latest_deal_date": None, "sample_count": 0, "min_area": None, "max_area": None},
        ])
        with patch.object(application, "get_conn", return_value=connection):
            response = application.app.test_client().get(
                "/api/analysis/rental-market-price?building_id=101&area_sqm=40"
            )

        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(payload["ok"])
        self.assertIn("자료", payload["reason"])
        self.assertIn("2건 미만", payload["reason"])
        self.assertEqual(connection.cursor_instance.executions[2][1][-2:], [36.0, 44.0])

    def test_same_parcel_multiple_buildings_fail_closed(self):
        connection = _Connection([
            {"building_name": "선택 건물", "sgg_cd": "11110", "umd_nm": "청운동", "jibun": "1", "parcel_building_count": 2},
            {"median_price": None, "latest_deal_date": None, "sample_count": 0, "min_area": None, "max_area": None},
            {"median_price": None, "latest_deal_date": None, "sample_count": 0, "min_area": None, "max_area": None},
        ])
        with patch.object(application, "get_conn", return_value=connection):
            response = application.app.test_client().get(
                "/api/analysis/rental-market-price?building_id=101&area_sqm=40"
            )
        payload = response.get_json()
        self.assertFalse(payload["ok"])
        self.assertIn("2건 미만", payload["reason"])
        self.assertEqual(len(connection.cursor_instance.executions), 3)
        for query, params in connection.cursor_instance.executions[1:]:
            self.assertIn("master_building_id = %s", query)
            self.assertNotIn("sgg_cd = %s", query)
            self.assertEqual(params[0], 101)

    def test_same_parcel_uses_only_selected_building_transactions(self):
        connection = _Connection([
            {"building_name": "선택 건물", "sgg_cd": "11110", "umd_nm": "청운동", "jibun": "1", "parcel_building_count": 2},
            {
                "median_price": 7200, "latest_deal_date": "2026-08-20",
                "sample_count": 2, "min_area": 40, "max_area": 40,
                "transactions": [
                    {"deal_date": "2026-08-20", "area_sqm": 40, "price": 7000},
                    {"deal_date": "2026-08-19", "area_sqm": 40, "price": 7400},
                ],
            },
        ])
        with patch.object(application, "get_conn", return_value=connection):
            response = application.app.test_client().get(
                "/api/analysis/rental-market-price?building_id=101&area_sqm=40"
            )
        self.assertTrue(response.get_json()["ok"])
        query, params = connection.cursor_instance.executions[1]
        self.assertIn("master_building_id = %s", query)
        self.assertNotIn("sgg_cd = %s", query)
        self.assertEqual(params[0], 101)

    def test_one_transaction_is_reported_as_insufficient(self):
        connection = _Connection([
            {"building_name": "테스트", "sgg_cd": "11110", "umd_nm": "청운동", "jibun": "1", "parcel_building_count": 1},
            {"median_price": 5000, "latest_deal_date": "2026-08-01", "sample_count": 1, "min_area": 40, "max_area": 40},
            {"median_price": 5000, "latest_deal_date": "2026-08-01", "sample_count": 1, "min_area": 40, "max_area": 40},
        ])
        with patch.object(application, "get_conn", return_value=connection):
            response = application.app.test_client().get(
                "/api/analysis/rental-market-price?building_id=101&area_sqm=40"
            )
        payload = response.get_json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["sample_count"], 1)
        self.assertIn("2건 미만", payload["reason"])

    def test_rejects_missing_area_without_querying_database(self):
        with patch.object(application, "get_conn") as get_conn:
            response = application.app.test_client().get(
                "/api/analysis/rental-market-price?building_id=101"
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn("전용면적", response.get_json()["reason"])
        get_conn.assert_not_called()


if __name__ == "__main__":
    unittest.main()