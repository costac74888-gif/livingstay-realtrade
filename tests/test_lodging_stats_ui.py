from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class LodgingStatsUiTests(unittest.TestCase):
    def test_admin_camping_uses_official_facility_and_site_fields(self):
        html = (ROOT / "static" / "admin.html").read_text(encoding="utf-8")
        self.assertIn('row.type === "캠핑" ? row.camping_facility_count', html)
        self.assertIn("row.camping_site_count", html)
        self.assertIn('["일반야영", breakdown.general_only, row.camping_general_site_count]', html)
        self.assertIn('["자동차야영", breakdown.auto_only, row.camping_auto_site_count]', html)
        self.assertIn('["글램핑", breakdown.glamping_only, row.camping_glamping_site_count]', html)
        self.assertIn('["카라반", breakdown.caravan_only, row.camping_caravan_site_count]', html)

    def test_mobile_home_table_fits_without_horizontal_scroll(self):
        css = (ROOT / "static" / "css" / "main.css").read_text(encoding="utf-8")
        self.assertIn(".datalab-table-wrap{overflow-x:hidden;}", css)
        self.assertIn(".datalab-table{width:100%; min-width:0; table-layout:fixed;", css)


if __name__ == "__main__":
    unittest.main()