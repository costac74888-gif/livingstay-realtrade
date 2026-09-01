import unittest

import sync_rural_hanok_trades as syncer


def _master(**overrides):
    row = {
        "id": 1,
        "building_name": "표본 한옥",
        "sgg_cd": "11110",
        "umd_nm": "청운동",
        "jibun": "12-3",
        "lodging_type": "한옥",
        "lodging_type_detail": "한옥체험업",
        "building_use_type": "주택",
        "building_use_detail": "단독주택(한옥)",
    }
    row.update(overrides)
    return row


class RuralHanokTradeSyncTests(unittest.TestCase):
    def test_permit_type_selects_target_but_public_use_selects_api(self):
        self.assertEqual(syncer.target_kind(_master()), "hanok")
        self.assertEqual(syncer.source_apis_for_use(_master()), ("SHTrade",))
        self.assertEqual(
            syncer.source_apis_for_use(
                _master(building_use_detail="공동주택 연립주택")
            ),
            ("RHTrade",),
        )
        self.assertEqual(
            syncer.source_apis_for_use(
                _master(building_use_type="숙박시설", building_use_detail="숙박시설")
            ),
            ("NrgTrade",),
        )
        self.assertEqual(
            syncer.source_apis_for_use(
                _master(building_use_type="확인불가", building_use_detail=None)
            ),
            (),
        )

    def test_official_api_scope_and_area_mapping(self):
        base = {
            "umdNm": "청운동",
            "jibun": "12-3",
            "dealYear": "2026",
            "dealMonth": "8",
            "dealDay": "1",
            "dealAmount": "12,300",
        }
        detached = syncer.normalize_trade(
            "SHTrade", "11110", dict(base, totalFloorAr="81.2", plottageAr="120")
        )
        row_house = syncer.normalize_trade(
            "RHTrade", "11110", dict(base, excluUseAr="45.1", landAr="21.4")
        )
        land = syncer.normalize_trade(
            "LandTrade", "11110", dict(base, dealArea="330")
        )
        self.assertEqual(detached["transaction_scope"], "whole_building")
        self.assertEqual(detached["area"], 81.2)
        self.assertEqual(detached["land_area"], 120.0)
        self.assertEqual(row_house["transaction_scope"], "unit")
        self.assertEqual(row_house["area"], 45.1)
        self.assertEqual(land["transaction_scope"], "land_or_site")
        self.assertEqual(land["land_area"], 330.0)

    def test_only_one_complete_compatible_master_is_linked(self):
        master = _master()
        key = ("11110", "청운동", "12-3")
        trade = syncer.normalize_trade(
            "SHTrade",
            "11110",
            {
                "umdNm": "청운동",
                "jibun": "12-3",
                "dealYear": "2026",
                "dealMonth": "8",
                "dealDay": "1",
                "dealAmount": "10000",
            },
        )
        self.assertEqual(syncer.match_trade(trade, {key: [master]}), (master, None))
        self.assertEqual(
            syncer.match_trade(trade, {key: [master, _master(id=2)]})[1],
            "ambiguous_exact_master",
        )
        self.assertEqual(
            syncer.match_trade(
                trade,
                {key: [_master(lodging_type="일반", building_name="일반숙박")]},
            )[1],
            "no_target_master",
        )
        masked = dict(trade, jibun="12-*")
        self.assertEqual(
            syncer.match_trade(masked, {key: [master]})[1],
            "masked_or_incomplete_identity",
        )
        land = dict(trade, transaction_scope="land_or_site")
        self.assertEqual(
            syncer.match_trade(land, {key: [master]})[1],
            "land_has_no_public_building_identity",
        )

    def test_source_and_scope_make_dedup_key_distinct(self):
        trade = {
            "source_api": "SHTrade",
            "transaction_scope": "whole_building",
            "sgg_cd": "11110",
            "umd_nm": "청운동",
            "jibun": "12-3",
            "deal_date": "2026-08-01",
            "price": 10000,
            "floor": "",
        }
        first = syncer.raw_key_for_trade(trade)
        second = syncer.raw_key_for_trade(dict(trade, source_api="RHTrade"))
        third = syncer.raw_key_for_trade(dict(trade, transaction_scope="unit"))
        self.assertNotEqual(first, second)
        self.assertNotEqual(first, third)
        self.assertEqual(first, syncer.raw_key_for_trade(trade))


if __name__ == "__main__":
    unittest.main()