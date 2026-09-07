import os
import tempfile
import unittest
import zipfile

from openpyxl import Workbook

from import_hotel_operation import (
    EXPECTED_SIDOS,
    _decoded_member_name,
    parse_operation_zip,
    validate_operation_records,
)


class HotelOperationImportTests(unittest.TestCase):
    @staticmethod
    def complete_records():
        return [
            (f"root/{sido}/지역 원데이터.xlsx", 2, sido, "테스트시", "전체")
            for sido in EXPECTED_SIDOS
        ]

    def test_parser_preserves_sgg_overall_and_grade_rows(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Sheet1"
        sheet.append([" 구   분"] + [""] * 15 + ["등급", "시도cd"])
        sheet.append(["강원 / 전체"] + [None] * 7 + [56.94, 166983, 95080, 3.3, 100, 57, 20, 2, "전체", 900])
        sheet.append(["강릉시"] + [None] * 7 + [62.23, 208511, 129756, 3.94, 100, 62, 20, 2, "전체", 901])
        sheet.append(["         5성"] + [None] * 7 + [81.26, 417190, 339009, 0, 50, 40, 10, 1, "5성", 901])
        handle, xlsx_path = tempfile.mkstemp(suffix=".xlsx")
        os.close(handle)
        workbook.save(xlsx_path)
        handle, zip_path = tempfile.mkstemp(suffix=".zip")
        os.close(handle)
        try:
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.write(
                    xlsx_path,
                    "root/강원특별자치도/2024년 호텔업 운영현황 강원지역 원데이터.xlsx",
                )
            digest, rows = parse_operation_zip(zip_path)
            self.assertEqual(64, len(digest))
            self.assertEqual([None, "강릉시", "강릉시"], [row[3] for row in rows])
            self.assertEqual(["전체", "전체", "5성"], [row[4] for row in rows])
            self.assertEqual((62.23, 208511.0, 129756.0), rows[1][5:8])
            with self.assertRaisesRegex(ValueError, "완전하지 않습니다"):
                validate_operation_records(rows)
        finally:
            os.unlink(xlsx_path)
            os.unlink(zip_path)

    def test_complete_validation_requires_exact_official_sido_set(self):
        records = self.complete_records()
        validate_operation_records(records)
        fake = [row for row in records if row[2] != "서울"]
        fake.append(("root/가짜도/지역 원데이터.xlsx", 2, "가짜", "가짜시", "전체"))
        with self.assertRaisesRegex(ValueError, "누락 \\['서울'\\].*예상 외 \\['가짜'\\]"):
            validate_operation_records(fake)

    def test_legacy_korean_zip_member_name_is_restored(self):
        original = "경기도/2024년 호텔업 운영현황 경기지역 원데이터.xlsx"
        mojibake = original.encode("euc-kr").decode("cp437")
        self.assertEqual(original, _decoded_member_name(mojibake))

    def test_uploaded_2024_archive_is_automatically_unpacked(self):
        path = (
            "attached_assets/"
            "2024_호텔업_운영현황(지역별,성급별_데이터)_1788789695472.zip"
        )
        if not os.path.isfile(path):
            self.skipTest("첨부 운영현황 ZIP이 없습니다.")
        _, rows = parse_operation_zip(path)
        validate_operation_records(rows)
        self.assertEqual(EXPECTED_SIDOS, {row[2] for row in rows})
        self.assertGreaterEqual(
            len([row for row in rows if row[3] and row[4] == "전체"]),
            100,
        )


if __name__ == "__main__":
    unittest.main()