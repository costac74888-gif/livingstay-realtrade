"""관리자 실거래 검색의 목록·엑셀 필터 일치 회귀 검사."""

import io
import os
import unittest
import uuid

from openpyxl import load_workbook

os.environ["DISABLE_EXTERNAL_NOTIFICATIONS"] = "1"

from app import app  # noqa: E402
from db import get_conn  # noqa: E402


class AdminTransactionSearchTest(unittest.TestCase):
    def test_filters_and_export_share_the_same_results(self):
        marker = "관리실거래검색" + uuid.uuid4().hex[:12]
        ids = []
        conn = get_conn()
        cur = conn.cursor()
        try:
            for sido, sgg, umd, year, lodging, scope in (
                ("서울", "강남구", "역삼동", "2025", "생활", "unit"),
                ("부산", "해운대구", "우동", "2024", "관광", "whole_building"),
            ):
                cur.execute("""
                    INSERT INTO transactions
                        (building_name, address, si_do, sgg_nm, umd_nm,
                         deal_date, lodging_type, transaction_scope, price)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 5000)
                    RETURNING id
                """, [marker, f"{umd} 시험주소", sido, sgg, umd,
                      f"{year}-05-20", lodging, scope])
                ids.append(cur.fetchone()["id"])
            conn.commit()

            with app.test_client() as client:
                with client.session_transaction() as session:
                    session["admin"] = True

                base = client.get("/api/admin/transactions", query_string={"q": marker})
                self.assertEqual(base.status_code, 200)
                self.assertEqual(base.get_json()["total"], 2)

                filters = {
                    "q": marker, "si_do": "서울특별시",
                    "sgg_nm": "서울특별시 강남구", "umd_nm": "역삼동",
                    "lodging_type": "생활", "year": "2025",
                    "transaction_scope": "unit",
                }
                filtered = client.get("/api/admin/transactions", query_string=filters)
                self.assertEqual(filtered.status_code, 200)
                self.assertEqual(filtered.get_json()["total"], 1)
                self.assertEqual(filtered.get_json()["items"][0]["id"], ids[0])

                export = client.get("/api/admin/transactions/export.xlsx", query_string=filters)
                self.assertEqual(export.status_code, 200)
                sheet = load_workbook(io.BytesIO(export.data), read_only=True).active
                self.assertEqual([row[0] for row in list(sheet.values)[1:]], [ids[0]])

                wrong = client.get("/api/admin/transactions", query_string={
                    "q": marker, "lodging_type": "캠핑",
                })
                self.assertEqual(wrong.get_json()["total"], 0)
        finally:
            if ids:
                cur.execute("DELETE FROM transactions WHERE id = ANY(%s)", [ids])
                conn.commit()
            cur.close()
            conn.close()


if __name__ == "__main__":
    unittest.main()