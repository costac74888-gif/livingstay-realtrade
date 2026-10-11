import json
import unittest
from hs2_data.repository import connect_fixture
from hs2_supermap.fixtures import create_fixture_app, WHO
from hs2_supermap.contracts import parse
from scripts.hs2_rate_preview import install


class PreviewRateSQL(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from hs2_calendar.fixtures import create_fixture_app
        create_fixture_app()

    def setUp(self):
        with connect_fixture() as conn, conn.cursor() as c:
            c.execute("""TRUNCATE hs2_dev.calendar_versions,hs2_dev.registration_events,
                hs2_dev.registration_applications,hs2_dev.registration_photos,
                hs2_dev.price_snapshots,hs2_dev.tariff_versions,hs2_dev.classification_decisions,
                hs2_dev.stay_listings,hs2_dev.grant_units,hs2_dev.registration_grants,
                hs2_dev.inventory_members,hs2_dev.inventory_pools,hs2_dev.registered_buildings CASCADE""")
        self.app = create_fixture_app(False, populate=True)
        install(self.app)
        self.repo = self.app.fixture_supermap
        self.client = self.app.test_client()

    def test_public_api_rates_and_no_calendar_private_payload(self):
        response = self.client.get("/hs2/search/api/results")
        self.assertEqual(response.status_code, 200)
        for row in response.json["items"]:
            self.assertIsNotNone(row["base_rates"])
            self.assertEqual(set(row["base_rates"]),
                {"night"} if row["stay_kind"] == "lodging" else {"week", "month"})
            self.assertTrue(row["base_rate_notice"].startswith("기본 요금"))
        text = response.get_data(as_text=True)
        for token in ("application_id", '"daily"', '"periods"', '"blocked"', "candidate_id",
                      "context_id", "user_id", "NEVER_PUBLIC", "37.512345", "127.123456"):
            self.assertNotIn(token, text)

    def test_hidden_count_filters_price_permission_and_kind(self):
        short = dict(check_in="2027-01-01", check_out="2027-01-02")
        out = self.repo.search(parse(short))
        self.assertEqual(out["period_hidden_count"], 1)
        self.assertTrue(all(i["stay_kind"] == "lodging" for i in out["items"]))
        for extra in ({"q": "NO_MATCH"}, {"rooms": "30"}, {"bounds": "34,125,35,126"},
                      {"min_total": "0"}, {"kind": "lodging"}, {"kind": "non_lodging"}):
            self.assertEqual(self.repo.search(parse({**short, **extra}))["period_hidden_count"], 0)
        self.app.fixture_approved.remove((101, WHO["context_id"]))
        self.assertEqual(self.repo.search(parse(short))["period_hidden_count"], 0)

    def test_inventory_failure_not_minimum_period(self):
        self.app.fixture_calendar.inventory_is_available = lambda *_: False
        out = self.repo.search(parse(dict(check_in="2027-01-01", check_out="2027-01-02")))
        self.assertEqual(out["period_hidden_count"], 0)
        self.assertEqual(out["items"], [])

    def test_ten_days_only_engine_decomposition_gets_candidates(self):
        out = self.repo.search(parse(dict(kind="non_lodging", check_in="2027-01-01",
                                          check_out="2027-01-11")))
        row = out["items"][0]
        self.assertIsNone(row["quote"])
        self.assertEqual(row["quote_issue"], "EXACT_PERIOD_QUOTE_UNAVAILABLE")
        self.assertTrue(row["candidate_check_outs"])
        for end in row["candidate_check_outs"]:
            quote = self.app.fixture_calendar.quote(row["public_id"], "2027-01-01", end)
            self.assertTrue(quote["complete"])
        # A price filter cannot expose an unquoted listing.
        self.assertEqual(self.repo.search(parse(dict(kind="non_lodging", check_in="2027-01-01",
            check_out="2027-01-11", max_total="999999")))["items"], [])

    def test_month_and_month_plus_week_still_use_engine(self):
        for start, end in (("2027-01-31", "2027-02-28"),
                           ("2028-01-31", "2028-02-29"),
                           ("2027-01-31", "2027-03-07")):
            out = self.repo.search(parse(dict(kind="non_lodging", check_in=start, check_out=end)))
            row = out["items"][0]
            expected = self.app.fixture_calendar.quote(row["public_id"], start, end)
            self.assertEqual(row["quote"], expected)
            self.assertIsNone(row["quote_issue"])
            self.assertEqual(row["candidate_check_outs"], [])

    def test_stale_calendar_withholds_base_even_without_dates(self):
        application = next(r for r in self.app.fixture_repo.list(WHO)
                           if r["payload"]["stay_kind"] == "non_lodging")
        with connect_fixture() as conn, conn.cursor() as c:
            c.execute("""INSERT INTO hs2_dev.calendar_versions
                (id,application_id,version,source_revision,payload)
                SELECT gen_random_uuid(),application_id,version+1,source_revision+1,payload
                FROM hs2_dev.calendar_versions WHERE application_id=%s
                ORDER BY version DESC LIMIT 1""",
                      (application["id"],))
        out = self.repo.search(parse({}))
        row = next(r for r in out["items"] if r["public_id"] == application["public_id"])
        self.assertIsNone(row["base_rates"])
        self.assertIsNone(row["base_rate_notice"])
        short = self.repo.search(parse(dict(check_in="2027-01-01", check_out="2027-01-02")))
        self.assertEqual(short["period_hidden_count"], 0)

    def test_fresh_candidate_recheck_shows_real_failure(self):
        row = next(r for r in self.app.fixture_repo.list(WHO)
                   if r["payload"]["stay_kind"] == "non_lodging")
        params = dict(public_id=row["public_id"], check_in="2027-01-01", check_out="2027-01-08")
        self.assertTrue(self.client.get("/__development__/seongsu/quote-check", query_string=params).json["ok"])
        self.app.fixture_calendar.inventory_is_available = lambda *_: False
        result = self.client.get("/__development__/seongsu/quote-check", query_string=params)
        self.assertFalse(result.json["ok"])
        self.assertEqual(result.json["code"], "INVENTORY_UNAVAILABLE")
        self.assertNotIn("주·월", result.json["message"])


if __name__ == "__main__":
    unittest.main()
