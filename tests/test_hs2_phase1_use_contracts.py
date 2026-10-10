"""S01-A01: executable classification/price contracts; no live application."""
import unittest
from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timedelta

from hs2_design.domain import (
    Classification, ContractError, LODGING_PERMITS, StayKind, classify_use,
)
from hs2_design.pricing import (
    PriceLine, Terms, lodging_date_snapshot, price_snapshot, validate_interval,
)


class UseContracts(unittest.TestCase):
    def setUp(self):
        self.lodging = Classification("stay:one", StayKind.LODGING, "permit:fixture", "classification:v1")
        self.non_lodging = Classification("stay:two", StayKind.NON_LODGING, "review:fixture", "classification:v1")
        # Review flags are artificial fixture decisions, not business approval.
        self.terms = Terms("fixture-terms:v1", "Asia/Seoul", True)
        self.start = date(2026, 10, 9)

    def daily(self, rates, days=1, **kwargs):
        return lodging_date_snapshot(
            self.lodging, self.start, self.start + timedelta(days=days), rates,
            tariff_version="fixture-rates:v1", terms=self.terms,
            adjustments=(), **kwargs,
        )

    def test_verified_lodging_permits_include_rural_urban_camping(self):
        for permit in LODGING_PERMITS:
            with self.subTest(permit=permit):
                result = classify_use(
                    "stay:one", building_use="주택", channel="Airbnb",
                    permit=permit, permit_verified=True,
                    evidence_id="verified-fixture", decision_version="v1",
                )
                self.assertEqual(result.kind, StayKind.LODGING)
                validate_interval(result, self.start, self.start + timedelta(days=1))

    def test_channel_or_building_use_alone_never_decides(self):
        for use in ("주택", "숙박시설", "상가", "창고", "기타", "복합"):
            for channel in ("Airbnb", "OTA", "direct", ""):
                with self.subTest(use=use, channel=channel):
                    c = classify_use("stay:one", building_use=use, channel=channel)
                    self.assertEqual(c.kind, StayKind.UNRESOLVED)

    def test_unverified_permit_does_not_allow_one_night(self):
        c = classify_use("stay:one", building_use="주택", channel="Airbnb", permit="rural_guesthouse")
        with self.assertRaisesRegex(ContractError, "CLASSIFICATION_REQUIRES_REVIEW"):
            validate_interval(c, self.start, self.start + timedelta(days=7))

    def test_non_lodging_needs_independent_evidenced_review(self):
        c = classify_use(
            "stay:two", building_use="주택", channel="Airbnb",
            non_lodging_reviewed=True, evidence_id="review", decision_version="v1",
        )
        self.assertEqual(c.kind, StayKind.NON_LODGING)
        with self.assertRaises(ContractError):
            classify_use("stay:two", building_use="주택", channel="", non_lodging_reviewed=True)

    def test_conflicting_decisions_and_unknown_permits_fail_closed(self):
        with self.assertRaisesRegex(ContractError, "CONFLICTING"):
            classify_use("stay:one", building_use="", channel="", permit="camping",
                         permit_verified=True, non_lodging_reviewed=True)
        with self.assertRaisesRegex(ContractError, "UNKNOWN_PERMIT"):
            classify_use("stay:one", building_use="", channel="", permit="unmapped", permit_verified=True)
        with self.assertRaisesRegex(ContractError, "UNRESOLVED_PERMIT"):
            classify_use("stay:one", building_use="", channel="", permit="camping", non_lodging_reviewed=True)

    def test_lodging_zero_nights_rejected_one_night_allowed(self):
        with self.assertRaises(ContractError):
            validate_interval(self.lodging, self.start, self.start)
        validate_interval(self.lodging, self.start, self.start + timedelta(days=1))

    def test_non_lodging_six_days_rejected_seven_allowed(self):
        with self.assertRaises(ContractError):
            validate_interval(self.non_lodging, self.start, self.start + timedelta(days=6))
        validate_interval(self.non_lodging, self.start, self.start + timedelta(days=7))

    def test_reverse_range_and_datetime_are_rejected(self):
        with self.assertRaises(ContractError):
            validate_interval(self.lodging, self.start, self.start - timedelta(days=1))
        with self.assertRaises(ContractError):
            validate_interval(self.lodging, datetime(2026, 10, 9), datetime(2026, 10, 10))

    def test_date_prices_use_overrides_and_exclude_checkout(self):
        rates = {self.start: 100_000, self.start + timedelta(days=1): 170_000,
                 self.start + timedelta(days=2): 999_999}
        result = self.daily(rates, days=2)
        self.assertEqual(result.accommodation_krw, 270_000)
        self.assertEqual(len(result.lines), 2)
        self.assertEqual(result.lines[-1].end, self.start + timedelta(days=2))

    def test_missing_date_rate_never_falls_back(self):
        with self.assertRaisesRegex(ContractError, "MISSING_DATE_RATE"):
            self.daily({self.start: 100_000}, days=2)

    def test_invalid_money_including_bool_and_won_unit_overflow_rejected(self):
        for value in (-1, 0, True, 0.5, "100000", 2**63):
            with self.subTest(value=value), self.assertRaises(ContractError):
                self.daily({self.start: value})

    def test_week_prices_support_effective_period_changes(self):
        end = self.start + timedelta(days=14)
        rows = [PriceLine(self.start, self.start + timedelta(days=7), "week", 700_000),
                PriceLine(self.start + timedelta(days=7), end, "week", 800_000)]
        result = price_snapshot(self.non_lodging, self.start, end, rows,
                                tariff_version="v1", terms=self.terms, adjustments=())
        self.assertEqual(result.total_krw, 1_500_000)

    def test_partial_week_does_not_invent_prorata(self):
        end = self.start + timedelta(days=10)
        with self.assertRaisesRegex(ContractError, "PARTIAL_PERIOD"):
            price_snapshot(self.non_lodging, self.start, end,
                           [PriceLine(self.start, end, "week", 1_000_000)],
                           tariff_version="v1", terms=self.terms, adjustments=())

    def test_month_price_blocks_until_boundary_policy_reviewed(self):
        start, end = date(2028, 2, 1), date(2028, 3, 1)
        rows = [PriceLine(start, end, "month", 2_000_000)]
        with self.assertRaisesRegex(ContractError, "MONTH_POLICY"):
            price_snapshot(self.non_lodging, start, end, rows,
                           tariff_version="v1", terms=self.terms, adjustments=())
        fixture_terms = replace(self.terms, month_basis="reviewed_explicit_periods")
        result = price_snapshot(self.non_lodging, start, end, rows,
                                tariff_version="v1", terms=fixture_terms, adjustments=())
        self.assertEqual((result.check_out - result.check_in).days, 29)
        self.assertEqual(result.total_krw, 2_000_000)

    def test_wrong_price_unit_for_either_classification_rejected(self):
        end = self.start + timedelta(days=7)
        for kind, rows in (
            (self.lodging, [PriceLine(self.start, end, "week", 700_000)]),
            (self.non_lodging, [PriceLine(self.start, end, "night", 700_000)]),
        ):
            with self.subTest(kind=kind.kind), self.assertRaises(ContractError):
                price_snapshot(kind, self.start, end, rows, tariff_version="v1",
                               terms=self.terms, adjustments=())

    def test_gap_overlap_unsorted_and_incomplete_prices_rejected(self):
        end = self.start + timedelta(days=14)
        first = PriceLine(self.start, self.start + timedelta(days=7), "week", 700_000)
        next_line = PriceLine(first.end, end, "week", 700_000)
        for rows in ([], [first], [first, first], [next_line, first]):
            with self.subTest(rows=rows), self.assertRaises(ContractError):
                price_snapshot(self.non_lodging, self.start, end, rows,
                               tariff_version="v1", terms=self.terms, adjustments=())

    def test_business_terms_timezone_and_tariff_must_be_explicit(self):
        row = PriceLine(self.start, self.start + timedelta(days=1), "night", 100_000)
        for terms, tariff in (
            (replace(self.terms, reviewed=False), "v1"),
            (replace(self.terms, version=""), "v1"),
            (replace(self.terms, timezone="NoSuch/BusinessZone"), "v1"),
            (self.terms, ""),
        ):
            with self.subTest(terms=terms, tariff=tariff), self.assertRaises(ContractError):
                price_snapshot(self.lodging, row.start, row.end, [row],
                               tariff_version=tariff, terms=terms, adjustments=())

    def test_snapshot_survives_source_price_terms_and_classification_changes(self):
        rates = {self.start: 100_000}
        result = self.daily(rates)
        rates[self.start] = 999_000
        changed_terms = replace(self.terms, version="v2")
        changed_classification = replace(self.lodging, decision_version="v2")
        self.assertEqual(result.total_krw, 100_000)
        self.assertEqual(result.terms_version, "fixture-terms:v1")
        self.assertNotEqual(result.classification_version, changed_classification.decision_version)
        self.assertNotEqual(result.terms_version, changed_terms.version)
        with self.assertRaises(FrozenInstanceError):
            result.tariff_version = "v2"
        with self.assertRaises(FrozenInstanceError):
            result.lines[0].amount_krw = 123
        with self.assertRaises(TypeError):
            result.lines[0] = result.lines[0]
        with self.assertRaises(ContractError):
            replace(result, lines=list(result.lines))

    def test_explicit_adjustments_are_copied_and_frozen_with_price(self):
        components = [["reviewed-fixture-fee", 3_000], ["reviewed-fixture-discount", -1_000]]
        result = lodging_date_snapshot(
            self.lodging, self.start, self.start + timedelta(days=1), {self.start: 100_000},
            tariff_version="v1", terms=self.terms, adjustments=components,
        )
        components[0][1] = 999_999
        self.assertEqual(result.adjustments[0][1], 3_000)
        self.assertEqual(result.total_krw, 102_000)

    def test_duplicate_invalid_adjustment_or_nonpositive_total_rejected(self):
        row = PriceLine(self.start, self.start + timedelta(days=1), "night", 100_000)
        for components in ([("fee", 1), ("fee", 2)], [("fee", True)], [("discount", -100_000)]):
            with self.subTest(components=components), self.assertRaises(ContractError):
                price_snapshot(self.lodging, row.start, row.end, [row],
                               tariff_version="v1", terms=self.terms, adjustments=components)


if __name__ == "__main__":
    unittest.main()
