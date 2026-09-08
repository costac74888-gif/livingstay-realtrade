import pathlib
import unittest


class TransactionSyncBootContractTests(unittest.TestCase):
    def test_existing_operation_seed_survives_missing_deployment_archive(self):
        source = pathlib.Path("db.py").read_text(encoding="utf-8")
        start = source.index("def _seed_hotel_operation_metrics(cur):")
        end = source.index("\ndef ", start + 10)
        seed = source[start:end]

        self.assertIn("FROM hotel_operation_source_versions v", seed)
        self.assertIn("FROM hotel_operation_metrics m", seed)
        self.assertIn("if cur.fetchone():", seed)
        self.assertIn("재적재를 건너뜁니다.", seed)
        self.assertIn(
            "raise RuntimeError(f\"호텔 운영현황 승인 원본이 없습니다:",
            seed,
        )

    def test_existing_transaction_table_receives_updated_at_column(self):
        source = pathlib.Path("db.py").read_text(encoding="utf-8")
        self.assertIn(
            'ALTER TABLE transactions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP',
            source,
        )
        self.assertIn('SCHEMA_VERSION = "2026-09-08-01"', source)


if __name__ == "__main__":
    unittest.main()