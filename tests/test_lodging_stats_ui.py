from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class LodgingStatsUiTests(unittest.TestCase):
    def test_admin_camping_uses_official_facility_and_site_fields(self):
        html = (ROOT / "static" / "admin.html").read_text(encoding="utf-8")
        self.assertIn('row.type === "캠핑" ? row.camping_facility_count', html)
        self.assertIn("row.camping_site_count", html)
        self.assertIn("const details = row.camping_classification_details || {}", html)
        self.assertIn('["일반야영", merge("general_only")]', html)
        self.assertIn('["자동차야영", merge("auto_only")]', html)
        self.assertIn('["글램핑", merge("glamping_only")]', html)
        self.assertIn('["카라반", merge("caravan_only")]', html)
        self.assertIn('["복합·미확인", merge("confirmed_mixed", "unknown")]', html)
        self.assertIn("${n(detail.matchedFacilityCount)}</td>", html)
        self.assertIn("${n(detail.matchedSiteCount)}</td>", html)
        self.assertIn("${pct(detail.reportRate)}</td>", html)
        self.assertNotIn("row.camping_general_site_count]", html)

    def test_mobile_home_table_fits_without_horizontal_scroll(self):
        css = (ROOT / "static" / "css" / "main.css").read_text(encoding="utf-8")
        self.assertIn(".datalab-table-wrap{overflow-x:hidden;", css)
        self.assertIn(".datalab-table{width:100%; min-width:0; table-layout:fixed;", css)
        main = (ROOT / "static" / "js" / "main.js").read_text(encoding="utf-8")
        self.assertIn('class="datalab-head-stack">건물수<small>(시설수)</small>', main)
        self.assertIn('class="datalab-head-stack">호실수<small>(사이트수)</small>', main)


if __name__ == "__main__":
    unittest.main()