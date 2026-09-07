import io
import os
import subprocess
import tempfile
import time
import unittest
from unittest import mock

from openpyxl import Workbook

from operation_document_parser import (
    DocumentParseError,
    merge_documents,
    parse_document,
    parse_documents_isolated,
    parse_metrics,
    release_parse_slot,
    try_acquire_parse_slot,
)


def _blocking_worker(connection, items, memory_limit_bytes, cpu_limit_seconds):
    time.sleep(10)


def _descendant_worker(connection, items, memory_limit_bytes, cpu_limit_seconds):
    marker = items[0][0].decode()
    child = subprocess.Popen(["sleep", "10"])
    with open(marker, "w", encoding="utf-8") as handle:
        handle.write(str(child.pid))
    time.sleep(10)


class OperationDocumentParserTests(unittest.TestCase):
    def test_csv_extracts_period_occ_room_revenue_sold_rooms_and_calculates_adr(self):
        raw = (
            "분석기간,2026-01-01 ~ 2026-01-31\n"
            "객실 이용률(OCC),74.5%\n"
            "객실매출,\"16,200,000원\"\n"
            "판매객실 수,100실\n"
        ).encode("utf-8")
        result = parse_document(raw, "csv")
        self.assertEqual(result["period_start"], "2026-01-01")
        self.assertEqual(result["period_end"], "2026-01-31")
        self.assertEqual(result["occ"], 74.5)
        self.assertEqual(result["room_revenue"], 16_200_000)
        self.assertEqual(result["sold_rooms"], 100)
        self.assertEqual(result["occupancy_days"], 31)
        self.assertEqual(result["adr"], 162_000)
        self.assertEqual(result["adr_source"], "calculated_from_room_revenue")

    def test_total_revenue_never_becomes_room_revenue_or_invented_adr(self):
        result = parse_metrics("기간 2026.01~2026.01 총매출 99,000,000원 OCC 80%").as_dict()
        self.assertIsNone(result["room_revenue"])
        self.assertIsNone(result["sold_rooms"])
        self.assertIsNone(result["adr"])

    def test_unquoted_thousands_separators_in_csv_are_preserved(self):
        raw = "객실매출,12,000,000원\n판매객실 수,80".encode()
        result = parse_document(raw, "csv")
        self.assertEqual(result["room_revenue"], 12_000_000)
        self.assertEqual(result["adr"], 150_000)

    def test_xlsx_extracts_explicit_adr(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["분석 기간", "2026/02/01 - 2026/02/28"])
        sheet.append(["OCC", 68.2])
        sheet.append(["ADR", 175000])
        stream = io.BytesIO()
        workbook.save(stream)
        result = parse_document(stream.getvalue(), "xlsx")
        self.assertEqual(result["occ"], 68.2)
        self.assertEqual(result["adr"], 175000)
        self.assertEqual(result["adr_source"], "explicit")
        self.assertIsNone(result["sold_rooms"])

    @mock.patch("operation_document_parser._ocr_image")
    def test_png_uses_ocr_text(self, ocr):
        from PIL import Image
        stream = io.BytesIO()
        Image.new("RGB", (20, 20), "white").save(stream, "PNG")
        ocr.return_value = "분석기간 2026-03-01~2026-03-31 OCC 77% 객실매출 20,000원 판매객실수 2"
        result = parse_document(stream.getvalue(), "png")
        self.assertEqual(result["occ"], 77)
        self.assertEqual(result["adr"], 10000)

    @mock.patch("pymupdf.open")
    def test_pdf_uses_embedded_table_text(self, fitz_open):
        page = mock.MagicMock()
        page.get_text.return_value = "기간 2026-04-01~2026-04-30 OCC 70 ADR 150000 객실매출 15000000 판매객실 수 100"
        document = mock.MagicMock()
        document.page_count = 1
        document.__iter__.return_value = [page]
        fitz_open.return_value = document
        result = parse_document(b"%PDF-1.7 sample", "pdf")
        self.assertEqual(result["period_end"], "2026-04-30")
        self.assertEqual(result["room_revenue"], 15000000)

    def test_merge_pairs_separate_sales_and_reservation_files_for_same_period(self):
        merged = merge_documents([
            parse_metrics("기간 2026-01-01~2026-01-31 객실매출 340000").as_dict(),
            parse_metrics("기간 2026-01-01~2026-01-31 판매객실 수 5").as_dict(),
        ])
        self.assertEqual(merged["room_revenue"], 340000)
        self.assertEqual(merged["sold_rooms"], 5)
        self.assertEqual(merged["adr"], 68000)
        self.assertEqual(merged["occupancy_days"], 31)

    def test_merge_rejects_duplicate_same_period_revenue_and_sold_inputs(self):
        merged = merge_documents([
            parse_metrics("기간 2026-01 객실매출 100000 판매객실 수 2").as_dict(),
            parse_metrics("기간 2026-01 객실매출 240000 판매객실 수 3").as_dict(),
        ])
        self.assertIsNone(merged["room_revenue"])
        self.assertIsNone(merged["sold_rooms"])
        self.assertIsNone(merged["adr"])

    def test_adr_label_does_not_look_like_sold_room_count(self):
        result = parse_metrics("판매객실 평균요금 ADR 180,000원").as_dict()
        self.assertEqual(result["adr"], 180000)
        self.assertIsNone(result["sold_rooms"])

    def test_header_and_rows_are_aggregated_by_columns_without_cross_capture(self):
        raw = (
            "기간,객실매출,판매객실 수,OCC\n"
            "2026-01-01~2026-01-31,16200000,100,75\n"
            "2026-02-01~2026-02-28,18000000,100,80\n"
        ).encode()
        result = parse_document(raw, "csv")
        self.assertEqual(result["room_revenue"], 34_200_000)
        self.assertEqual(result["sold_rooms"], 200)
        self.assertEqual(result["adr"], 171_000)
        self.assertEqual(result["period_start"], "2026-01-01")
        self.assertEqual(result["period_end"], "2026-02-28")
        self.assertEqual(result["occupancy_days"], 59)
        self.assertIsNone(result["occ"])

    def test_multirow_adr_uses_total_revenue_over_total_sold_rooms(self):
        raw = (
            "기간,객실매출,판매객실 수,ADR\n"
            "2026-01,100000,1,100000\n"
            "2026-02,900000,3,300000\n"
        ).encode()
        result = parse_document(raw, "csv")
        self.assertEqual(result["room_revenue"], 1_000_000)
        self.assertEqual(result["sold_rooms"], 4)
        self.assertEqual(result["adr"], 250_000)
        self.assertEqual(result["adr_source"], "calculated_from_room_revenue")

    def test_period_and_adr_only_table_does_not_read_year_as_adr_or_average_rows(self):
        raw = (
            "기간,ADR\n"
            "2026-01,100000\n"
            "2026-02,300000\n"
        ).encode()
        result = parse_document(raw, "csv")
        self.assertEqual(result["period_start"], "2026-01-01")
        self.assertEqual(result["period_end"], "2026-02-28")
        self.assertIsNone(result["adr"])

    def test_unpaired_revenue_and_sold_rows_stay_unpaired_after_document_merge(self):
        raw = (
            "기간,객실매출,판매객실 수\n"
            "2026-01,100000,\n"
            "2026-02,,2\n"
        ).encode()
        document = parse_document(raw, "csv")
        self.assertFalse(document["adr_calculation_valid"])
        self.assertIsNone(document["adr"])
        self.assertIsNone(merge_documents([document])["adr"])

    def test_month_only_period_uses_the_full_calendar_month(self):
        result = parse_metrics("기간 2026-02 판매객실 수 140").as_dict()
        self.assertEqual(result["period_start"], "2026-02-01")
        self.assertEqual(result["period_end"], "2026-02-28")
        self.assertEqual(result["occupancy_days"], 28)

    def test_multi_period_occ_is_not_weighted_by_sold_rooms(self):
        raw = (
            "기간,판매객실 수,OCC\n"
            "2026-01-01~2026-01-31,10,10\n"
            "2026-02-01~2026-02-28,90,90\n"
        ).encode()
        result = parse_document(raw, "csv")
        self.assertIsNone(result["occ"])

    def test_different_document_periods_do_not_create_combined_occ(self):
        first = parse_metrics("기간 2026-01-01~2026-01-31 OCC 10%").as_dict()
        second = parse_metrics("기간 2026-02-01~2026-02-28 OCC 90%").as_dict()
        merged = merge_documents([first, second])
        self.assertIsNone(merged["occ"])
        self.assertIsNone(merged["occupancy_days"])

    def test_different_document_periods_do_not_create_combined_adr(self):
        first = parse_metrics("기간 2026-01-01~2026-01-31 객실매출 100000 판매객실 수 2").as_dict()
        second = parse_metrics("기간 2026-02-01~2026-02-28 객실매출 240000 판매객실 수 3").as_dict()
        merged = merge_documents([first, second])
        self.assertIsNone(merged["adr"])

    def test_isolated_parser_hard_stops_a_blocked_native_parser(self):
        started = time.monotonic()
        with self.assertRaisesRegex(DocumentParseError, "시간이 초과"):
            parse_documents_isolated(
                [(b"ignored", "csv")],
                timeout_seconds=0.15,
                worker_target=_blocking_worker,
            )
        self.assertLess(time.monotonic() - started, 3)

    def test_isolated_parser_returns_normal_results(self):
        documents = parse_documents_isolated([
            ("기간,객실매출,판매객실 수,OCC\n2026-06-01~2026-06-30,9000000,60,72".encode(), "csv")
        ], timeout_seconds=5)
        self.assertEqual(documents[0]["room_revenue"], 9_000_000)
        self.assertEqual(documents[0]["adr"], 150_000)

    def test_timeout_stops_parser_descendants_too(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = os.path.join(directory, "pid")
            with self.assertRaises(DocumentParseError):
                parse_documents_isolated(
                    [(marker.encode(), "csv")],
                    timeout_seconds=2,
                    worker_target=_descendant_worker,
                )
            for _ in range(20):
                if os.path.exists(marker):
                    break
                time.sleep(0.02)
            self.assertTrue(os.path.exists(marker))
            with open(marker, encoding="utf-8") as handle:
                pid = int(handle.read())
            time.sleep(0.1)
            try:
                state = subprocess.check_output(
                    ["ps", "-o", "stat=", "-p", str(pid)], text=True
                ).strip()
            except subprocess.CalledProcessError:
                state = ""
            self.assertTrue(not state or state.startswith("Z"), state)

    def test_parse_slot_rejects_a_second_concurrent_holder(self):
        first = try_acquire_parse_slot()
        self.assertIsNotNone(first)
        try:
            self.assertIsNone(try_acquire_parse_slot())
        finally:
            release_parse_slot(first)
        second = try_acquire_parse_slot()
        self.assertIsNotNone(second)
        release_parse_slot(second)


if __name__ == "__main__":
    unittest.main()