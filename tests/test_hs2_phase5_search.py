"""Real HTTP query contracts: period totals, missing quotes, privacy, failures."""
import unittest
from hs2_consumer.api import create_blueprint
from hs2_consumer.fixtures import create_fixture_app, fixture_catalog
from hs2_consumer.search import query, search
from hs2_design.domain import ContractError
from flask import Flask

DATES = {"check_in": "2026-11-01", "check_out": "2026-11-08"}


class ConsumerSearch(unittest.TestCase):
    def setUp(self):
        self.app = create_fixture_app()
        self.client = self.app.test_client()

    def get(self, values=None):
        return self.client.get("/hs2/api/consumer/search", query_string=values or {})

    def test_default_actual_nonempty_public_projection(self):
        data = self.get().get_json()
        self.assertEqual(data["count"], 3)
        self.assertEqual(data["price_basis"], "selected_stay_total")
        self.assertTrue(all(i["quote"] is None for i in data["items"]))

    def test_total_filter_not_daily_weekly_unit_conversion(self):
        data = self.get({**DATES, "min_total": "220000", "max_total": "250000"}).get_json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["items"][0]["quote"]["total_krw"], 240000)
        self.assertEqual(data["unquoted_count"], 1)

    def test_inclusive_endpoints_and_actual_zero_quote(self):
        data = search(query({**DATES, "min_total": "240000", "max_total": "240000"}), fixture_catalog)
        self.assertEqual(data["count"], 1)
        def zero(v):
            row = fixture_catalog(v)[0]
            row["quote"]["total_krw"] = 0
            return [row]
        self.assertEqual(search(query({**DATES, "max_total": "0"}), zero)["count"], 1)

    def test_missing_incomplete_mismatched_bool_stale_quotes_never_zero(self):
        for field, value in (("complete", False), ("check_out", "2026-12-01"),
                             ("total_krw", True), ("source_version", ""),
                             ("public_price_allowed", False), ("total_krw", -1)):
            def source(v):
                row = fixture_catalog(v)[0]
                row["quote"][field] = value
                return [row]
            result = search(query({**DATES, "max_total": "999999"}), source)
            self.assertEqual(result["count"], 0)
            self.assertEqual(result["unquoted_count"], 1)

    def test_price_filter_requires_complete_dates(self):
        for values in ({"min_total": "1"}, {"check_in": DATES["check_in"]},
                       {**DATES, "check_out": "2026-10-01"}):
            self.assertEqual(self.get(values).status_code, 400)

    def test_strict_shape_dates_numeric_and_options(self):
        for values in ({"user_id": "101"}, {"check_in": "20261101", "check_out": "20261108"},
                       {**DATES, "min_total": "-1"}, {**DATES, "min_total": "1.5"},
                       {**DATES, "max_total": "1000000001"}, {"guests": "１０"},
                       {"options": "wifi,wifi"}, {"options": "evil"}, {"instant": "true"},
                       {"q": "x" * 101}, {**DATES, "min_total": "9", "max_total": "1"}):
            self.assertEqual(self.get(values).status_code, 400)
        self.assertEqual(self.get([("q", "one"), ("q", "two")]).status_code, 400)

    def test_whitelisted_kind_and_safe_text_filter(self):
        self.assertEqual(self.get({"kind": "non_lodging"}).get_json()["count"], 1)
        self.assertEqual(self.get({"q": "숙박형"}).get_json()["count"], 2)
        self.assertEqual(self.get({"q": "NEVER_PUBLIC_BUILDING_NAME"}).get_json()["count"], 0)

    def test_non_lodging_minimum_seven_days(self):
        data = self.get({**DATES, "check_out": "2026-11-02"}).get_json()
        self.assertEqual(data["count"], 2)
        self.assertTrue(all(i["stay_kind"] == "lodging" for i in data["items"]))

    def test_unknown_private_attributes_do_not_match_filters(self):
        for v in ({"rooms": "1"}, {"guests": "2"}, {"min_area": "20"},
                  {"options": "wifi"}, {"instant": "1"}, {"discount": "1"}):
            self.assertEqual(self.get(v).get_json()["count"], 0)

    def test_no_private_payload_or_exact_geo(self):
        text = self.get(DATES).get_data(as_text=True)
        for value in ("NEVER_PUBLIC", '"lat"', '"lng"', "registered_building_id",
                      "private_address", "source_version", "photo"):
            self.assertNotIn(value, text)

    def test_failed_catalog_explicit_error_not_empty_success(self):
        app = Flask("failed_fixture")
        def fail(_):
            raise RuntimeError("secret-like internal payload MUST_NOT_LEAK")
        app.register_blueprint(create_blueprint(public_catalog=fail, map_config=lambda: None))
        response = app.test_client().get("/hs2/api/consumer/search")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("MUST_NOT_LEAK", response.get_data(as_text=True))

    def test_bad_source_identity_projection_and_duplicates_fail(self):
        for change in ("id", "precision", "duplicate"):
            def source(v):
                row = fixture_catalog(v)[0]
                if change == "id": row["public_id"] = "42"
                if change == "precision": row["location_precision"] = "exact"
                return [row, row] if change == "duplicate" else [row]
            with self.assertRaises((ContractError, ValueError)):
                search(query({}), source)

    def test_safe_zero_results_and_private_cache_headers(self):
        response = self.get({"kind": "lodging", "q": "없는 매물"})
        self.assertEqual(response.get_json()["items"], [])
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
