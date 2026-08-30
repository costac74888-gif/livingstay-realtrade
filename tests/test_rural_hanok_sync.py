import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import import_airbnb_lodging as common
import sync_rural_hanok as syncer


def _item(**overrides):
    item = {
        "OPN_ATMY_GRP_CD": "5000000",
        "MNG_NO": "RURAL-1",
        "BPLC_NM": "공식 민박",
        "GSRM_CNT": "2",
        "SALS_STTS_NM": "영업/정상",
        "DTL_SALS_STTS_NM": "정상",
        "ROAD_NM_ADDR": "제주특별자치도 제주시 애월읍 애월로 1",
        "LOTNO_ADDR": "제주특별자치도 제주시 애월읍 애월리 1",
        "LCPMT_YMD": "20260101",
        "DAT_UPDT_PNT": "20260830120000",
        "TELNO": "064-123-4567",
        "HSAR": "85.2",
        "BLDG_SHP_SE_NM": "단독주택",
        "USG_RGN": "계획관리지역",
    }
    item.update(overrides)
    return item


class RuralHanokParsingTests(unittest.TestCase):
    def test_rural_item_maps_to_distinct_official_type(self):
        parsed = syncer.parse_item(_item(), syncer.SOURCES["rural"])
        self.assertEqual(parsed["permit_number"], "RURAL:5000000:RURAL-1")
        self.assertEqual(parsed["hygiene_type"], "농어촌민박업")
        self.assertEqual(parsed["lodging_type"], "농어촌민박")
        self.assertEqual(parsed["room_count"], 2)
        self.assertEqual(parsed["phone"], "0641234567")

    def test_hanok_item_maps_to_distinct_key_and_type(self):
        parsed = syncer.parse_item(
            _item(
                MNG_NO="HANOK-1",
                CULTR_SPTS_TPBIZ_NM="한옥체험업",
                BLDG_USG_NM="단독주택",
                FCLT_SCL="120.5",
            ),
            syncer.SOURCES["hanok"],
        )
        self.assertEqual(parsed["permit_number"], "HANOK:5000000:HANOK-1")
        self.assertEqual(parsed["hygiene_type"], "한옥체험업")
        self.assertEqual(parsed["lodging_type"], "한옥")

    def test_inactive_status_is_preserved(self):
        parsed = syncer.parse_item(
            _item(SALS_STTS_NM="폐업", DTL_SALS_STTS_NM="폐업처리"),
            syncer.SOURCES["rural"],
        )
        self.assertEqual(parsed["biz_status_name"], "폐업")

    def test_authority_code_prevents_management_number_collision(self):
        config = syncer.SOURCES["rural"]
        first = syncer._permit_number(config, "5000000", "1")
        second = syncer._permit_number(config, "5010000", "1")
        self.assertNotEqual(first, second)

    def test_ambiguous_road_never_falls_back_to_jibun(self):
        parsed = syncer.parse_item(_item(), syncer.SOURCES["rural"])
        building_id, reason = common._match_master(
            parsed,
            {parsed["road_norm"]: common._AMBIGUOUS},
            {parsed["jibun_norm"]: 7},
        )
        self.assertIsNone(building_id)
        self.assertIn("도로명", reason)

    def test_empty_middle_page_is_not_treated_as_completion(self):
        with self.assertRaisesRegex(RuntimeError, "중간 빈 페이지"):
            syncer._page_is_complete(100, 0, 300)

    def test_exact_total_is_required_for_completion(self):
        self.assertFalse(syncer._page_is_complete(0, 100, 250))
        self.assertTrue(syncer._page_is_complete(200, 50, 250))
        with self.assertRaisesRegex(RuntimeError, "총건수보다 많"):
            syncer._page_is_complete(200, 51, 250)


class RuralHanokClassificationTests(unittest.TestCase):
    def _row(self, **overrides):
        row = {
            "lodging_type": "미분류",
            "lodging_type_detail": None,
            "source": "legacy",
            "lodging_classification_source": None,
            "hygiene_types": ["농어촌민박업"],
        }
        row.update(overrides)
        return row

    def test_active_rural_permit_reclassifies_unprotected_building(self):
        self.assertEqual(
            syncer._classification_action(self._row()),
            ("update", "농어촌민박"),
        )

    def test_rural_and_hanok_at_same_building_become_mixed(self):
        action, target = syncer._classification_action(
            self._row(hygiene_types=["농어촌민박업", "한옥체험업"])
        )
        self.assertEqual((action, target), ("update", "복합"))

    def test_specific_existing_type_is_protected_from_generic_permit(self):
        action, target = syncer._classification_action(
            self._row(
                lodging_type="한옥",
                hygiene_types=["일반호텔"],
            )
        )
        self.assertEqual((action, target), ("protected", "일반"))

    def test_last_inactive_permit_clears_only_active_permit_classification(self):
        action, target = syncer._classification_action(
            self._row(
                lodging_type="농어촌민박",
                lodging_classification_source="active_permit",
                hygiene_types=[],
            )
        )
        self.assertEqual((action, target), ("clear", "미분류"))

    def test_no_active_permit_preserves_non_permit_classification(self):
        action, target = syncer._classification_action(
            self._row(
                lodging_type="일반",
                lodging_classification_source="building_registry",
                hygiene_types=[],
            )
        )
        self.assertEqual((action, target), ("keep", None))

    def test_partial_run_preserves_unaffected_conflict_reviews(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "conflicts.json"
            report.write_text(
                json.dumps([
                    {"building_id": 1, "reason": "protected_classification"},
                    {"building_id": 2, "reason": "protected_classification"},
                ]),
                encoding="utf-8",
            )
            with patch.object(syncer, "REPORT_PATH", report):
                syncer._write_conflict_report(
                    [{"building_id": 2, "reason": "protected_classification"}],
                    {2, 3},
                )
            saved = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual([item["building_id"] for item in saved], [1, 2])


if __name__ == "__main__":
    unittest.main()