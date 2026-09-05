import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FavoriteLimitConsistencyTests(unittest.TestCase):
    def test_server_and_browser_use_same_regular_user_limit(self):
        app_source = (ROOT / "app.py").read_text(encoding="utf-8")
        js_source = (ROOT / "static/js/main.js").read_text(encoding="utf-8")

        server_match = re.search(r"^MAX_FAVORITES\s*=\s*(\d+)", app_source, re.MULTILINE)
        browser_match = re.search(
            r"^const MAX_FAVORITES = IS_ADMIN \? \d+ : (\d+);",
            js_source,
            re.MULTILINE,
        )

        self.assertIsNotNone(server_match)
        self.assertIsNotNone(browser_match)
        self.assertEqual(server_match.group(1), browser_match.group(1))
        self.assertEqual(server_match.group(1), "30")


if __name__ == "__main__":
    unittest.main()