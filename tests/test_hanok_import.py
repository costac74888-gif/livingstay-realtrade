import unittest

import import_hanok_lodging as importer


def _row(**overrides):
    row = {
        "개방자치단체코드": "3000000",
        "관리번호": "CDFI-1",
        "인허가일자": "2025-08-07",
        "영업상태명": "영업/정상",
        "사업장명": "한옥스테이",
        "객실수": "4",
        "건물용도명": "단독주택",
        "데이터갱신시점": "2026-05-11 22:39:57",
        "도로명주소": "서울특별시 종로구 자하문로5가길 36 (체부동)",
        "상세영업상태명": "영업중",
        "시설규모": "56.2",
        "전화번호": "02-1234-5678",
        "지번주소": "서울특별시 종로구 체부동 12-3",
        "지역구분명": "일반주거지역",
    }
    row.update(overrides)
    return row


class HanokImportTests(unittest.TestCase):
    def test_parse_row_uses_hanok_identity_and_type(self):
        parsed = importer.parse_row(_row())
        self.assertEqual(parsed["permit_number"], "HANOK:3000000:CDFI-1")
        self.assertEqual(parsed["hygiene_type"], "한옥체험업")
        self.assertEqual(parsed["lodging_type"], "한옥")
        self.assertEqual(parsed["room_count"], 4)
        self.assertEqual(parsed["phone"], "0212345678")

    def test_inactive_rows_are_preserved(self):
        parsed = importer.parse_row(_row(영업상태명="폐업"))
        self.assertEqual(parsed["biz_status_name"], "폐업")

    def test_missing_identity_is_skipped(self):
        self.assertIsNone(importer.parse_row(_row(관리번호="")))


if __name__ == "__main__":
    unittest.main()