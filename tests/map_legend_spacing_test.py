import unittest
from pathlib import Path


class MapLegendSpacingTest(unittest.TestCase):
    def test_desktop_legend_starts_after_side_panel(self):
        css = Path("static/css/main.css").read_text(encoding="utf-8")
        self.assertIn(
            "left:calc(var(--panel-w) + var(--stage-gap) * 2); z-index:15;",
            css,
        )
        self.assertIn(
            "body:has(.side-panel.panel-collapsed) "
            ".map-legend{left:var(--stage-gap);}",
            css,
        )
        self.assertIn(
            "@media (max-width: 980px){\n    "
            ".map-legend{left:var(--stage-gap);}",
            css,
        )


if __name__ == "__main__":
    unittest.main()