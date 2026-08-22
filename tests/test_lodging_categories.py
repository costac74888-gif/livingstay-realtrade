import json
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lodging_categories import (
    GENERAL_LODGING_HYGIENE_TYPES,
    TARGET_LODGING_HYGIENE_TYPES,
    is_target_lodging_hygiene,
)
from sync_lodgings import PROGRESS_TARGET_HYGIENES, _load_progress


class _ProgressCursor:
    def __init__(self, value):
        self.value = value

    def execute(self, *_args, **_kwargs):
        pass

    def fetchone(self):
        return {"value": self.value}


class LodgingCategoriesTest(unittest.TestCase):
    def test_confirmed_general_types_are_collected(self):
        self.assertEqual(
            GENERAL_LODGING_HYGIENE_TYPES,
            frozenset({"일반호텔", "여관업", "여인숙업"}),
        )
        for value in GENERAL_LODGING_HYGIENE_TYPES | {"숙박업(생활)"}:
            self.assertTrue(is_target_lodging_hygiene(value))

    def test_obsolete_general_label_and_ambiguous_types_are_not_collected(self):
        for value in ("숙박업(일반)", "숙박업 기타", "관광호텔", "휴양콘도미니엄업"):
            self.assertNotIn(value, TARGET_LODGING_HYGIENE_TYPES)
            self.assertFalse(is_target_lodging_hygiene(value))

    def test_old_scope_checkpoint_restarts_before_general_lodging_pages_are_skipped(self):
        old_living_only_checkpoint = json.dumps({
            "next_page": 200,
            "total_count": 58649,
            "target_hygienes": ["숙박업(생활)"],
        })
        self.assertEqual(
            _load_progress(_ProgressCursor(old_living_only_checkpoint)),
            {"next_page": 1, "total_count": None},
        )

    def test_matching_scope_checkpoint_continues_safely(self):
        current_scope_checkpoint = json.dumps({
            "next_page": 200,
            "total_count": 58649,
            "target_hygienes": PROGRESS_TARGET_HYGIENES,
        })
        self.assertEqual(
            _load_progress(_ProgressCursor(current_scope_checkpoint)),
            {"next_page": 200, "total_count": 58649},
        )


if __name__ == "__main__":
    unittest.main()