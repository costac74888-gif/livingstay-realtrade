import json
import unittest
from datetime import date
from scripts.hs2_rate_preview import base_rates, candidate_ends, NOTICE, PreviewRateSearch
from hs2_calendar.engine import anniversary


class PublicBaseRates(unittest.TestCase):
    def test_allowlist_not_calendar_payload(self):
        rates = base_rates("lodging", dict(kind="lodging", base=178000,
            weekly=None, monthly=None, daily={"secret-day": 999},
            blocked=["secret-day"], periods={"secret": 77}, application_id="PRIVATE"), allowed=True)
        self.assertEqual(rates, {"night": 178000})
        self.assertNotIn("secret", json.dumps(rates))

    def test_zero_is_not_missing(self):
        self.assertEqual(base_rates("lodging", {"kind": "lodging", "base": 0},
                                   allowed=True), {"night": 0})
        self.assertIsNone(base_rates("lodging", {"kind": "lodging"}, allowed=True))
        self.assertEqual(base_rates("non_lodging",
            {"kind": "non_lodging", "weekly": 0}, allowed=True), {"week": 0, "month": None})
        self.assertEqual(base_rates("non_lodging",
            {"kind": "non_lodging", "monthly": 10}, allowed=True), {"week": None, "month": 10})
        self.assertIsNone(base_rates("non_lodging", {"kind": "non_lodging"}, allowed=True))

    def test_strict_types_ranges_and_kind_mix(self):
        for value in (True, False, "12", 12.0, 12.1, -1, 1000000001, [], {}):
            with self.subTest(value=value):
                self.assertIsNone(base_rates("lodging", {"kind": "lodging", "base": value}, allowed=True))
                self.assertIsNone(base_rates("non_lodging",
                    {"kind": "non_lodging", "weekly": 10, "monthly": value}, allowed=True))
        for c in ({"kind": "lodging", "base": 10, "weekly": 0},
                  {"kind": "non_lodging", "base": 0, "weekly": 10},
                  {"kind": "unknown", "base": 10}):
            self.assertIsNone(base_rates(c["kind"], c, allowed=True))
        self.assertIsNone(base_rates("lodging", {"kind": "non_lodging", "base": 10}, allowed=True))
        self.assertEqual(base_rates("lodging", {"kind": "lodging", "base": 1000000000},
                                   allowed=True), {"night": 1000000000})

    def test_explicit_public_permission_required(self):
        for allowed in (False, None, 1, "true"):
            self.assertIsNone(base_rates("lodging", {"kind": "lodging", "base": 1}, allowed=allowed))

    def test_month_only_candidates_never_promise_weeks(self):
        result = candidate_ends("2028-01-31", "2028-02-10", {"week": None, "month": 100})
        self.assertEqual(result[0], "2028-02-29")
        self.assertNotIn("2028-02-07", result)
        self.assertIn("2028-03-31", result)

    def test_week_month_candidates_use_original_anniversary(self):
        result = candidate_ends("2027-01-31", "2027-03-07", {"week": 10, "month": 20})
        self.assertNotIn("2027-03-07", result)  # exclude the current selection
        self.assertIn(anniversary(date(2027, 1, 31), 2).isoformat(), result)
        self.assertIn("2027-02-28", result)
        self.assertEqual(NOTICE, "기본 요금이며 날짜에 따라 다를 수 있습니다")

    def test_hidden_count_before_pagination_and_all_same_filters(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from hs2_design.domain import ContractError
        from hs2_supermap.contracts import parse
        safe = [dict(public_id=f"00000000-0000-4000-8000-{i:012d}",
                     stay_kind="non_lodging") for i in range(70)]
        def quote(*_):
            raise ContractError("MINIMUM_STAY_NOT_MET")
        native = SimpleNamespace(calendar=SimpleNamespace(registrations=object(), quote=quote),
            search=lambda _: dict(items=[], counts={}, truncated={}, withheld_count=0,
                                  native_statistics_changed=False),
            public_location_match=lambda key, q: int(key[-12:]) < 35,
            public_geometry=lambda _: None)
        adapter = PreviewRateSearch(native)
        adapter.source = lambda _: ({"payload": {"public_summary": True, "min_stay": 7,
            "rooms": 1, "area_m2": "20", "guests": 2, "options": []}},
            {"blocked": []}, {"week": 0, "month": None})
        with patch("scripts.hs2_rate_preview.public_rows", return_value=safe):
            short = dict(check_in="2027-01-01", check_out="2027-01-02")
            self.assertEqual(adapter.search(parse(short))["period_hidden_count"], 70)
            self.assertEqual(adapter.search(parse({**short, "q": "match"}))["period_hidden_count"], 35)
            self.assertEqual(adapter.search(parse({**short, "guests": "3"}))["period_hidden_count"], 0)
            result = adapter.search(parse({}))
            self.assertEqual(result["counts"]["stay"], 70)
            self.assertEqual(len(result["items"]), 60)
            self.assertEqual(result["period_hidden_count"], 0)


if __name__ == "__main__":
    unittest.main()
