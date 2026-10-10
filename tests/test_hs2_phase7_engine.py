import unittest
from datetime import date
from hs2_design.domain import Classification, ContractError, StayKind
from hs2_calendar.engine import anniversary, build_snapshot, change, safe_quote, local_date


class CalendarEngine(unittest.TestCase):
    def calendar(self, kind="lodging"):
        return dict(kind=kind, base=100000, weekly=300000, monthly=1000000,
                    daily={}, periods={}, blocked=[], inclusive=True)

    def classification(self, kind):
        return Classification("private-listing", StayKind(kind), "operator-reviewed", "revision:1")

    def quote(self, start, end, calendar):
        return build_snapshot(self.classification(calendar["kind"]), date.fromisoformat(start),
                              date.fromisoformat(end), calendar, tariff_version="calendar:v1",
                              minimum_stay=1 if calendar["kind"] == "lodging" else 7)

    def test_lodging_every_day_explicit_override_total(self):
        c = self.calendar()
        c["daily"]["2027-01-02"] = 250000
        s = self.quote("2027-01-01", "2027-01-04", c)
        self.assertEqual(s.total_krw, 450000)
        self.assertEqual(len(s.lines), 3)

    def test_non_lodging_whole_week_no_partial_or_day_conversion(self):
        c = self.calendar("non_lodging")
        self.assertEqual(self.quote("2027-01-01", "2027-01-15", c).total_krw, 600000)
        for end in ("2027-01-07", "2027-01-09"):
            with self.assertRaises(ContractError):
                self.quote("2027-01-01", end, c)

    def test_month_anniversary_leap_end_clamping_no_drift(self):
        self.assertEqual(anniversary(date(2028, 1, 31), 1), date(2028, 2, 29))
        self.assertEqual(anniversary(date(2028, 1, 31), 2), date(2028, 3, 31))
        self.assertEqual(anniversary(date(2027, 1, 31), 1), date(2027, 2, 28))
        c = self.calendar("non_lodging")
        c["weekly"] = None
        s = self.quote("2027-01-31", "2027-03-31", c)
        self.assertEqual(s.total_krw, 2000000)
        self.assertEqual(s.lines[1].end, date(2027, 3, 31))

    def test_cheapest_exact_combo_and_equal_cost_month_preference(self):
        c = self.calendar("non_lodging")
        c["monthly"] = 900000
        s = self.quote("2027-02-01", "2027-03-01", c)
        self.assertEqual(s.total_krw, 900000)
        c["monthly"] = 1200000
        self.assertEqual(self.quote("2027-02-01", "2027-03-01", c).lines[0].unit, "month")
        c["monthly"] = 1500000
        self.assertEqual(self.quote("2027-02-01", "2027-03-01", c).lines[0].unit, "week")

    def test_future_period_rate_change_applies_start_boundary(self):
        c = self.calendar("non_lodging")
        c["weekly"] = None
        c["periods"]["2027-02-10"] = dict(monthly=1300000)
        s = self.quote("2027-01-10", "2027-03-10", c)
        self.assertEqual(s.total_krw, 2300000)

    def test_weekday_bulk_override_then_single_override_and_old_snapshot(self):
        c = self.calendar()
        cmd = dict(start="2027-01-01", end="2027-01-08", action="nightly",
                   values={"4": 180000, "5": 200000, "6": 160000}, inclusive=True)
        changed = change(c, cmd, date(2026, 10, 11))
        frozen = self.quote("2027-01-01", "2027-01-04", changed)
        newer = change(changed, {**cmd, "end": "2027-01-02", "values": {"4": 250000}}, date(2026, 10, 11))
        self.assertEqual(frozen.total_krw, 540000)
        self.assertEqual(self.quote("2027-01-01", "2027-01-04", newer).total_krw, 610000)
        self.assertEqual(c["daily"], {})

    def test_closed_date_blocks_entire_stay_checkout_exclusive(self):
        c = self.calendar()
        c["blocked"] = ["2027-01-04"]
        self.assertEqual(self.quote("2027-01-01", "2027-01-04", c).total_krw, 300000)
        with self.assertRaises(ContractError):
            self.quote("2027-01-01", "2027-01-05", c)

    def test_missing_zero_price_and_inclusive_ack_fail_explicitly(self):
        for changes in ({"base": None}, {"base": 0}, {"inclusive": False}):
            with self.assertRaises(ContractError):
                self.quote("2027-01-01", "2027-01-02", {**self.calendar(), **changes})

    def test_mutation_future_bounds_and_shape_bool_or_wrong_type(self):
        cmd = dict(start="2027-01-01", end="2027-01-02", action="nightly", values={"4": 150000}, inclusive=True)
        for changes in ({"start": "2026-10-10"}, {"values": {"4": True}}, {"values": {"7": 1}},
                        {"inclusive": False}, {"action": "unknown"}, {"end": "2030-01-01"}):
            with self.assertRaises(ContractError):
                change(self.calendar(), {**cmd, **changes}, date(2026, 10, 11))

    def test_period_rates_none_is_explicit_disable_not_zero(self):
        c = change(self.calendar("non_lodging"),
                   dict(start="2027-01-01", end="2027-01-02", action="periods",
                        values={"weekly": None}, inclusive=True), date(2026, 10, 11))
        with self.assertRaises(ContractError):
            self.quote("2027-01-01", "2027-01-08", c)

    def test_minimum_stay_and_classification_price_mismatch(self):
        with self.assertRaises(ContractError):
            build_snapshot(self.classification("lodging"), date(2027, 1, 1), date(2027, 1, 3),
                           self.calendar(), tariff_version="v1", minimum_stay=3)
        with self.assertRaises(ContractError):
            self.quote("2027-01-01", "2027-01-02", {**self.calendar(), "kind": "non_lodging"})

    def test_public_quote_does_not_contain_private_identity_or_booking_claim(self):
        result = safe_quote("random-public", self.quote("2027-01-01", "2027-01-02", self.calendar()))
        self.assertNotIn("private-listing", str(result))
        self.assertFalse(result["booking_confirmed"])
        self.assertFalse(result["deposit_included"])

    def test_dates_canonical_and_inputs_not_default_today(self):
        for value in ("2027-1-1", "20270101", "2027-02-30", None, True):
            with self.assertRaises(ContractError):
                local_date(value)
