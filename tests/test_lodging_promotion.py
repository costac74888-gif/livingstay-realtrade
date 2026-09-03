import unittest

from lodging_promotion import (
    _apply_review_decision,
    _build_targets,
    _validate_target_admission,
)


class LodgingPromotionTest(unittest.TestCase):
    def test_new_row_uses_unique_existing_building_without_auto_create(self):
        staging = [
            {
                "source_row_id": 1,
                "batch_id": 10,
                "permit_number": "P-1",
                "biz_name": "숙소",
                "raw_status": "영업/정상",
                "status_bucket": "active",
                "road_address": "서울특별시 중구 세종대로 1",
                "jibun_address": None,
                "raw_hygiene_type": "숙박업(일반)",
                "raw_record": {},
            }
        ]
        buildings = [
            {
                "id": 7,
                "road_address": "서울특별시 중구 세종대로 1",
                "jibun_address": None,
                "sgg_cd": None,
                "umd_nm": None,
                "jibun": None,
            }
        ]
        targets, summary = _build_targets(staging, [], buildings)
        self.assertEqual(targets[0]["action"], "insert")
        self.assertEqual(targets[0]["production_match_state"], "existing_building")
        self.assertEqual(targets[0]["production_building_id"], 7)
        self.assertEqual(summary["would_auto_create_master_buildings"], 0)

    def test_existing_link_is_preserved(self):
        staging = [
            {
                "source_row_id": 2,
                "batch_id": 10,
                "permit_number": "P-2",
                "biz_name": "새 이름",
                "raw_status": "영업/정상",
                "status_bucket": "active",
                "road_address": "새 주소",
                "jibun_address": None,
                "raw_hygiene_type": "숙박업(일반)",
                "raw_record": {"객실수": ""},
                "diff_kind": "changed",
            }
        ]
        registry = [
            {
                "permit_number": "P-2",
                "biz_name": "옛 이름",
                "biz_status_name": "영업/정상",
                "room_count": 10,
                "hygiene_type": "숙박업(일반)",
                "applied_building_id": 99,
                "road_address": "옛 주소",
                "jibun_address": None,
            }
        ]
        targets, summary = _build_targets(staging, registry, [])
        self.assertEqual(targets[0]["action"], "update")
        self.assertEqual(targets[0]["existing_applied_building_id"], 99)
        self.assertEqual(summary["existing_links_preserved"], 1)

    def test_duplicate_permit_is_rejected(self):
        targets = [
            {"payload": {"permit_number": "P-1", "row_state": "validated"}},
            {"payload": {"permit_number": "P-1", "row_state": "validated"}},
        ]
        with self.assertRaisesRegex(RuntimeError, "중복"):
            _validate_target_admission(targets, allow_manual_review=True)

    def test_unresolved_review_row_blocks_approval_or_apply(self):
        targets = [
            {
                "payload": {
                    "permit_number": "P-2",
                    "row_state": "review_required",
                }
            }
        ]
        with self.assertRaisesRegex(RuntimeError, "수동 검토"):
            _validate_target_admission(targets, allow_manual_review=False)
        self.assertEqual(
            _validate_target_admission(targets, allow_manual_review=True),
            1,
        )

    def test_review_include_creates_resolved_copy_without_mutating_original(self):
        target = {
            "source_row_id": 3,
            "action": "insert",
            "payload": {
                "permit_number": "P-3",
                "row_state": "review_required",
                "review_reason": "업태 공백·관리자 확인",
                "raw_hygiene_type": None,
                "service_category": "미분류",
                "status_bucket": "closed",
                "raw_record": {"업태구분명": ""},
            },
        }
        resolved = _apply_review_decision(
            target,
            "include_unclassified_history",
            note="폐업 역사 원장 보존",
        )
        self.assertEqual(target["payload"]["row_state"], "review_required")
        self.assertEqual(resolved["payload"]["row_state"], "validated")
        self.assertIsNone(resolved["payload"]["review_reason"])
        self.assertEqual(
            resolved["payload"]["original_review_reason"],
            "업태 공백·관리자 확인",
        )
        self.assertEqual(
            resolved["payload"]["review_resolution"]["decision"],
            "include_unclassified_history",
        )

    def test_review_exclude_omits_target_from_new_manifest(self):
        target = {
            "payload": {
                "permit_number": "P-4",
                "row_state": "review_required",
            }
        }
        self.assertIsNone(_apply_review_decision(target, "exclude"))

    def test_review_decision_rejects_non_review_target(self):
        target = {
            "payload": {
                "permit_number": "P-5",
                "row_state": "validated",
            }
        }
        with self.assertRaisesRegex(ValueError, "이미 해결"):
            _apply_review_decision(target, "exclude")

    def test_unclassified_history_include_rejects_other_review_reasons(self):
        target = {
            "payload": {
                "permit_number": "P-6",
                "row_state": "review_required",
                "raw_hygiene_type": None,
                "service_category": "미분류",
                "status_bucket": "active",
            }
        }
        with self.assertRaisesRegex(ValueError, "폐업 원장"):
            _apply_review_decision(target, "include_unclassified_history")


if __name__ == "__main__":
    unittest.main()