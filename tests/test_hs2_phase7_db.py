import unittest
from datetime import date
from hs2_data.repository import connect_fixture
from hs2_design.domain import ContractError
from hs2_listings.fixtures import seed
from hs2_calendar.fixtures import create_fixture_app
from hs2_calendar.repository import migrate
from hs2_calendar.api import create_blueprint
from hs2_consumer.search import query, search
from flask import Flask

WHO = dict(user_id=101, context_id="operator:fixture:101", role="operator")
OTHER = dict(user_id=102, context_id="operator:fixture:102", role="operator")
CMD = dict(start="2027-01-01", end="2027-01-08", action="nightly",
           values={str(i): 150000 for i in range(7)}, inclusive=True)


class PersistentCalendar(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        seed()
        with connect_fixture() as conn:
            migrate(conn)

    def setUp(self):
        with connect_fixture() as conn, conn.cursor() as c:
            c.execute("""TRUNCATE hs2_dev.calendar_versions,hs2_dev.registration_events,
                hs2_dev.registration_applications,hs2_dev.registration_photos,
                hs2_dev.price_snapshots,hs2_dev.tariff_versions,hs2_dev.classification_decisions,
                hs2_dev.stay_listings,hs2_dev.grant_units,hs2_dev.registration_grants,
                hs2_dev.inventory_members,hs2_dev.inventory_pools,hs2_dev.registered_buildings CASCADE;
                UPDATE hs2_fixture_legacy.users SET active=true""")
        self.app = create_fixture_app(False, populate=True)
        self.repo = self.app.fixture_calendar
        self.client = self.app.test_client()
        rows = self.app.fixture_repo.list(WHO)
        self.lodging = next(r for r in rows if r["payload"]["stay_kind"] == "lodging")
        self.non = next(r for r in rows if r["payload"]["stay_kind"] == "non_lodging")
        self.headers = {"X-HS2-CSRF": "synthetic-csrf-only"}

    def enable(self, application=None, command=None):
        application = application or self.lodging
        return self.repo.update(WHO, application["id"], 0, 1, command or CMD)

    def test_persistent_bulk_and_override_new_connection(self):
        self.enable()
        self.repo.update(WHO, self.lodging["id"], 1, 1,
            {**CMD, "end": "2027-01-02", "values": {"4": 250000}})
        fresh = create_fixture_app(False).fixture_calendar
        row = fresh.read(WHO, self.lodging["id"])
        self.assertEqual(row["version"], 2)
        self.assertEqual(row["calendar"]["daily"]["2027-01-01"], 250000)
        self.assertEqual(fresh.quote(self.lodging["public_id"], "2027-01-01", "2027-01-03")["total_krw"], 400000)

    def test_inclusive_ack_and_missing_price_version_not_zero_quote(self):
        with self.assertRaises(ContractError):
            self.repo.quote(self.lodging["public_id"], "2027-01-01", "2027-01-02")
        with self.assertRaises(ContractError):
            self.enable(command={**CMD, "inclusive": False})
        self.assertEqual(self.repo.read(WHO, self.lodging["id"])["version"], 0)

    def test_scope_source_and_calendar_revision_fences(self):
        for other in (OTHER, {**WHO, "context_id": "operator:fixture:other"}):
            with self.assertRaises(ContractError):
                self.repo.read(other, self.lodging["id"])
            with self.assertRaises(ContractError):
                self.repo.update(other, self.lodging["id"], 0, 1, CMD)
        self.enable()
        for calendar_revision, source_revision in ((0, 1), (1, 2), (True, 1)):
            with self.assertRaises(ContractError):
                self.repo.update(WHO, self.lodging["id"], calendar_revision, source_revision, CMD)

    def test_closed_open_range_checkout_exclusive_and_inventory_callback(self):
        self.enable()
        command = dict(start="2027-01-03", end="2027-01-04", action="close", values={}, inclusive=True)
        self.repo.update(WHO, self.lodging["id"], 1, 1, command)
        self.assertEqual(self.repo.quote(self.lodging["public_id"], "2027-01-01", "2027-01-03")["total_krw"], 300000)
        with self.assertRaises(ContractError):
            self.repo.quote(self.lodging["public_id"], "2027-01-01", "2027-01-04")
        self.repo.update(WHO, self.lodging["id"], 2, 1, {**command, "action": "open"})
        self.assertEqual(self.repo.quote(self.lodging["public_id"], "2027-01-01", "2027-01-04")["total_krw"], 450000)
        self.repo.inventory_is_available = lambda *_: False
        with self.assertRaises(ContractError):
            self.repo.quote(self.lodging["public_id"], "2027-01-01", "2027-01-04")

    def test_week_month_updates_and_exact_month_end_quote(self):
        cmd = dict(start="2027-01-01", end="2027-04-01", action="periods",
                   values={"weekly": 320000, "monthly": 1100000}, inclusive=True)
        self.enable(self.non, cmd)
        s = self.repo.quote(self.non["public_id"], "2027-01-31", "2027-03-31")
        self.assertEqual(s["total_krw"], 2200000)
        self.assertEqual([r["unit"] for r in s["lines"]], ["month", "month"])
        with self.assertRaises(ContractError):
            self.repo.quote(self.non["public_id"], "2027-01-01", "2027-01-09")

    def test_original_fk_snapshot_append_only_and_later_rate_changes(self):
        self.enable()
        frozen = self.repo.freeze_fixture(WHO, self.lodging["id"], "2027-01-01", "2027-01-03")
        self.assertEqual(frozen["total_krw"], 300000)
        self.assertFalse(frozen["booking_confirmed"])
        self.repo.update(WHO, self.lodging["id"], 1, 1, {**CMD, "values": {"4": 280000, "5": 280000}})
        self.assertEqual(self.repo.quote(self.lodging["public_id"], "2027-01-01", "2027-01-03")["total_krw"], 560000)
        with connect_fixture() as conn, conn.cursor() as c:
            c.execute("SELECT total_krw,payload FROM hs2_dev.price_snapshots WHERE id=%s", (frozen["snapshot_id"],))
            amount, payload = c.fetchone()
            self.assertEqual(amount, 300000)
            self.assertEqual(payload["total_krw"], 300000)
            with self.assertRaises(Exception):
                c.execute("UPDATE hs2_dev.price_snapshots SET total_krw=1 WHERE id=%s", (frozen["snapshot_id"],))

    def test_calendar_versions_database_immutable_and_private_role(self):
        self.enable()
        for sql in ("UPDATE hs2_dev.calendar_versions SET source_revision=9",
                    "DELETE FROM hs2_dev.calendar_versions"):
            with connect_fixture() as conn, conn.cursor() as c:
                with self.assertRaises(Exception):
                    c.execute(sql)
        with connect_fixture() as conn, conn.cursor() as c:
            c.execute("SET LOCAL ROLE hs2_fixture_public")
            with self.assertRaises(Exception):
                c.execute("SELECT * FROM hs2_dev.calendar_versions")

    def test_original_revision_change_unpublishes_and_prices_mark_stale(self):
        self.enable()
        self.app.fixture_repo.change(WHO, self.lodging["id"], 1, "save", self.lodging["payload"])
        self.assertTrue(self.repo.read(WHO, self.lodging["id"])["stale"])
        with self.assertRaises(ContractError):
            self.repo.quote(self.lodging["public_id"], "2027-01-01", "2027-01-03")
        with self.assertRaises(ContractError):
            self.repo.update(WHO, self.lodging["id"], 1, 1, CMD)
        self.assertEqual(self.repo.update(WHO, self.lodging["id"], 1, 2, CMD)["version"], 2)

    def test_withdrawal_expiry_and_context_revocation_no_stale_quote_or_freeze(self):
        self.enable()
        self.app.fixture_approved.remove((101, WHO["context_id"]))
        with self.assertRaises(ContractError):
            self.repo.quote(self.lodging["public_id"], "2027-01-01", "2027-01-03")
        self.app.fixture_approved.add((101, WHO["context_id"]))
        with connect_fixture() as conn, conn.cursor() as c:
            c.execute("UPDATE hs2_dev.registration_applications SET approved_until=clock_timestamp()-interval '1 day' WHERE id=%s", (self.lodging["id"],))
        with self.assertRaises(ContractError):
            self.repo.freeze_fixture(WHO, self.lodging["id"], "2027-01-01", "2027-01-03")

    def test_http_csrf_authority_and_public_quote_only_safe_fields(self):
        key = self.lodging["id"]
        body = dict(version=0, source_revision=1, command=CMD)
        url = "/hs2/calendar/applications/" + key + "/prices"
        self.assertEqual(self.client.post(url, json=body).status_code, 403)
        self.assertEqual(self.client.post(url, json={**body, "user_id": 102}, headers=self.headers).status_code, 409)
        self.assertEqual(self.client.post(url, json=body, headers=self.headers).status_code, 200)
        response = self.client.get("/hs2/calendar/quote", query_string=dict(
            public_id=self.lodging["public_id"], check_in="2027-01-01", check_out="2027-01-03"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["quote"]["total_krw"], 300000)
        self.assertNotIn(key, response.get_data(as_text=True))
        self.assertNotIn("PRIVATE_FIXTURE_ADDRESS", response.get_data(as_text=True))
        self.assertFalse(response.get_json()["quote"]["booking_confirmed"])

    def test_public_quote_budget_anonymous_and_no_owner_api_bypass(self):
        app = Flask("anonymous_calendar")
        app.register_blueprint(create_blueprint(self.repo, resolve_context=lambda: None,
            csrf_token=lambda: "", check_csrf=lambda: False, allow_quote_request=lambda: False))
        self.assertEqual(app.test_client().get("/hs2/calendar/quote").status_code, 429)
        self.assertEqual(app.test_client().get("/hs2/calendar/meta").status_code, 401)

    def test_migration_receipts_no_legacy_change_and_future_clock(self):
        with connect_fixture() as conn, conn.cursor() as c:
            migrate(conn)
            c.execute("SELECT version FROM hs2_dev.migration_receipts ORDER BY version")
            self.assertEqual(c.fetchall(), [(1,), (6,), (7,)])
            c.execute("SELECT count(*) FROM hs2_fixture_legacy.master_buildings")
            self.assertEqual(c.fetchone()[0], 0)
        with self.assertRaises(ContractError):
            self.enable(command={**CMD, "start": "2026-10-10"})
        self.repo.today = lambda: None
        with self.assertRaises(ContractError):
            self.repo.read(WHO, self.lodging["id"])

    def test_public_period_total_adapter_does_not_fill_unquoted_missing_prices(self):
        self.enable()
        values = query(dict(check_in="2027-01-01", check_out="2027-01-03"))
        rows = self.repo.consumer_rows(values)
        self.assertEqual(len(rows), 2)
        self.assertIsNone(next(r for r in rows if r["stay_kind"] == "non_lodging")["quote"])
        priced = next(r for r in rows if r["stay_kind"] == "lodging")
        self.assertEqual(priced["quote"]["total_krw"], 300000)
        filtered = search(query(dict(check_in="2027-01-01", check_out="2027-01-03",
                                     min_total="300000", max_total="300000")), self.repo.consumer_rows)
        self.assertEqual(len(filtered["items"]), 1)
        self.assertEqual(filtered["items"][0]["public_id"], self.lodging["public_id"])
