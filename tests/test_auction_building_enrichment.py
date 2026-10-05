"""On-demand lookup tests: no real API, mail/SMS, or production writes."""
import json
import unittest
from unittest.mock import Mock, patch
from xml.etree import ElementTree as ET

import auction_building_enrichment as lookup
import building_registry
from address_utils import BjdongMap


class LookupRulesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.codes = BjdongMap("법정동코드_전체자료.zip")

    def setUp(self):
        self.item = {"id": 987, "master_building_id": None,
                     "address_jibun": "인천광역시 서구 석남동 511-16",
                     "address_road": None,
                     "title": "인천광역시 서구 석남동 511-16 해경스테이1차 B동 407호"}
        self.identity = lookup.parcel_identity(self.item, self.codes)
        self.title = {"mgmBldrgstPk": "test-register-pk",
                      "platPlc": self.item["address_jibun"], "newPlatPlc": "",
                      "dongNm": "B동", "mainPurpsCdNm": "숙박시설",
                      "etcPurps": "생활숙박시설", "bldNm": "해경스테이1차",
                      "hoCnt": "50", "totArea": "1200", "platArea": "100",
                      "grndFlrCnt": "10", "ugrndFlrCnt": "0", "useAprDay": "20210102"}

    def test_exact_parcel_and_region_alias(self):
        self.assertIsNotNone(self.identity)
        self.assertEqual(self.identity["jibun"], "511-16")
        alias = {**self.item, "address_jibun": "인천 서구 석남동 511-16"}
        self.assertEqual(lookup.parcel_identity(alias, self.codes), self.identity)

    def test_retired_district_uses_unique_current_official_dong_first(self):
        identities = lookup.query_identities(self.identity, self.codes)
        self.assertEqual(identities[0]["sgg_text"], "인천광역시 서해구")
        self.assertEqual(identities[0]["sgg_cd"], "28275")
        self.assertEqual(identities[-1], self.identity)
        title = {**self.title, "platPlc": "인천광역시 서해구 석남동 511-16번지",
                 "newPlatPlc": "인천광역시 서해구 칠천왕로 14 (석남동)",
                 "dongNm": "", "bldNm": "해경스테이 1차 - B동"}
        item = {**self.item, "address_road": "인천 서구 칠천왕로 14"}
        self.assertEqual(lookup.select_title(item, identities[0], [title]), title)
        self.assertIsNone(lookup.select_title({**item,"title":item["title"].replace("B동","A동")},
                                            identities[0], [title]))

    def test_multi_parcel_conflicts_and_incomplete_address_do_not_call_api(self):
        for change in (
            {"address_jibun": self.item["address_jibun"] + " 외 2필지"},
            {"title": "인천광역시 서구 석남동 111-2 생활숙박시설"},
            {"address_jibun": None, "title": "해경스테이 B동 407호"},
        ):
            self.assertIsNone(lookup.parcel_identity({**self.item, **change}, self.codes))

    def test_rural_parcel_keeps_eup_myeon_and_ri(self):
        identity = lookup.parcel_identity(
            {"address_jibun": "경기도 가평군 청평면 청평리 123-4"}, self.codes)
        self.assertIsNotNone(identity)
        self.assertEqual(identity["umd_nm"], "청평면청평리")

    def test_title_is_selected_by_official_address_and_explicit_dong(self):
        a = {**self.title, "mgmBldrgstPk": "a", "dongNm": "A동"}
        self.assertEqual(lookup.select_title(self.item, self.identity, [a, self.title]), self.title)
        unnamed = {**self.item, "title": self.item["address_jibun"] + " 생활숙박시설"}
        self.assertIsNone(lookup.select_title(unnamed, self.identity, [a, self.title]))
        self.assertIsNone(lookup.select_title(self.item, self.identity, [
            {**self.title, "platPlc": "인천광역시 서구 석남동 999-9"}]))

    def test_road_conflict_missing_pk_and_duplicate_pk(self):
        item = {**self.item, "address_road": "인천광역시 서구 석남로 1"}
        self.assertIsNone(lookup.select_title(item, self.identity, [
            {**self.title, "newPlatPlc": "인천광역시 서구 석남로 2"}]))
        self.assertIsNone(lookup.select_title(self.item, self.identity, [
            {**self.title, "mgmBldrgstPk": ""}]))
        self.assertEqual(lookup.select_title(self.item, self.identity,
                                            [self.title, self.title]), self.title)

    def test_provider_error_header_is_not_treated_as_empty(self):
        response = Mock(content=b"<response><header><resultCode>22</resultCode>"
                        b"<resultMsg>quota</resultMsg></header></response>")
        with patch.object(building_registry, "_get_with_retry", return_value=response):
            with self.assertRaises(RuntimeError):
                building_registry._fetch_title_rows("28260", "11100", "0", "511", "16",
                                                   max_pages=3)

    def test_partial_pages_cannot_choose_a_false_unique_candidate(self):
        response = Mock(content=b"<response><totalCount>101</totalCount><items>"
                        b"<item><mgmBldrgstPk>x</mgmBldrgstPk></item></items></response>")
        with patch.object(building_registry, "_get_with_retry", return_value=response) as fetch:
            with self.assertRaises(RuntimeError):
                building_registry._fetch_title_rows("28260", "11100", "0", "511", "16",
                                                   max_pages=1)
            self.assertEqual(fetch.call_count, 1)

    def test_persist_rechecks_source_before_writing(self):
        cur = Mock()
        cur.fetchone.return_value = {**self.item, "address_jibun": "changed"}
        self.assertIsNone(lookup.persist_title(cur, self.item, self.identity, self.title))
        self.assertEqual(cur.execute.call_count, 1)

    def test_new_title_stores_register_facts_not_auction_unit_area(self):
        cur = Mock()
        cur.fetchone.side_effect = [self.item, {"id": 112}]
        cur.fetchall.return_value = []
        cur.rowcount = 1
        self.assertEqual(lookup.persist_title(cur, {**self.item, "area_m2": 26.12},
                                              self.identity, self.title), 112)
        inserts = [call for call in cur.execute.call_args_list
                   if call.args[0].startswith("INSERT INTO master_buildings")]
        self.assertEqual(len(inserts), 1)
        self.assertIn(1200.0, inserts[0].args[1])
        self.assertNotIn(26.12, inserts[0].args[1])
        self.assertIn("생활", inserts[0].args[1])
        self.assertNotIn("operating_records", inserts[0].args[0])
        self.assertNotIn("detail_fetched_at", inserts[0].args[0])

    def test_outdated_runner_never_calls_provider(self):
        conn = Mock()
        conn.__enter__ = Mock(return_value=conn)
        conn.__exit__ = Mock(return_value=False)
        cur = Mock()
        cur.__enter__ = Mock(return_value=cur)
        cur.__exit__ = Mock(return_value=False)
        conn.cursor.return_value = cur
        cur.fetchone.return_value = {"value": json.dumps({"run_id": "newer"})}
        with patch.object(lookup, "get_conn", return_value=conn), \
                patch.object(building_registry, "_fetch_title_rows") as fetch:
            lookup.run_lookup(self.item["id"], "old")
            fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
