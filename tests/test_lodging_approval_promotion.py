import unittest

from validate_lodging_approval_promotion import (
    classify_registry_action,
    parse_optional_room_count,
)


class LodgingApprovalPromotionTest(unittest.TestCase):
    def test_blank_room_count_is_preserved(self):
        self.assertIsNone(parse_optional_room_count({"객실수": ""}))
        self.assertIsNone(parse_optional_room_count({}))
        self.assertEqual(parse_optional_room_count({"객실수": "1,234"}), 1234)

    def test_existing_status_change_takes_priority(self):
        payload = {
            "biz_name": "숙소",
            "raw_status": "폐업",
            "road_address": "도로 1",
            "jibun_address": "지번 1",
            "raw_hygiene_type": "숙박업(생활)",
            "raw_record": {"객실수": ""},
        }
        existing = {
            "biz_name": "숙소",
            "biz_status_name": "영업/정상",
            "road_address": "도로 1",
            "jibun_address": "지번 1",
            "hygiene_type": "숙박업(생활)",
            "room_count": 20,
        }
        self.assertEqual(
            classify_registry_action(payload, existing),
            "status_change",
        )

    def test_unchanged_existing_row_stays_unchanged_when_room_is_blank(self):
        payload = {
            "biz_name": "숙소",
            "raw_status": "영업/정상",
            "road_address": "도로 1",
            "jibun_address": "지번 1",
            "raw_hygiene_type": "숙박업(생활)",
            "raw_record": {"객실수": ""},
        }
        existing = {
            "biz_name": "숙소",
            "biz_status_name": "영업/정상",
            "road_address": "도로 1",
            "jibun_address": "지번 1",
            "hygiene_type": "숙박업(생활)",
            "room_count": 20,
        }
        self.assertEqual(classify_registry_action(payload, existing), "unchanged")

    def test_new_row_is_insert(self):
        self.assertEqual(classify_registry_action({}, None), "insert")


if __name__ == "__main__":
    unittest.main()