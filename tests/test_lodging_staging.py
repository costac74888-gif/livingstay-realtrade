import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lodging_staging import (
    APPROVAL_STATUSES,
    STAGING_STATUSES,
    assert_development_connection,
    _diff_kind,
    _require_admin_actor,
    assert_development_staging,
    canonical_source_key,
    inspect_csv,
    normalize_source_row,
)
from lodging_data_contract import (
    SERVICE_CATEGORY_GENERAL,
    SERVICE_CATEGORY_TOURISM,
    SERVICE_CATEGORY_UNCLASSIFIED,
)


class LodgingStagingTests(unittest.TestCase):
    def test_all_eight_sources_and_legacy_aliases_are_available(self):
        for source in (
            "tourism_lodging",
            "tourism_pension",
            "rural_homestay",
            "lodging",
            "foreign_city_homestay",
            "general_camping",
            "auto_camping",
            "hanok",
        ):
            self.assertEqual(canonical_source_key(source), source)
        self.assertEqual(canonical_source_key("airbnb"), "foreign_city_homestay")
        with self.assertRaises(ValueError):
            canonical_source_key("special_recreation")

    def test_standard_row_keeps_raw_type_separate_from_service_category(self):
        row = normalize_source_row(
            "lodging",
            {
                "개방자치단체코드": "1100000",
                "관리번호": "A-1",
                "사업장명": "호텔",
                "업태구분명": "관광호텔",
                "영업상태명": "영업/정상",
                "도로명주소": "서울특별시 중구 세종대로 1",
            },
            "2026-09-03",
            2,
        )
        self.assertEqual(row["raw_hygiene_type"], "관광호텔")
        self.assertEqual(row["service_category"], SERVICE_CATEGORY_TOURISM)
        self.assertEqual(row["row_state"], "validated")
        self.assertEqual(row["status_bucket"], "active")
        self.assertEqual(row["permit_number"], "A-1")

    def test_blank_type_is_unclassified_and_held(self):
        row = normalize_source_row(
            "lodging",
            {
                "개방자치단체코드": "1100000",
                "관리번호": "A-2",
                "사업장명": "확인필요",
                "업태구분명": "",
                "영업상태명": "영업/정상",
            },
            "2026-09-03",
            2,
        )
        self.assertIsNone(row["raw_hygiene_type"])
        self.assertEqual(row["service_category"], SERVICE_CATEGORY_UNCLASSIFIED)
        self.assertEqual(row["row_state"], "review_required")
        self.assertIn("업태 공백", row["review_reason"])

    def test_unknown_type_and_status_are_held(self):
        row = normalize_source_row(
            "lodging",
            {
                "개방자치단체코드": "1100000",
                "관리번호": "A-3",
                "사업장명": "검토필요",
                "업태구분명": "새로운업태",
                "영업상태명": "알수없음",
            },
            "2026-09-03",
            2,
        )
        self.assertEqual(row["row_state"], "review_required")
        self.assertIn("알 수 없는 업태", row["review_reason"])
        self.assertIn("알 수 없는 영업상태", row["review_reason"])

    def test_missing_identity_is_held_without_silent_key(self):
        row = normalize_source_row(
            "hanok",
            {
                "개방자치단체코드": "",
                "관리번호": "",
                "사업장명": "한옥",
                "영업상태명": "영업/정상",
            },
            "2026-09-03",
            2,
        )
        self.assertEqual(row["row_state"], "review_required")
        self.assertIsNone(row["permit_number"])
        self.assertIn("관리번호 없음", row["review_reason"])

    def test_inspect_csv_is_db_free_and_preserves_duplicate_rows_for_review(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "lodging.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "개방자치단체코드",
                        "관리번호",
                        "사업장명",
                        "업태구분명",
                        "영업상태명",
                    ],
                )
                writer.writeheader()
                writer.writerow({
                    "개방자치단체코드": "1100000",
                    "관리번호": "A-1",
                    "사업장명": "일반호텔",
                    "업태구분명": "일반호텔",
                    "영업상태명": "영업/정상",
                })
                writer.writerow({
                    "개방자치단체코드": "1100000",
                    "관리번호": "A-1",
                    "사업장명": "일반호텔",
                    "업태구분명": "일반호텔",
                    "영업상태명": "폐업",
                })
            result = inspect_csv("lodging", str(path), "2026-09-03")
        self.assertEqual(result["total_rows"], 2)
        self.assertEqual(result["valid_rows"], 0)
        self.assertEqual(result["review_rows"], 2)
        self.assertEqual(result["status"], "review_required")
        self.assertEqual(result["rows"][0]["service_category"], SERVICE_CATEGORY_GENERAL)
        self.assertEqual(
            result["rows"][0]["snapshot_key"],
            result["rows"][1]["snapshot_key"],
        )
        self.assertTrue(
            all(row["row_state"] == "review_required" for row in result["rows"])
        )

    def test_status_constants_are_explicit_for_schema_contract(self):
        self.assertEqual(
            STAGING_STATUSES,
            (
                "uploaded",
                "parsed",
                "validating",
                "review_required",
                "validated",
                "approved",
                "dry_run",
                "applied",
                "failed",
            ),
        )
        self.assertEqual(APPROVAL_STATUSES, ("draft", "approved", "dry_run", "applied", "failed"))

    def test_existing_registry_rows_are_classified_before_approval(self):
        item = {
            "row_state": "validated",
            "biz_name": "호텔",
            "road_address": "서울 중구 세종대로 1",
            "jibun_address": None,
            "raw_hygiene_type": "일반호텔",
            "raw_status": "영업/정상",
        }
        existing = {
            "biz_name": "호텔",
            "road_address": "서울 중구 세종대로 1",
            "jibun_address": None,
            "hygiene_type": "일반호텔",
            "biz_status_name": "영업/정상",
        }
        self.assertEqual(_diff_kind(item, None), "new")
        self.assertEqual(_diff_kind(item, existing), "unchanged")
        self.assertEqual(
            _diff_kind({**item, "raw_status": "휴업"}, existing),
            "status_change",
        )
        self.assertEqual(
            _diff_kind({**item, "biz_name": "새 호텔"}, existing),
            "changed",
        )

    def test_production_database_and_anonymous_approval_are_blocked(self):
        production_conn = unittest.mock.MagicMock()
        with (
            patch.dict(
                "os.environ",
                {"PROD_DATABASE_URL": "postgresql://redacted"},
                clear=False,
            ),
            patch(
                "lodging_staging.psycopg2.connect",
                return_value=production_conn,
            ),
            patch(
                "lodging_staging._database_fingerprint",
                side_effect=[("same", "same", 5432), ("same", "same", 5432)],
            ),
        ):
            with self.assertRaises(RuntimeError):
                assert_development_connection(unittest.mock.MagicMock())
        production_conn.close.assert_called_once()
        with self.assertRaises(ValueError):
            _require_admin_actor(None, "승인")
        self.assertEqual(_require_admin_actor("7", "승인"), 7)


if __name__ == "__main__":
    unittest.main()