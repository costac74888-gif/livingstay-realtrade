import unittest

from lodging_data_contract import (
    EXCLUDED_SOURCE_KEYS,
    GOVERNMENT_LODGING_SOURCES,
    SERVICE_CATEGORY_GENERAL,
    SERVICE_CATEGORY_LIVING,
    SERVICE_CATEGORY_TOURISM,
    SERVICE_CATEGORY_UNCLASSIFIED,
    STATUS_CLOSED,
    STATUS_EXCLUDED,
    STATUS_REVIEW,
    STATUS_TEMPORARILY_CLOSED,
    build_permit_identity,
    build_registry_permit_identity,
    build_source_snapshot_identity,
    classify_operation_status,
    is_in_active_statistics,
    is_visible_in_basic_list,
    normalize_reference_date,
    service_category_for_hygiene,
    source_is_supported,
)


class LodgingDataContractTests(unittest.TestCase):
    def test_exactly_eight_government_sources_are_supported(self):
        self.assertEqual(len(GOVERNMENT_LODGING_SOURCES), 8)
        self.assertTrue(all(source_is_supported(key) for key in GOVERNMENT_LODGING_SOURCES))
        self.assertIn("special_recreation", EXCLUDED_SOURCE_KEYS)
        self.assertFalse(source_is_supported("special_recreation"))

    def test_confirmed_service_category_mapping(self):
        self.assertEqual(service_category_for_hygiene("관광숙박업"), SERVICE_CATEGORY_TOURISM)
        self.assertEqual(service_category_for_hygiene("관광펜션업"), SERVICE_CATEGORY_TOURISM)
        self.assertEqual(service_category_for_hygiene("관광호텔"), SERVICE_CATEGORY_TOURISM)
        self.assertEqual(
            service_category_for_hygiene("휴양콘도미니엄업"),
            SERVICE_CATEGORY_TOURISM,
        )
        self.assertEqual(service_category_for_hygiene("숙박업 기타"), SERVICE_CATEGORY_GENERAL)
        self.assertEqual(service_category_for_hygiene("숙박업(생활)"), SERVICE_CATEGORY_LIVING)
        self.assertEqual(service_category_for_hygiene(""), SERVICE_CATEGORY_UNCLASSIFIED)
        self.assertIsNone(service_category_for_hygiene("알 수 없는 업태"))

    def test_building_use_is_not_part_of_service_category_contract(self):
        self.assertNotIn("building_use_type", GOVERNMENT_LODGING_SOURCES)
        self.assertNotIn("building_use_type", str(service_category_for_hygiene("관광호텔")))

    def test_status_contract_preserves_raw_state_meaning(self):
        self.assertTrue(is_visible_in_basic_list("영업/정상"))
        self.assertTrue(is_visible_in_basic_list("휴업"))
        self.assertTrue(is_in_active_statistics("영업/정상"))
        self.assertFalse(is_in_active_statistics("휴업"))
        self.assertEqual(classify_operation_status("폐업"), STATUS_CLOSED)
        self.assertEqual(classify_operation_status("취소/말소/만료/정지/중지"), STATUS_CLOSED)
        self.assertEqual(classify_operation_status("제외/삭제/전출"), STATUS_EXCLUDED)
        self.assertEqual(classify_operation_status(""), STATUS_REVIEW)

    def test_permit_identity_keeps_source_and_authority_separate(self):
        first = build_permit_identity("lodging", "1100000", "A/1")
        same = build_permit_identity("lodging", "1100000", "A/1")
        different_source = build_permit_identity("tourism_lodging", "1100000", "A/1")
        different_authority = build_permit_identity("lodging", "2600000", "A/1")
        self.assertEqual(first, same)
        self.assertNotEqual(first, different_source)
        self.assertNotEqual(first, different_authority)
        self.assertIsNone(build_permit_identity("lodging", "1100000", ""))
        with self.assertRaises(ValueError):
            build_permit_identity("special_recreation", "1100000", "A/1")

    def test_snapshot_identity_includes_normalized_reference_date(self):
        self.assertEqual(
            normalize_reference_date("2026.05.11 22:39:57"),
            "2026-05-11",
        )
        self.assertEqual(
            build_source_snapshot_identity(
                "lodging",
                "2026/5/11",
                "1100000",
                "A/1",
            ),
            "LODGING:2026-05-11:1100000:A%2F1",
        )
        self.assertNotEqual(
            build_source_snapshot_identity("lodging", "2026-05-11", "1100000", "A/1"),
            build_source_snapshot_identity("lodging", "2026-05-12", "1100000", "A/1"),
        )
        self.assertIsNone(
            build_source_snapshot_identity("lodging", "", "1100000", "A/1")
        )

    def test_registry_identity_remains_compatible_with_existing_importers(self):
        self.assertEqual(
            build_registry_permit_identity("lodging", "1100000", "M-1"),
            "M-1",
        )
        self.assertEqual(
            build_registry_permit_identity("rural_homestay", "1100000", "M-1"),
            "RURAL:1100000:M-1",
        )
        self.assertEqual(
            build_registry_permit_identity(
                "foreign_city_homestay", "1100000", "M-1"
            ),
            "AIRBNB:1100000:M-1",
        )


if __name__ == "__main__":
    unittest.main()