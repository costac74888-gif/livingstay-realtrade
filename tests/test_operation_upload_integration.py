import io
import unittest

from app import app


class OperationUploadIntegrationTests(unittest.TestCase):
    def test_same_period_sales_and_reservation_files_are_combined_immediately(self):
        with app.test_client() as client:
            with client.session_transaction() as session:
                session["user_id"] = 1
            response = client.post(
                "/api/analysis/operation-upload",
                data={
                    "files": [
                        (
                            io.BytesIO(
                                "기간,객실매출\n2026-01,502200000\n".encode()
                            ),
                            "sales.csv",
                        ),
                        (
                            io.BytesIO(
                                "기간,판매객실 수\n2026-01,3100\n".encode()
                            ),
                            "reservations.csv",
                        ),
                    ],
                },
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["retained"])
        self.assertEqual(payload["processed_file_count"], 2)
        self.assertEqual(payload["result"]["period_start"], "2026-01-01")
        self.assertEqual(payload["result"]["period_end"], "2026-01-31")
        self.assertEqual(payload["result"]["room_revenue"], 502_200_000)
        self.assertEqual(payload["result"]["sold_rooms"], 3_100)
        self.assertEqual(payload["result"]["occupancy_days"], 31)
        self.assertEqual(payload["result"]["adr"], 162_000)
        self.assertEqual(
            payload["result"]["adr_source"],
            "calculated_from_room_revenue",
        )


if __name__ == "__main__":
    unittest.main()