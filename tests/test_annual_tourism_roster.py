"""Focused contracts for the isolated approved annual roster module."""
import io
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

from openpyxl import Workbook

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import annual_tourism_roster as roster


def workbook_bytes(headers, row):
    book = Workbook()
    sheet = book.active
    sheet.append(headers)
    sheet.append(row)
    output = io.BytesIO()
    book.save(output)
    return output.getvalue()


class AnnualTourismRosterTests(unittest.TestCase):
    def test_parses_official_style_columns_and_normalizes_short_year(self):
        raw = workbook_bytes(
            ["번호", "지역1\n(시도)", "지역2\n(시군구)", "업종", "시설개요", "주소", "객실수(실)", "영업상태"],
            [1, "서울", "중구", "관광호텔업", "테스트 호텔", "서울 중구", "1,234", "영업중"],
        )
        year, rows, headers = roster.parse_xlsx("25년_말_기준_관광숙박업.xlsx", raw)
        self.assertEqual(year, 2025)
        self.assertEqual(rows[0]["subtype"], "관광호텔업")
        self.assertEqual(rows[0]["room_count"], 1234)
        self.assertEqual(headers[3], "업종")

    def test_rejects_wrong_extension_and_missing_required_columns(self):
        with self.assertRaises(ValueError):
            roster.parse_xlsx("roster.csv", b"x")
        raw = workbook_bytes(["업종", "시설개요", "영업상태"], ["관광호텔업", "A", "영업중"])
        with self.assertRaisesRegex(ValueError, "객실수"):
            roster.parse_xlsx("2025년_관광숙박업.xlsx", raw)

    def test_uploaded_official_fixture_active_totals(self):
        fixture = os.path.join(
            os.path.dirname(__file__), "..", "attached_assets",
            "25년_말_기준_관광숙박업(호텔,_휴양콘도)_등록현황(최종)공개용_1788693043516.xlsx",
        )
        with open(fixture, "rb") as source:
            year, rows, _ = roster.parse_xlsx(os.path.basename(fixture), source.read())
        self.assertEqual(year, 2025)
        self.assertEqual(len(rows), 2996)
        active = [row for row in rows if row["is_active"]]
        self.assertEqual(len(active), 2929)
        self.assertEqual(sum(row["room_count"] for row in active), 219621)

    def test_production_guard_rejects_non_production_database(self):
        target, production = MagicMock(), MagicMock()
        target.cursor.return_value.fetchone.return_value = ("dev", "host", 1)
        production.cursor.return_value.fetchone.return_value = ("prod", "host", 1)
        with patch.dict(os.environ, {"PROD_DATABASE_URL": "postgres://prod"}, clear=False), \
             patch("annual_tourism_roster.psycopg2.connect", return_value=production):
            with self.assertRaisesRegex(RuntimeError, "운영 서버"):
                roster.assert_production_connection(target)
        production.close.assert_called_once()

    def test_breakdown_keeps_only_permit_and_room_aggregates(self):
        result = roster._breakdown([
            {"subtype": "관광호텔업", "room_count": 2},
            {"subtype": "관광호텔업", "room_count": 3},
            {"subtype": "호스텔업", "room_count": 1},
        ])
        self.assertEqual(result, [
            {"subtype": "관광호텔업", "permit_count": 2, "room_count": 5},
            {"subtype": "호스텔업", "permit_count": 1, "room_count": 1},
        ])

    def test_legal_water_and_medical_tourism_subtypes_are_preserved(self):
        self.assertEqual(roster._subtype("수상관광호텔업"), "수상관광호텔업")
        self.assertEqual(roster._subtype("의료관광호텔업"), "의료관광호텔업")


if __name__ == "__main__":
    unittest.main()