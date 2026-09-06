"""Focused public contract tests for unified official operating records."""
import os
import sys
import unittest
from unittest.mock import MagicMock

os.environ.setdefault("SKIP_STARTUP_SCHEMA_INIT", "1")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import app as application


class PublicOperatingRecordTests(unittest.TestCase):
    def _row(self, **values):
        base = {
            "biz_name": "공식 숙소", "permit_number": "TOURISM:1",
            "permit_date": "2025-01-01", "biz_status_name": "영업/정상",
            "biz_status_detail": "정상", "room_count": 12,
            "camping_site_count": None, "camping_general_site_count": None,
            "camping_auto_site_count": None, "camping_glamping_site_count": None,
            "camping_caravan_site_count": None, "camping_classification": None,
            "hygiene_type": "관광호텔업", "phone": "02-1234-5678",
            "road_address": "서울 중구 세종대로 1", "jibun_address": "서울 중구 태평로1가 1",
            "source_updated_at": "2025-02-01",
        }
        base.update(values)
        return base

    def test_road_first_returns_all_active_permits_and_public_fields_only(self):
        cur = MagicMock()
        cur.fetchall.return_value = [self._row(), self._row(permit_number="PENSION:2")]
        records = application._public_lodging_registry_records(
            cur, {"road_address": "서울 중구 세종대로 1", "jibun_address": "서울 중구 태평로1가 1"})
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["address_match_method"], "road")
        self.assertEqual(records[1]["source_name"], "관광펜션업 CSV")
        self.assertNotIn("facility_area", records[0])
        self.assertNotIn("camping_amenities", records[0])
        self.assertNotIn("phone", records[0])
        self.assertNotIn("biz_status_detail", records[0])

    def test_jibun_is_used_only_when_road_has_no_active_record(self):
        cur = MagicMock()
        cur.fetchall.side_effect = [[], [self._row(permit_number="RURAL:2")]]
        records = application._public_lodging_registry_records(
            cur, {"road_address": "서울 중구 세종대로 1", "jibun_address": "서울 중구 태평로1가 1"})
        self.assertEqual(records[0]["address_match_method"], "jibun")
        self.assertEqual(cur.execute.call_count, 2)

    def test_camping_inventory_is_not_room_inventory(self):
        cur = MagicMock()
        cur.fetchall.return_value = [self._row(
            permit_number="CAMPING:123", hygiene_type="자동차야영장업", room_count=None,
            camping_site_count=20, camping_general_site_count=2,
            camping_auto_site_count=10, camping_glamping_site_count=5,
            camping_caravan_site_count=3, camping_classification="오토·글램핑")]
        record = application._public_lodging_registry_records(
            cur, {"road_address": "서울 중구 세종대로 1"})[0]
        self.assertIsNone(record["official_room_count"])
        self.assertEqual(record["official_site_count"], 20)
        self.assertEqual(record["camping_site_composition"], "오토·글램핑")
        self.assertEqual(record["legal_category"], "자동차야영장업")

    def test_dedupe_requires_strong_permit_or_name_address_key(self):
        same = {"permit_number": "1", "source_name": "A", "registered_name": "가",
                "official_road_address": "서울 중구 세종대로 1"}
        duplicate = {**same, "source_name": "B"}
        unknown = {"permit_number": None, "source_name": "C", "registered_name": None,
                   "official_road_address": None}
        result = application._deduplicate_public_operating_records([same, duplicate, unknown])
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["source_provenance"], ["A", "B"])

    def test_annual_projection_preserves_hotel_grade(self):
        cur = MagicMock()
        with unittest.mock.patch.object(
            application.annual_tourism_roster,
            "latest_linked_operating_records",
            return_value=[{
                "facility_name": "호텔신라",
                "subtype": "관광호텔업",
                "hotel_grade": "5성급",
                "registration_number": "26003-1978-000001",
                "official_room_count": 464,
                "address": "서울특별시 중구 동호로 249",
                "reference_year": 2025,
                "source": "관광숙박업 등록현황",
            }],
        ):
            record = application._public_annual_operating_records(cur, 1)[0]
        self.assertEqual(record["hotel_grade"], "5성급")
        self.assertNotIn("phone", record)

    def test_annual_tourism_record_is_selected_as_operating_primary(self):
        registry = {"source_category": "lodging_registry", "registered_name": "일반 신고명"}
        annual = {"source_category": "annual_tourism_roster", "registered_name": "관광 등록명"}
        records = [registry, annual]
        primary = next(
            (row for row in records if row.get("source_category") == "annual_tourism_roster"),
            records[0],
        )
        self.assertEqual(primary["registered_name"], "관광 등록명")

    def test_inactive_registry_rows_are_not_exposed(self):
        cur = MagicMock()
        cur.fetchall.return_value = [
            self._row(biz_status_name="폐업", biz_status_detail="폐업"),
            self._row(permit_number="RURAL:ACTIVE"),
        ]
        records = application._public_lodging_registry_records(
            cur, {"road_address": "서울 중구 세종대로 1"})
        self.assertEqual([record["permit_number"] for record in records], ["RURAL:ACTIVE"])
        serialized = repr(records)
        self.assertNotIn("폐업", serialized)

    def test_every_imported_source_prefix_has_an_explicit_public_label(self):
        expected = {
            "TOURISM:1": "관광숙박업 등록현황(문체부)",
            "PENSION:1": "관광펜션업 CSV",
            "RURAL:1": "농어촌민박업 CSV",
            "AIRBNB:1": "외국인관광도시민박업 CSV",
            "HANOK:1": "한옥체험업 CSV",
            "CAMPING:1": "고캠핑 API",
            "CAMPING:1:2": "정부 야영장 CSV",
            "3491000-201-2017-00009": "숙박업 영업신고 원장(행안부)",
        }
        for permit_number, label in expected.items():
            with self.subTest(permit_number=permit_number):
                self.assertEqual(
                    application._admin_lodging_source_label(permit_number),
                    label,
                )


if __name__ == "__main__":
    unittest.main()