import unittest
from unittest.mock import patch

from app import app
from db import _seed_hotel_operation_metrics


class FakeCursor:
    def __init__(self, building=None, rows=None, inserted_id=None):
        self.building = building
        self.rows = rows or []
        self.inserted_id = inserted_id
        self.execute_count = 0

    def execute(self, _sql, _params=None):
        self.execute_count += 1

    def fetchone(self):
        if self.building is not None and self.execute_count == 1:
            return self.building
        return {"id": self.inserted_id} if self.inserted_id else None

    def fetchall(self):
        return self.rows

    def close(self):
        pass


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def close(self):
        pass


class OperationBenchmarksIntegrationTests(unittest.TestCase):
    def test_deployment_seed_loads_the_real_approved_archive(self):
        cursor = FakeCursor(inserted_id=77)
        with patch("psycopg2.extras.execute_values") as execute_values:
            _seed_hotel_operation_metrics(cursor)
        values = execute_values.call_args.args[2]
        self.assertEqual(633, len(values))
        self.assertEqual(77, values[0][0])
        self.assertEqual(16, len({row[3] for row in values}))

    def test_endpoint_returns_sorted_real_shaped_rows_for_building_address_sido(self):
        rows = [
            {
                "region": "성남시", "adr": 141609, "occ": 76.35,
                "revpar": 108118, "foreign": 23.6, "reference_year": 2024,
                "source_name": "한국호텔업협회 호텔업 운영현황",
                "source_file": "2024_호텔업운영현황_1788781907828.zip",
            },
            {
                "region": "양평군", "adr": 166688, "occ": 58.34,
                "revpar": 97246, "foreign": 0.5, "reference_year": 2024,
                "source_name": "한국호텔업협회 호텔업 운영현황",
                "source_file": "2024_호텔업운영현황_1788781907828.zip",
            },
        ]
        cursor = FakeCursor(building={"sido": "경기"}, rows=rows)
        with patch("app.get_conn", return_value=FakeConnection(cursor)):
            with app.test_client() as client:
                with client.session_transaction() as session:
                    session["user_id"] = 1
                response = client.get(
                    "/api/analysis/operation-benchmarks?building_id=101"
                )
        payload = response.get_json()
        self.assertEqual(200, response.status_code)
        self.assertEqual("경기", payload["sido"])
        self.assertEqual(["성남시", "양평군"], [
            item["region"] for item in payload["items"]
        ])
        self.assertEqual(2024, payload["source"]["reference_year"])

    def test_endpoint_uses_approved_archive_when_production_tables_are_empty(self):
        cursor = FakeCursor(building={"sido": "경기"}, rows=[])
        fallback = ([{
            "region": "용인시", "adr": 150000.0, "occ": 60.0,
            "revpar": 90000.0, "foreign": 2.0,
        }], {
            "name": "한국호텔업협회 호텔업 운영현황",
            "file": "approved.zip", "reference_year": 2024,
        })
        with patch("app.get_conn", return_value=FakeConnection(cursor)), \
                patch("app._approved_operation_benchmarks", return_value=fallback):
            with app.test_client() as client:
                with client.session_transaction() as session:
                    session["user_id"] = 1
                response = client.get(
                    "/api/analysis/operation-benchmarks?building_id=101"
                )
        payload = response.get_json()
        self.assertEqual(200, response.status_code)
        self.assertEqual("용인시", payload["items"][0]["region"])
        self.assertEqual(2024, payload["source"]["reference_year"])


if __name__ == "__main__":
    unittest.main()