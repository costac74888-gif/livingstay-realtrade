import unittest
from datetime import datetime

import import_camping_lodging as importer


def _camping_row(**overrides):
    row = {
        "개방자치단체코드": 3030000,
        "관리번호": "CDFI2262132015000001",
        "인허가일자": datetime(2015, 6, 30),
        "영업상태명": "영업/정상",
        "사업장명": "테스트 캠핑장",
        "객실수": None,
        "건물용도명": None,
        "데이터갱신시점": datetime(2026, 8, 30, 12, 34, 56),
        "도로명주소": "서울특별시 성동구 뚝섬로 273 (성수동1가)",
        "상세영업상태명": "영업중",
        "시설규모": 2000,
        "전화번호": "02-1234-5678",
        "지번주소": "서울특별시 성동구 성수동1가 643",
        "지역구분명": "자연녹지지역",
    }
    row.update(overrides)
    return row


class CampingImportTests(unittest.TestCase):
    def test_uses_camping_source_key_and_legal_type(self):
        parsed = importer.parse_row(_camping_row())

        self.assertEqual(
            parsed["permit_number"],
            "CAMPING:3030000:CDFI2262132015000001",
        )
        self.assertEqual(parsed["hygiene_type"], "일반야영장업")
        self.assertEqual(parsed["lodging_type"], "캠핑")
        self.assertEqual(parsed["master_source"], "camping_import")

    def test_same_management_number_in_different_authorities_does_not_collide(self):
        first = importer.parse_row(_camping_row(개방자치단체코드=3030000))
        second = importer.parse_row(_camping_row(개방자치단체코드=3040000))

        self.assertNotEqual(first["permit_number"], second["permit_number"])

    def test_camping_room_count_is_not_used_as_lodging_room_count(self):
        parsed = importer.parse_row(_camping_row(객실수=12))

        self.assertIsNone(parsed["room_count"])

    def test_non_active_rows_are_preserved_for_status_refresh(self):
        parsed = importer.parse_row(_camping_row(영업상태명="폐업"))

        self.assertEqual(parsed["biz_status_name"], "폐업")

    def test_real_xlsx_is_read_by_shared_header_parser(self):
        rows = importer.common.read_rows(
            "attached_assets/문화_일반야영장업1_1788079511098.xlsx"
        )

        self.assertEqual(len(rows), 4901)
        self.assertEqual(rows[0]["문화체육업종명"], "일반야영장업")


if __name__ == "__main__":
    unittest.main()