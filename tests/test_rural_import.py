import unittest

import import_rural_lodging as importer


def _row(**overrides):
    row = {
        "개방자치단체코드": "3330000",
        "관리번호": "AGCV-1",
        "인허가일자": "2019-09-06",
        "영업상태명": "영업/정상",
        "사업장명": "산골민박",
        "객실수": "4",
        "건물형태구분명": "",
        "데이터갱신시점": "2026-05-11 22:39:57",
        "도로명주소": "강원특별자치도 평창군 봉평면 태기로 1",
        "상세영업상태명": "정상",
        "소재지면적": "494",
        "주택면적": "120.5",
        "전화번호": "033-123-4567",
        "지번주소": "강원특별자치도 평창군 봉평면 무이리 1",
    }
    row.update(overrides)
    return row


class RuralImportTests(unittest.TestCase):
    def test_parse_row_uses_rural_identity_and_type(self):
        parsed = importer.parse_row(_row())
        self.assertEqual(parsed["permit_number"], "RURAL:3330000:AGCV-1")
        self.assertEqual(parsed["hygiene_type"], "농어촌민박업")
        self.assertEqual(parsed["lodging_type"], "농어촌민박")
        self.assertEqual(parsed["room_count"], 4)
        self.assertEqual(parsed["facility_area"], 120.5)

    def test_inactive_rows_are_preserved(self):
        parsed = importer.parse_row(_row(영업상태명="폐업"))
        self.assertEqual(parsed["biz_status_name"], "폐업")

    def test_missing_identity_is_skipped(self):
        self.assertIsNone(importer.parse_row(_row(관리번호="")))


if __name__ == "__main__":
    unittest.main()