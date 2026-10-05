import unittest

from auction_building_matching import build_indexes, choose_building, resolve_building
from unittest.mock import patch, Mock


class AuctionBuildingMatchingTest(unittest.TestCase):
    def setUp(self):
        self.first = {
            "id": 1, "road_address": "부산광역시 해운대구 해운대해변로298번길 25",
            "jibun_address": "부산광역시 해운대구 중동 1124-8",
            "lat": 35.16, "lng": 129.16,
        }
        self.second = {
            "id": 2, "road_address": self.first["road_address"] + " (중동)",
            "jibun_address": None, "sgg_text": "부산광역시 해운대구",
            "umd_nm": "중동", "jibun": "1126-45",
        }
        self.item = {
            "address_road": self.first["road_address"] + " (중동, 호텔)",
            "address_jibun": self.first["jibun_address"] + " 호텔 101호",
        }
        self.index = build_indexes([self.first, self.second])

    def choose(self, item, index=None):
        return choose_building(item, *(index or self.index)[:2])

    def test_multiple_road_candidates_disambiguated_by_parcel(self):
        self.assertEqual(self.choose(self.item)["id"], 1)

    def test_unique_jibun_with_no_road_and_region_alias(self):
        self.assertEqual(self.choose({**self.item, "address_road": "",
                                     "address_jibun": "부산 해운대구 중동 1124-8"})["id"], 1)

    def test_structured_jibun_is_used_without_jibun_address(self):
        self.assertEqual(self.choose({**self.item,
            "address_jibun": "부산광역시 해운대구 중동 1126-45"})["id"], 2)

    def test_ambiguous_road_without_parcel_stays_unmatched(self):
        self.assertIsNone(self.choose({**self.item, "address_jibun": ""}))

    def test_missing_address_fields_use_exact_official_title_address_only(self):
        self.assertEqual(self.choose({"title":
            self.first["jibun_address"] + " 해운대호텔 숙박시설 101호"})["id"], 1)
        self.assertIsNone(self.choose({"title": "해운대호텔 숙박시설"}))
        self.assertIsNone(self.choose({"title":
            self.first["jibun_address"] + " 외 2필지 숙박시설"}))

    def test_conflicting_road_and_parcel_are_not_guessed(self):
        third = {**self.first, "id": 3, "road_address": "부산광역시 해운대구 다른길 9"}
        self.assertIsNone(self.choose({**self.item, "address_jibun":
            "부산광역시 해운대구 중동 1124-8"}, build_indexes([self.second, third])))

    def test_duplicate_parcel_not_arbitrarily_selected(self):
        self.assertIsNone(self.choose(self.item, build_indexes([
            self.first, {**self.first, "id": 3}])))

    def test_multi_parcel_and_unknown_addresses_stay_unmatched(self):
        for address in ("부산광역시 해운대구 중동 1124-8 외 2필지",
                        "부산광역시 해운대구 중동 1124-8, 1126-45"):
            self.assertIsNone(self.choose({**self.item, "address_jibun": address}))
        self.assertIsNone(self.choose({"address_road": "", "address_jibun": ""}))

    def test_existing_id_preserved_and_deleted_id_resolved_without_db_write(self):
        cursor = Mock()
        cursor.fetchone.return_value = None
        with patch("auction_building_matching.get_indexes", return_value=self.index):
            existing = {**self.item, "master_building_id": 2}
            self.assertEqual(resolve_building(cursor, existing)["id"], 2)
            deleted = {**self.item, "master_building_id": 999}
            self.assertEqual(resolve_building(cursor, deleted)["id"], 1)
            self.assertEqual(deleted["master_building_id"], 1)
            self.assertEqual(deleted["lat"], self.first["lat"])
        cursor.execute.assert_called_once()
        self.assertIn("WHERE id=%s", cursor.execute.call_args[0][0])

    def test_newly_saved_building_bypasses_stale_worker_index(self):
        cursor = Mock()
        new = {**self.first, "id": 999}
        cursor.fetchone.return_value = new
        with patch("auction_building_matching.get_indexes", return_value=self.index):
            item = {**self.item, "master_building_id": 999}
            self.assertEqual(resolve_building(cursor, item)["id"], 999)
        cursor.execute.assert_called_once()


if __name__ == "__main__":
    unittest.main()