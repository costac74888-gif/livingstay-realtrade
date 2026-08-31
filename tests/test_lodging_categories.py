import json
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lodging_categories import (
    GENERAL_LODGING_HYGIENE_TYPES,
    TARGET_LODGING_HYGIENE_TYPES,
    is_target_lodging_hygiene,
)
from lodging_classification import (
    CLASSIFICATION_CONFIDENCE_HIGH,
    CLASSIFICATION_SOURCE_ACTIVE_PERMIT,
    CLASSIFICATION_SOURCE_BUILDING_REGISTRY,
    BUILDING_REGISTRY_LINEAGE_SOURCES,
    classify_building_use,
    choose_primary_lodging_type,
    is_active_status,
    iter_chunks,
    lodging_type_for_building_registry_detail,
    lodging_type_for_hygiene,
    lodging_subtype_for_hygiene,
    recover_classification_provenance,
    should_protect_from_active_permit_reclassification,
)
from sync_lodgings import PROGRESS_TARGET_HYGIENES, _load_progress


class _ProgressCursor:
    def __init__(self, value):
        self.value = value

    def execute(self, *_args, **_kwargs):
        pass

    def fetchone(self):
        return {"value": self.value}


class LodgingCategoriesTest(unittest.TestCase):
    def test_confirmed_general_types_are_collected(self):
        self.assertEqual(
            GENERAL_LODGING_HYGIENE_TYPES,
            frozenset({"일반호텔", "여관업", "여인숙업"}),
        )
        for value in GENERAL_LODGING_HYGIENE_TYPES | {"숙박업(생활)"}:
            self.assertTrue(is_target_lodging_hygiene(value))

    def test_obsolete_general_label_and_ambiguous_types_are_not_collected(self):
        for value in ("숙박업(일반)", "숙박업 기타", "관광호텔", "휴양콘도미니엄업"):
            self.assertNotIn(value, TARGET_LODGING_HYGIENE_TYPES)
            self.assertFalse(is_target_lodging_hygiene(value))

    def test_old_scope_checkpoint_restarts_before_general_lodging_pages_are_skipped(self):
        old_living_only_checkpoint = json.dumps({
            "next_page": 200,
            "total_count": 58649,
            "target_hygienes": ["숙박업(생활)"],
        })
        self.assertEqual(
            _load_progress(_ProgressCursor(old_living_only_checkpoint)),
            {"next_page": 1, "total_count": None},
        )

    def test_matching_scope_checkpoint_continues_safely(self):
        current_scope_checkpoint = json.dumps({
            "next_page": 200,
            "total_count": 58649,
            "target_hygienes": PROGRESS_TARGET_HYGIENES,
        })
        self.assertEqual(
            _load_progress(_ProgressCursor(current_scope_checkpoint)),
            {"next_page": 200, "total_count": 58649},
        )

    def test_legal_lodging_type_mapping(self):
        self.assertEqual(lodging_type_for_hygiene("숙박업(생활)"), "생활")
        self.assertEqual(lodging_type_for_hygiene("일반호텔"), "일반")
        self.assertEqual(lodging_type_for_hygiene("관광호텔업"), "관광")
        self.assertEqual(lodging_type_for_hygiene("외국인관광도시민박업"), "에어비앤비")
        self.assertEqual(lodging_type_for_hygiene("야영장업"), "캠핑")
        self.assertEqual(lodging_type_for_hygiene("자동차야영장업"), "캠핑")
        self.assertEqual(
            lodging_subtype_for_hygiene("자동차야영장업"), "자동차야영"
        )
        self.assertEqual(lodging_type_for_hygiene("한옥체험업"), "한옥")

    def test_specific_law_registration_wins_over_deemed_hygiene_report(self):
        self.assertEqual(
            choose_primary_lodging_type(["일반호텔", "관광호텔업"]),
            "관광",
        )
        self.assertEqual(
            choose_primary_lodging_type(
                ["숙박업(생활)", "외국인관광도시민박업"]
            ),
            "에어비앤비",
        )

    def test_different_specific_law_types_are_not_arbitrarily_selected(self):
        self.assertEqual(
            choose_primary_lodging_type(["야영장업", "한옥체험업"]),
            "복합",
        )
        for other_type in (
            "외국인관광도시민박업",
            "농어촌민박업",
            "야영장업",
            "한옥체험업",
        ):
            with self.subTest(other_type=other_type):
                self.assertEqual(
                    choose_primary_lodging_type(["관광호텔업", other_type]),
                    "복합",
                )

    def test_only_exact_normal_status_is_active(self):
        self.assertTrue(is_active_status("영업/정상"))
        for status in ("폐업", "휴업", "취소", "말소", "만료", "", None):
            self.assertFalse(is_active_status(status))

    def test_building_use_is_independent_from_lodging_business_type(self):
        self.assertEqual(classify_building_use("단독주택"), "주택")
        self.assertEqual(classify_building_use("청소년수련시설"), "수련시설")
        self.assertEqual(classify_building_use("관광숙박시설"), "숙박시설")
        self.assertEqual(classify_building_use(None), "확인불가")

    def test_bulk_updates_over_one_hundred_are_split_without_loss(self):
        chunks = list(iter_chunks(list(range(250)), 100))

        self.assertEqual([len(chunk) for chunk in chunks], [100, 100, 50])
        self.assertEqual([item for chunk in chunks for item in chunk], list(range(250)))

    def test_building_registry_provenance_wins_over_conflicting_active_permit(self):
        self.assertEqual(
            recover_classification_provenance(
                "생활",
                "숙박시설 생활숙박시설",
                next(iter(BUILDING_REGISTRY_LINEAGE_SOURCES)),
                "2026-08-30",
                ["일반호텔"],
            ),
            (
                CLASSIFICATION_SOURCE_BUILDING_REGISTRY,
                CLASSIFICATION_CONFIDENCE_HIGH,
            ),
        )

    def test_building_registry_detail_is_reparsed_before_recovery(self):
        self.assertEqual(
            lodging_type_for_building_registry_detail("숙박시설 콘도미니엄"),
            "관광",
        )
        self.assertEqual(
            lodging_type_for_building_registry_detail(
                "생활숙박시설 및 일반숙박시설"
            ),
            "복합",
        )
        self.assertEqual(
            lodging_type_for_building_registry_detail("건물명 기반 일반숙박 분류"),
            None,
        )

    def test_matching_active_permit_provenance_is_recovered(self):
        self.assertEqual(
            recover_classification_provenance(
                "에어비앤비",
                "외국인관광도시민박업",
                "airbnb_import",
                None,
                ["숙박업(생활)", "외국인관광도시민박업"],
            ),
            (
                CLASSIFICATION_SOURCE_ACTIVE_PERMIT,
                CLASSIFICATION_CONFIDENCE_HIGH,
            ),
        )

    def test_official_camping_permit_recovers_active_permit_provenance(self):
        self.assertEqual(
            lodging_type_for_hygiene("일반야영장업"),
            "캠핑",
        )
        self.assertEqual(
            choose_primary_lodging_type(["일반야영장업"]),
            "캠핑",
        )
        self.assertEqual(
            recover_classification_provenance(
                "캠핑",
                None,
                "camping_import",
                None,
                ["일반야영장업"],
            ),
            (
                CLASSIFICATION_SOURCE_ACTIVE_PERMIT,
                CLASSIFICATION_CONFIDENCE_HIGH,
            ),
        )

    def test_conflicting_or_unverifiable_provenance_stays_missing(self):
        self.assertEqual(
            recover_classification_provenance(
                "일반", "숙박업(생활)", "original", "2026-08-30", ["숙박업(생활)"]
            ),
            (None, None),
        )
        self.assertEqual(
            recover_classification_provenance(
                "일반", "건물명 기반 일반숙박 분류", "original", "2026-08-30", []
            ),
            (None, None),
        )
        self.assertEqual(
            recover_classification_provenance(
                "일반", "숙박시설", "original", "2026-08-30", ["숙박업(생활)"]
            ),
            (None, None),
        )
        self.assertEqual(
            recover_classification_provenance(
                "관광",
                "숙박시설 콘도미니엄",
                "original",
                "2026-08-30",
                [],
            ),
            (None, None),
        )

    def test_recovered_source_does_not_broaden_protected_set(self):
        self.assertFalse(
            should_protect_from_active_permit_reclassification(
                "일반",
                "생활",
                "숙박시설",
                "original",
                CLASSIFICATION_SOURCE_BUILDING_REGISTRY,
            )
        )
        self.assertTrue(
            should_protect_from_active_permit_reclassification(
                "관광",
                "일반",
                "숙박시설 콘도미니엄",
                "original",
                CLASSIFICATION_SOURCE_BUILDING_REGISTRY,
            )
        )


if __name__ == "__main__":
    unittest.main()