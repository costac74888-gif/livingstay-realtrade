import unittest
from datetime import datetime
from decimal import Decimal

import import_airbnb_lodging as importer


def _active_row(**overrides):
    row = {
        "개방자치단체코드": 3000000,
        "관리번호": "CDFI2262212025000001",
        "인허가일자": datetime(2025, 1, 2),
        "영업상태명": "영업/정상",
        "사업장명": "테스트 스테이",
        "객실수": 2,
        "건물용도명": "단독주택",
        "데이터갱신시점": datetime(2026, 8, 30, 12, 34, 56),
        "도로명주소": "서울특별시 종로구 동망산길 68-3, 2층 (숭인동)",
        "상세영업상태명": None,
        "시설규모": "49.66",
        "전화번호": "02-1234-5678",
        "지번주소": "서울특별시 종로구 숭인동 123-4",
        "지역구분명": "일반주거지역",
    }
    row.update(overrides)
    return row


class AirbnbImportParsingTests(unittest.TestCase):
    def test_active_row_uses_authority_and_management_number_as_stable_key(self):
        parsed = importer.parse_row(_active_row())

        self.assertEqual(
            parsed["permit_number"],
            "AIRBNB:3000000:CDFI2262212025000001",
        )
        self.assertEqual(parsed["hygiene_type"], "외국인관광도시민박업")
        self.assertEqual(parsed["room_count"], 2)
        self.assertEqual(parsed["facility_area"], Decimal("49.66"))
        self.assertEqual(parsed["phone"], "0212345678")
        self.assertEqual(parsed["permit_date"], "2025-01-02 00:00:00")

    def test_same_management_number_in_different_authorities_does_not_collide(self):
        first = importer.parse_row(_active_row(개방자치단체코드=3000000))
        second = importer.parse_row(_active_row(개방자치단체코드=3010000))

        self.assertNotEqual(first["permit_number"], second["permit_number"])

    def test_integral_numeric_identity_is_stable_across_xlsx_cell_types(self):
        integer_key = importer._permit_number(3000000, 12345)
        float_key = importer._permit_number(3000000.0, 12345.0)

        self.assertEqual(integer_key, float_key)
        self.assertEqual(integer_key, "AIRBNB:3000000:12345")

    def test_fractional_numeric_identity_is_rejected(self):
        self.assertIsNone(importer._permit_number(3000000, 12345.5))

    def test_csv_integral_numeric_text_matches_xlsx_numeric_identity(self):
        self.assertEqual(
            importer._permit_number("3000000.0", "12345.0"),
            importer._permit_number(3000000, 12345),
        )

    def test_non_active_rows_are_preserved_for_status_refresh(self):
        parsed = importer.parse_row(_active_row(영업상태명="폐업"))

        self.assertEqual(parsed["biz_status_name"], "폐업")

    def test_column_values_are_read_by_header_not_numeric_position(self):
        parsed = importer.parse_row(
            _active_row(
                전화번호="010-9876-5432",
                지번주소="서울특별시 종로구 숭인동 55-6",
            )
        )

        self.assertEqual(parsed["phone"], "01098765432")
        self.assertIn("숭인동55-6", parsed["jibun_norm"])


class AirbnbMasterMatchingTests(unittest.TestCase):
    def test_road_match_has_priority_over_jibun_match(self):
        data = {"road_norm": "road", "jibun_norm": "jibun"}

        building_id, reason = importer._match_master(
            data,
            {"road": 10},
            {"jibun": 20},
        )

        self.assertEqual(building_id, 10)
        self.assertEqual(reason, "road")

    def test_ambiguous_road_match_is_not_replaced_by_jibun_match(self):
        data = {"road_norm": "road", "jibun_norm": "jibun"}

        building_id, reason = importer._match_master(
            data,
            {"road": importer._AMBIGUOUS},
            {"jibun": 20},
        )

        self.assertIsNone(building_id)
        self.assertIn("여러 건물", reason)

    def test_unparseable_address_has_no_matching_key(self):
        parsed = importer.parse_row(
            _active_row(
                도로명주소="서울특별시 종로구",
                지번주소=None,
            )
        )

        self.assertIsNone(parsed["road_norm"])
        self.assertIsNone(parsed["jibun_norm"])


class _CaptureCursor:
    def __init__(self):
        self.sql = None
        self.params = None

    def execute(self, sql, params):
        self.sql = sql
        self.params = params

    def fetchone(self):
        return {"id": 1, "is_new": False}


class AirbnbUpsertTests(unittest.TestCase):
    def test_reimport_clears_old_building_association_before_rematching(self):
        cursor = _CaptureCursor()
        data = importer.parse_row(_active_row())

        importer._upsert_registry(cursor, data)

        self.assertIn("applied_building_id = NULL", cursor.sql)

    def test_importer_does_not_initialize_schema_on_its_own(self):
        self.assertFalse(hasattr(importer, "init_db"))


if __name__ == "__main__":
    unittest.main()