"""Real published-view reuse; no mocks of SQL success or legacy mutations."""
from datetime import date, timedelta
import unittest
import test_hs2_phase2_data as original
from hs2_consumer.repository import FixtureCatalog
from hs2_consumer.search import query, search


class ConsumerPublishedPostgreSQL(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        original.PostgreSQLDataContracts.setUpClass()

    def setUp(self):
        self.base = original.PostgreSQLDataContracts()
        self.base.setUp()
        self.conn = self.base.conn
        self.repo = self.base.graph()
        self.base.draft(self.repo)
        self.base.decision()
        self.repo.change_status(original.uid(5), "published", original.uid(6))
        self.base.sql("CREATE TABLE hs2_fixture_legacy.test_public_rates(day date PRIMARY KEY,krw bigint)")
        for i, price in enumerate((100000, 140000)):
            self.base.sql("INSERT INTO hs2_fixture_legacy.test_public_rates VALUES(%s,%s)",
                          (date(2026, 11, 1) + timedelta(days=i), price))
        self.values = query({"check_in": "2026-11-01", "check_out": "2026-11-03"})
        self.catalog = FixtureCatalog(self.conn, self.quote)

    def tearDown(self):
        self.base.tearDown()

    def quote(self, public_id, values):
        # Explicit synthetic tariff only; no tax/partial-period policy assumptions.
        days = (date.fromisoformat(values["check_out"]) - date.fromisoformat(values["check_in"])).days
        rows = self.base.sql("SELECT krw FROM hs2_fixture_legacy.test_public_rates WHERE day >= %s AND day < %s",
                             (values["check_in"], values["check_out"]), fetch=True)
        if len(rows) != days:
            return None
        return dict(check_in=values["check_in"], check_out=values["check_out"],
                    total_krw=sum(r[0] for r in rows), complete=True,
                    public_price_allowed=True, source_version="fixture-explicit-daily-v1")

    def test_actual_published_view_and_selected_total(self):
        data = search({**self.values, "min_total": 220000}, self.catalog)
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["items"][0]["quote"]["total_krw"], 240000)
        self.assertEqual(data["items"][0]["public_id"], original.uid(105))

    def test_withdrawn_and_draft_rows_never_public(self):
        self.repo.change_status(original.uid(5), "withdrawn")
        self.assertEqual(search(self.values, self.catalog)["count"], 0)

    def test_missing_day_never_partial_total_or_zero(self):
        self.base.sql("DELETE FROM hs2_fixture_legacy.test_public_rates WHERE day='2026-11-02'")
        data = search(self.values, self.catalog)
        self.assertIsNone(data["items"][0]["quote"])
        self.assertEqual(search({**self.values, "min_total": 0}, self.catalog)["count"], 0)

    def test_public_role_cannot_read_private_buildings(self):
        self.base.sql("SET LOCAL ROLE hs2_fixture_public")
        no_quote = FixtureCatalog(self.conn, lambda *_: None)
        result = search(query({}), no_quote)
        self.assertEqual(result["count"], 1)
        for key in ("road_address", "lat", "lng", "registered_building_id"):
            self.assertNotIn(key, result["items"][0])
        with self.base.rejected():
            self.base.sql("SELECT * FROM hs2_dev.registered_buildings")

    def test_read_only_source_does_not_create_membership_booking_or_snapshot(self):
        before = self.base.legacy_image()
        search(self.values, self.catalog)
        self.assertEqual(self.base.legacy_image(), before)
        self.assertEqual(self.base.sql("SELECT count(*) FROM hs2_dev.price_snapshots", fetch=True), [(0,)])
