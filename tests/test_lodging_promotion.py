import unittest

from lodging_promotion import _build_targets


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


if __name__ == "__main__":
    unittest.main()