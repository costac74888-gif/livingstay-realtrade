import unittest
from pathlib import Path

from app import (
    _camping_content_id,
    _choose_camping_detail_row,
    _choose_verified_camping_web_row,
)


ROOT = Path(__file__).resolve().parents[1]


class CampingDetailUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app_source = (ROOT / "app.py").read_text(encoding="utf-8")
        cls.main_source = (ROOT / "static/js/main.js").read_text(encoding="utf-8")
        cls.db_source = (ROOT / "db.py").read_text(encoding="utf-8")

    def test_schema_and_detail_api_include_gocamping_metadata(self):
        for field in (
            "camping_location_types",
            "camping_theme_types",
            "camping_amenities",
            "camping_toilet_count",
            "camping_shower_count",
            "camping_sink_count",
            "camping_operating_seasons",
            "camping_animal_policy",
            "camping_reservation_url",
            "camping_first_image_url",
        ):
            self.assertIn(field, self.db_source)
            self.assertIn(field, self.app_source)
        self.assertIn('result["camping"] = camping', self.app_source)
        self.assertIn('"info_url": info_url', self.app_source)
        self.assertIn('"content_id": content_id', self.app_source)
        self.assertIn('"detail_fields": web_detail.get("detail_fields")', self.app_source)
        self.assertIn('"photos": image_urls', self.app_source)

    def test_camping_card_replaces_transaction_cards_and_resets(self):
        self.assertIn('id="bCampCard"', self.main_source)
        self.assertIn("function _renderCampingSection(b)", self.main_source)
        self.assertIn('["bAreaFilterCard", "bTrendCard", "bTxCard"]', self.main_source)
        self.assertIn('if (b.lodging_type !== "캠핑")', self.main_source)
        self.assertIn('card.style.display = "none"', self.main_source)
        self.assertIn("function _campingAnimalLabel(value)", self.main_source)
        self.assertIn("`반려동물 동반 ${policy}`", self.main_source)
        self.assertNotIn('id="bCampInfoLink"', self.main_source)
        self.assertIn("camp-gocamping-btn", self.main_source)
        self.assertNotIn("캠핑장 예약 페이지 열기 ↗", self.main_source)
        self.assertIn(
            'class="camp-contact-btn camp-gocamping-btn" href="${escapeHtml(infoUrl)}"',
            self.main_source,
        )
        self.assertIn('고캠핑에서 이 캠핑장 상세 보기', self.main_source)
        self.assertIn('class="camp-gocamping-chip"', self.main_source)
        self.assertIn('href="${escapeHtml(infoUrl)}"', self.main_source)
        self.assertIn('operator-banner-cta', self.main_source)
        self.assertIn('운영 파트너 등록', self.main_source)
        self.assertIn(
            'operations: ["bCampCard", "bNonCampingOperationsCard", "bReservationCard", "bLodgingOperatorCard", "bOperatorInfoDisclaimer"]',
            self.main_source,
        )

    def test_camping_public_links_fall_back_to_canonical_source_fields(self):
        self.assertIn("def _camping_content_id(camping_row, verified_web_row=None)", self.app_source)
        self.assertIn('r"CAMPING:(\\d+)"', self.app_source)
        self.assertIn("or format_phone(camping_row.get(\"phone\"))", self.app_source)
        self.assertEqual(
            _camping_content_id({"permit_number": "CAMPING:2185"}),
            "2185",
        )
        self.assertIn('camping_operator.get("booking_url")', self.app_source)
        self.assertIn(
            'or _safe_public_url(camping_row.get("camping_reservation_url"))',
            self.app_source,
        )
        self.assertNotIn(
            "_camping_official_homepage_from_reservation",
            self.app_source,
        )

    def test_camping_booking_does_not_treat_gocamping_guide_as_reservation(self):
        self.assertIn('host.includes("gocamping")', self.main_source)
        self.assertIn('camping_resve_url', self.main_source)
        self.assertIn('const infoUrl = _publicHttpUrl(b?.camping?.info_url)', self.main_source)

    def test_odd_facility_count_has_no_placeholder_cell(self):
        self.assertIn('.camp-facts div:last-child:nth-child(odd)', (ROOT / "static/css/main.css").read_text(encoding="utf-8"))

    def test_gocamping_images_are_available_even_with_existing_photos(self):
        self.assertIn('"source": "gocamping"', self.app_source)
        self.assertIn("gocamping_photos =", self.app_source)
        self.assertNotIn('camping["image_urls"] and not building["photos"]', self.app_source)
        self.assertIn('photo?.source === "gocamping"', self.main_source)
        self.assertIn("renderPhotoSlider(gocampingInitial)", self.main_source)
        self.assertIn(
            "saved?.streetview_available === true && !gocampingInitial.length",
            self.main_source,
        )

    def test_canonical_gocamping_row_wins_over_larger_csv_row(self):
        selected = _choose_camping_detail_row([
            {
                "permit_number": "CAMPING:1234567:LOCAL-1",
                "camping_site_count": 100,
                "camping_first_image_url": None,
            },
            {
                "permit_number": "CAMPING:217764",
                "camping_site_count": 12,
                "camping_amenities": "전기,온수",
                "camping_first_image_url": "https://example.com/camp.jpg",
            },
        ])
        self.assertEqual(selected["permit_number"], "CAMPING:217764")
        self.assertEqual(
            selected["camping_first_image_url"],
            "https://example.com/camp.jpg",
        )

    def test_verified_web_row_can_enrich_separate_canonical_row(self):
        canonical = {
            "permit_number": "CAMPING:100093",
            "biz_name": "비토애글램핑2호점",
            "gocamping_content_id": "100093",
        }
        csv_row = {
            "permit_number": "CAMPING:local:permit",
            "biz_name": "비토애글램핑2호점(BITOLUV GLAMPING Season2)",
            "gocamping_content_id": "100093",
            "gocamping_detail": {"intro": "공식 웹 소개"},
            "gocamping_detail_fetched_at": "2026-09-06",
        }
        selected = _choose_verified_camping_web_row([canonical, csv_row], canonical)
        self.assertIs(selected, csv_row)

    def test_verified_web_row_rejects_conflicting_content_ids(self):
        canonical = {"permit_number": "CAMPING:1", "biz_name": "같은 이름"}
        rows = [
            canonical,
            {"biz_name": "같은 이름", "gocamping_content_id": "1",
             "gocamping_detail": {"intro": "A"}},
            {"biz_name": "같은 이름", "gocamping_content_id": "2",
             "gocamping_detail": {"intro": "B"}},
        ]
        self.assertIsNone(_choose_verified_camping_web_row(rows, canonical))


if __name__ == "__main__":
    unittest.main()