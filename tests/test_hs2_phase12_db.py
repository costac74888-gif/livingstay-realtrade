import unittest
from unittest.mock import patch
import test_hs2_phase11_db as finance_tests
from hs2_dashboard.fixtures import create_fixture_app
from hs2_dashboard.repository import DashboardRepository
from hs2_supermap.fixtures import WHO
from hs2_design.domain import ContractError
from hs2_data.repository import connect_fixture


class DashboardSQL(unittest.TestCase):
    receipt=finance_tests.FinanceSQL.receipt
    command=staticmethod(finance_tests.FinanceSQL.command)
    request=finance_tests.FinanceSQL.request
    contract=finance_tests.FinanceSQL.contract
    event=finance_tests.FinanceSQL.event
    paid=finance_tests.FinanceSQL.paid

    @classmethod
    def setUpClass(cls):create_fixture_app()

    def setUp(self):
        finance_tests.FinanceSQL.setUp(self)
        self.dashboard=DashboardRepository(self.finance)
        self.reg=self.finance.registrations

    def test_exact_active_cash_basis_not_approval_or_fake_settlement(self):
        self.request()
        d=self.dashboard.overview(WHO)
        self.assertEqual(d["counts"]["bookings_pending_operator"],1)
        self.assertEqual(d["finance"]["active_stay_krw"],0)
        self.assertFalse(d["finance"]["actual_money_executed"])
        self.assertEqual(d["applications"]["total"],len(self.reg.list(WHO)))
        self.assertEqual(d["counts"]["published_rooms"],2)

    def test_signed_capture_then_paid_cancel_preserves_evidence_not_active_income(self):
        paid=self.paid();d=self.dashboard.overview(WHO)
        self.assertEqual(d["counts"]["bookings_confirmed_active"],1)
        self.assertEqual(d["finance"]["sandbox_capture_krw"],250000)
        self.assertEqual(d["finance"]["live_capture_krw"],0)
        self.assertEqual(d["finance"]["active_stay_krw"],200000)
        self.assertEqual(d["finance"]["deposit_liability_krw"],50000)
        self.assertEqual(d["finance"]["host_payout_review_basis_krw"],200000)
        from hs2_details.fixtures import CONSUMER
        self.finance.cancel(CONSUMER,paid["contract_id"]);d=self.dashboard.overview(WHO)
        self.assertEqual(d["counts"]["bookings_confirmed_active"],0)
        self.assertEqual(d["counts"]["bookings_cancelled_paid"],1)
        self.assertEqual(d["bookings"]["items"][0]["status"],"cancelled_paid")
        self.assertEqual(d["finance"]["sandbox_capture_krw"],250000)
        self.assertEqual(d["finance"]["refund_review_krw"],250000)
        self.assertEqual(d["finance"]["active_stay_krw"],0)
        self.assertEqual(d["finance"]["host_payout_review_basis_krw"],0)

    def test_late_capture_does_not_become_income(self):
        contract=self.contract()
        with connect_fixture() as conn,conn.cursor() as c:
            c.execute("UPDATE hs2_dev.bookings SET deadline=clock_timestamp()-interval '1 second' WHERE id=%s",(contract["booking_id"],))
        raw,sig=self.event(contract);self.finance.receive(raw,sig)
        d=self.dashboard.overview(WHO)
        self.assertEqual(d["finance"]["sandbox_capture_krw"],250000)
        self.assertEqual(d["finance"]["active_stay_krw"],0)
        self.assertEqual(d["counts"]["bookings_confirmed_active"],0)
        self.assertEqual(d["bookings"]["items"][0]["status"],"expired")

    def test_context_member_and_fresh_approval_are_required(self):
        self.paid()
        with self.assertRaises(ContractError):self.dashboard.overview({**WHO,"user_id":102})
        with patch.object(self.reg,"context_is_active",return_value=False):
            with self.assertRaisesRegex(ContractError,"APPROVED_BUSINESS_REQUIRED"):self.dashboard.overview(WHO)
        with connect_fixture() as conn,conn.cursor() as c:c.execute("UPDATE hs2_fixture_legacy.users SET active=FALSE WHERE id=101")
        try:
            with self.assertRaisesRegex(ContractError,"ACTIVE_MEMBER_REQUIRED"):self.dashboard.overview(WHO)
        finally:
            with connect_fixture() as conn,conn.cursor() as c:c.execute("UPDATE hs2_fixture_legacy.users SET active=TRUE WHERE id=101")

    def test_empty_approved_context_not_other_business(self):
        self.paid()
        # An independently trusted approved context may have no records.
        with patch.object(self.reg,"context_is_active",return_value=True):
            d=self.dashboard.overview({**WHO,"context_id":"operator:owned-empty"})
        self.assertEqual(d["counts"]["registrations_all"],0)
        self.assertEqual(d["finance"]["sandbox_capture_krw"],0)
        self.assertEqual(d["applications"]["items"],[])
        self.assertEqual(d["bookings"]["items"],[])
        self.assertEqual(d["contracts"]["items"],[])

    def test_dashboard_route_rejects_client_scope_and_is_no_store(self):
        from hs2_dashboard.api import create_blueprint
        self.app.fixture_dashboard=self.dashboard
        self.app.register_blueprint(create_blueprint(self.dashboard,current_operator=lambda:self.app.fixture_booking_operator,allow_request=lambda:True))
        client=self.app.test_client()
        self.assertEqual(client.get("/hs2/dashboard/api/overview?user_id=102").status_code,403)
        response=client.get("/hs2/dashboard/api/overview")
        self.assertEqual(response.status_code,200);self.assertEqual(response.headers["Cache-Control"],"no-store")
        self.app.fixture_booking_operator=None
        self.assertFalse(client.get("/hs2/dashboard/api/session").get_json()["can_operator"])
        self.assertEqual(client.get("/hs2/dashboard/api/overview").status_code,403)

    def test_exact_full_totals_are_not_recent_list_length(self):
        source=self.reg.list(WHO)[0]
        for _ in range(21):self.reg.create(WHO,source["candidate_id"],source["payload"])
        d=self.dashboard.overview(WHO)
        self.assertEqual(d["applications"]["total"],23)
        self.assertEqual(d["counts"]["registrations_all"],23)
        self.assertEqual(len(d["applications"]["items"]),20)
        self.assertTrue(d["applications"]["has_more"])
        self.assertEqual(d["counts"]["published_rooms"],2)


if __name__=="__main__":unittest.main()
