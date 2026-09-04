import unittest
from pathlib import Path

from app import _choose_camping_detail_row


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

    def test_camping_card_replaces_transaction_cards_and_resets(self):
        self.assertIn('id="bCampCard"', self.main_source)
        self.assertIn("function _renderCampingSection(b)", self.main_source)
        self.assertIn('["bAreaFilterCard", "bTrendCard", "bTxCard"]', self.main_source)
        self.assertIn('if (b.lodging_type !== "캠핑")', self.main_source)
        self.assertIn('card.style.display = "none"', self.main_source)
        self.assertIn("function _campingAnimalLabel(value)", self.main_source)
        self.assertIn("`반려동물 동반 ${policy}`", self.main_source)

    def test_gocamping_image_is_a_photo_fallback(self):
        self.assertIn('"source": "gocamping"', self.app_source)
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


if __name__ == "__main__":
    unittest.main()