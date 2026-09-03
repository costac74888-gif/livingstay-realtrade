import unittest
from unittest.mock import patch

from apply_lodging_promotion import apply_manifest, build_registry_record


class ApplyLodgingPromotionTest(unittest.TestCase):
    def test_existing_room_and_link_are_preserved_when_csv_is_blank(self):
        payload = {
            "source_key": "rural_homestay",
            "permit_number": "RURAL:1:A",
            "biz_name": "숙소",
            "status_bucket": "active",
            "raw_status": "영업/정상",
            "road_address": "서울시 중구 세종대로 1",
            "raw_record": {"객실수": ""},
            "production_match_state": "new_building_candidate",
            "production_building_id": None,
        }
        result = build_registry_record(
            payload,
            {
                "room_count": 27,
                "camping_site_count": None,
                "applied_building_id": 101,
            },
        )
        self.assertEqual(result["room_count"], 27)
        self.assertEqual(result["applied_building_id"], 101)

    def test_new_active_unique_match_is_linked(self):
        payload = {
            "source_key": "tourism_lodging",
            "permit_number": "TOUR:1:A",
            "biz_name": "호텔",
            "status_bucket": "active",
            "raw_status": "영업/정상",
            "raw_record": {"한실수": "2", "양실수": "8"},
            "production_match_state": "existing_building",
            "production_building_id": 55,
        }
        result = build_registry_record(payload)
        self.assertEqual(result["room_count"], 10)
        self.assertEqual(result["applied_building_id"], 55)

    def test_inactive_or_ambiguous_new_row_is_not_linked(self):
        payload = {
            "source_key": "lodging",
            "permit_number": "L:1",
            "biz_name": "폐업 숙소",
            "status_bucket": "closed",
            "raw_status": "폐업",
            "raw_record": {},
            "production_match_state": "existing_building",
            "production_building_id": 77,
        }
        self.assertIsNone(build_registry_record(payload)["applied_building_id"])
        payload["status_bucket"] = "active"
        payload["production_match_state"] = "ambiguous_existing_building"
        self.assertIsNone(build_registry_record(payload)["applied_building_id"])

    def test_camping_sites_do_not_become_room_count(self):
        payload = {
            "source_key": "general_camping",
            "permit_number": "CAMP:1",
            "biz_name": "캠핑장",
            "status_bucket": "active",
            "raw_status": "영업/정상",
            "raw_record": {"객실수": "20", "야영사이트수": "45"},
        }
        result = build_registry_record(payload)
        self.assertIsNone(result["room_count"])
        self.assertEqual(result["camping_site_count"], 45)

    def test_phone_is_stored_as_digits_only(self):
        payload = {
            "source_key": "lodging",
            "permit_number": "L:2",
            "biz_name": "숙소",
            "status_bucket": "active",
            "raw_status": "영업/정상",
            "raw_record": {"전화번호": "02-1234-5678"},
        }
        self.assertEqual(build_registry_record(payload)["phone"], "0212345678")

    def test_facility_area_is_preserved_for_new_record(self):
        payload = {
            "source_key": "lodging",
            "permit_number": "L:3",
            "biz_name": "숙소",
            "status_bucket": "active",
            "raw_status": "영업/정상",
            "raw_record": {"시설규모": "1,234.50"},
        }
        self.assertEqual(
            str(build_registry_record(payload)["facility_area"]),
            "1234.50",
        )

    @patch("apply_lodging_promotion._load_manifest")
    def test_apply_rejects_manifest_before_completed_dry_run(self, load_manifest):
        load_manifest.return_value = (
            {"status": "approved", "run_id": "run-a"},
            [],
        )
        with self.assertRaisesRegex(ValueError, "dry-run"):
            apply_manifest(1, confirm_run_id="run-a")

    @patch("apply_lodging_promotion._load_manifest")
    def test_apply_rejects_wrong_confirmation_run_id(self, load_manifest):
        load_manifest.return_value = (
            {"status": "dry_run", "run_id": "run-a"},
            [],
        )
        with self.assertRaisesRegex(ValueError, "run_id"):
            apply_manifest(1, confirm_run_id="run-b")


if __name__ == "__main__":
    unittest.main()