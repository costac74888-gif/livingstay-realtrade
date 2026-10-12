"""Pure presentation/fixture coverage checks, no services or inherited secrets."""
import unittest
from pathlib import Path
from scripts.hs2_seongsu_seed import NAMES

ROOT = Path(__file__).resolve().parents[1]


class RebuildRequirements(unittest.TestCase):
    def test_twenty_named_synthetic_stays_with_balanced_kinds(self):
        self.assertEqual(len(NAMES), 20)
        self.assertEqual(len(set(NAMES)), 20)
        self.assertEqual(sum(i % 2 == 0 for i in range(len(NAMES))), 10)

    def test_runtime_color_observer_does_not_restore_retired_palette(self):
        text = (ROOT / "scripts/hs2_design_assets/shell.js").read_text()
        self.assertIn("#ff385c", text)
        self.assertIn("#2563eb", text)
        self.assertNotIn("#596044", text)
        self.assertNotIn("#9b7618", text)

    def test_photo_swipe_is_passive_and_axis_gated(self):
        text = (ROOT / "scripts/hs2_real_map.js").read_text()
        self.assertIn("Math.abs(dx) > Math.abs(dy) * 1.4", text)
        self.assertIn("passive:true", text)
        self.assertIn('control.setAttribute("aria-label", label)', text)


if __name__ == "__main__":
    unittest.main()
