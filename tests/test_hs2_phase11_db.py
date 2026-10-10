import unittest,time
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from uuid import uuid4
import test_hs2_phase10_db as booking_tests
from hs2_finance.fixtures import create_fixture_app
from hs2_finance.policy import ReviewedPolicy
from hs2_data.repository import connect_fixture
from hs2_details.fixtures import CONSUMER
from hs2_supermap.fixtures import WHO
from hs2_design.domain import ContractError


class FinanceSQL(unittest.TestCase):
    receipt=booking_tests.BookingSQL.receipt
    command=staticmethod(booking_tests.BookingSQL.command)
    request=booking_tests.BookingSQL.request

    @classmethod
    def setUpClass(cls):create_fixture_app()

    def setUp(self):
        booking_tests.BookingSQL.setUp(self)
        self.app=create_fixture_app(False,populate=False)
        self.repo=self.app.fixture_bookings;self.finance=self.app.fixture_finance;self.client=self.app.test_client()

    def contract(self,start="2027-01-01",end="2027-01-03"):
        booking=self.request(start=start,end=end)
        approved=self.repo.act(WHO,booking["booking_id"],1,"approve",operator=True)
        preview=self.finance.quote(CONSUMER,approved["booking_id"])
        return self.finance.create(CONSUMER,dict(booking_id=approved["booking_id"],request_id=str(uuid4()),acknowledged=True,
            expected_terms_sha256=preview["terms_sha256"]))

    def event(self,contract,**patches):
        return self.app.fixture_payment_provider.sign(dict(event_id=str(uuid4()),contract_id=contract["contract_id"],
            reference="owned-"+str(uuid4()),kind="capture",amount_krw=contract["terms"]["payable_krw"],
            currency="KRW",issued_at=int(time.time()),**patches))

    def paid(self):
        contract=self.contract();raw,sig=self.event(contract)
        return self.finance.receive(raw,sig)

    def test_provider_event_and_booking_confirm_are_atomic_exact_not_live(self):
        result=self.paid()
        self.assertEqual(result["status"],"captured");self.assertTrue(result["booking_confirmed"])
        self.assertTrue(result["sandbox"]);self.assertFalse(result["actual_money_executed"])
        self.assertEqual(result["terms"]["host_payout_krw"],200000)
        self.assertTrue(self.repo.list(CONSUMER)[0]["payment_verified"])

    def test_concurrent_webhook_retry_one_capture_and_single_confirmation(self):
        contract=self.contract();raw,sig=self.event(contract)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:self.finance.receive(raw,sig),range(2)))
        self.assertTrue(all(r["booking_confirmed"] for r in results))
        self.assertEqual(len(results[0]["events"]),1)
        self.assertEqual(self.repo.list(CONSUMER)[0]["revision"],3)
        changed=__import__("json").loads(raw);changed["issued_at"]+=1
        retry=self.app.fixture_payment_provider.sign(changed)
        self.assertTrue(self.finance.receive(*retry)["booking_confirmed"])

    def test_event_reference_replay_conflicting_body_and_underpayment_denied(self):
        contract=self.contract();raw,sig=self.event(contract)
        self.finance.receive(raw,sig)
        with self.assertRaisesRegex(ContractError,"PROVIDER_REFERENCE_REPLAY"):
            same=__import__("json").loads(raw);same["event_id"]=str(uuid4())
            raw2,sig2=self.app.fixture_payment_provider.sign(same);self.finance.receive(raw2,sig2)
        same["event_id"]=__import__("json").loads(raw)["event_id"];same["amount_krw"]=1
        raw2,sig2=self.app.fixture_payment_provider.sign(same)
        with self.assertRaisesRegex(ContractError,"PROVIDER_EVENT_REPLAY"):self.finance.receive(raw2,sig2)
        contract2=self.contract("2027-01-03","2027-01-05")
        changed=dict(__import__("json").loads(self.event(contract2)[0]),amount_krw=1)
        raw2,sig2=self.app.fixture_payment_provider.sign(changed)
        with self.assertRaisesRegex(ContractError,"PROVIDER_AMOUNT_MISMATCH"):self.finance.receive(raw2,sig2)

    def test_late_payment_kept_for_refund_review_never_revives_expired_inventory(self):
        contract=self.contract()
        with connect_fixture() as conn,conn.cursor() as c:
            c.execute("UPDATE hs2_dev.bookings SET deadline=clock_timestamp()-interval '1 minute' WHERE id=%s",(contract["booking_id"],))
        result=self.finance.receive(*self.event(contract))
        self.assertEqual(result["status"],"late_payment_review");self.assertFalse(result["booking_confirmed"])
        result=self.finance.cancel(CONSUMER,contract["contract_id"])
        self.assertEqual(result["refund_krw"],250000);self.assertFalse(result["actual_money_executed"])
        self.assertEqual(self.request(self.other)["status"],"pending_operator")

    def test_source_change_preserves_verified_money_without_wrong_confirmation(self):
        contract=self.contract();application=next(r for r in self.app.fixture_repo.list(WHO) if r["public_id"]==self.id)
        calendar=self.app.fixture_calendar.read(WHO,application["id"])
        self.app.fixture_calendar.update(WHO,application["id"],calendar["version"],application["revision"],
            dict(start="2027-01-01",end="2027-01-03",action="nightly",values={str(i):300000 for i in range(7)},inclusive=True))
        result=self.finance.receive(*self.event(contract))
        self.assertEqual(result["status"],"late_payment_review");self.assertFalse(result["booking_confirmed"])
        self.assertEqual(result["terms"]["stay_krw"],200000)

    def test_paid_cancellation_preserves_original_price_and_has_idempotent_refund_review(self):
        paid=self.paid()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:self.finance.cancel(CONSUMER,paid["contract_id"]),range(2)))
        self.assertTrue(all(r["booking_cancelled"] for r in results));self.assertEqual(len(results[0]["events"]),2)
        booking=self.repo.list(CONSUMER)[0]
        self.assertEqual(booking["status"],"cancelled_paid");self.assertFalse(booking["inventory_held"])
        self.assertEqual(booking["quote"]["total_krw"],200000)
        self.assertEqual(self.request(self.other)["status"],"pending_operator")

    def test_original_snapshot_and_financial_records_are_immutable(self):
        paid=self.paid()
        for sql in ("UPDATE hs2_dev.financial_contracts SET terms='{}'","DELETE FROM hs2_dev.financial_events",
                    "UPDATE hs2_dev.bookings SET check_out=check_out+1"):
            with self.assertRaises(Exception):
                with connect_fixture() as conn,conn.cursor() as c:c.execute(sql)

    def test_fee_policy_changes_do_not_change_committed_terms(self):
        paid=self.paid()
        self.app.fixture_financial_policy=ReviewedPolicy("new-reviewed",80000,platform_bps=700,reviewed=True,pg_processing_krw=0)
        result=self.finance.read(CONSUMER,paid["contract_id"])
        self.assertEqual(result["terms"],paid["terms"])
        self.assertEqual(self.finance.quote(CONSUMER,paid["booking_id"])["terms"],paid["terms"])

    def test_policy_changed_after_preview_requires_fresh_informed_ack(self):
        booking=self.request();self.repo.act(WHO,booking["booking_id"],1,"approve",operator=True)
        preview=self.finance.quote(CONSUMER,booking["booking_id"])
        self.app.fixture_financial_policy=ReviewedPolicy("new-reviewed",80000,reviewed=True,pg_processing_krw=0)
        with self.assertRaisesRegex(ContractError,"FINANCIAL_TERMS_CHANGED"):
            self.finance.create(CONSUMER,dict(booking_id=booking["booking_id"],request_id=str(uuid4()),
                acknowledged=True,expected_terms_sha256=preview["terms_sha256"]))

    def test_release_reviews_are_due_scoped_idempotent_and_deposit_not_host_revenue(self):
        paid=self.paid()
        self.assertEqual(len(self.finance.release_reviews(WHO,paid["contract_id"])["events"]),1)
        with patch.object(self.finance,"today",return_value=date(2027,1,11)):
            first=self.finance.release_reviews(WHO,paid["contract_id"]);second=self.finance.release_reviews(WHO,paid["contract_id"])
        self.assertEqual(len(first["events"]),len(second["events"]))
        amounts={e["kind"]:e["amount_krw"] for e in first["events"]}
        self.assertEqual(amounts["deposit_review"],50000);self.assertEqual(amounts["payout_review"],200000)
        with self.assertRaisesRegex(ContractError,"LIVE_SETTLEMENT_NOT_APPROVED"):self.finance.execute_live()

    def test_client_authority_missing_csrf_other_member_wrong_scope_and_live_gate(self):
        contract=self.contract()
        with self.assertRaises(ContractError):self.finance.read(self.other,contract["contract_id"])
        with self.assertRaises(ContractError):self.finance.release_reviews({**WHO,"user_id":102},contract["contract_id"])
        self.assertEqual(self.client.post("/hs2/finance/api/contracts",json={}).status_code,403)
        self.assertEqual(self.client.post("/hs2/finance/api/contracts",json=dict(booking_id=contract["booking_id"],
            request_id=str(uuid4()),acknowledged=True,paid=True),headers={"X-CSRF-Token":"isolated-consumer-csrf-not-real-session"}).status_code,400)
        self.finance.provider=None
        with self.assertRaisesRegex(ContractError,"LIVE_PAYMENT_NOT_APPROVED"):self.finance.receive(b"{}", "")

    def test_deadline_rechecked_after_trusted_proof_wait(self):
        contract=self.contract()
        with connect_fixture() as conn,conn.cursor() as c:
            c.execute("UPDATE hs2_dev.bookings SET deadline=clock_timestamp()+interval '0.4 second' WHERE id=%s",(contract["booking_id"],))
        self.repo.payment_terms_reviewed=lambda _:True
        def slow(key):
            time.sleep(0.6)
            return dict(verified=True,booking_id=key,paid_krw=200000,currency="KRW",reference="slow-owned-proof")
        self.repo.payment_proof=slow
        with self.assertRaisesRegex(ContractError,"BOOKING_DEADLINE_EXPIRED"):
            self.repo.act(CONSUMER,contract["booking_id"],2,"confirm-payment")
        self.assertFalse(self.repo.list(CONSUMER)[0]["payment_verified"])
