import unittest
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
from datetime import date
from hs2_data.repository import connect_fixture
from hs2_details.fixtures import CONSUMER
from hs2_supermap.fixtures import WHO
from hs2_supermap.contracts import parse
from hs2_booking.fixtures import create_fixture_app
from hs2_design.domain import ContractError


class BookingSQL(unittest.TestCase):
    @classmethod
    def setUpClass(cls):create_fixture_app()

    def setUp(self):
        with connect_fixture() as conn,conn.cursor() as c:
            c.execute("""TRUNCATE hs2_dev.booking_events,hs2_dev.booking_slots,hs2_dev.bookings,
                hs2_dev.consumer_quote_receipts,hs2_dev.calendar_versions,
                hs2_dev.registration_events,hs2_dev.registration_applications,hs2_dev.registration_photos,
                hs2_dev.price_snapshots,hs2_dev.tariff_versions,hs2_dev.classification_decisions,
                hs2_dev.stay_listings,hs2_dev.grant_units,hs2_dev.registration_grants,
                hs2_dev.inventory_members,hs2_dev.inventory_pools,hs2_dev.registered_buildings CASCADE""")
            c.execute("""INSERT INTO hs2_fixture_legacy.users(id,active)
                VALUES(102,true) ON CONFLICT(id) DO UPDATE SET active=true""")
        self.app=create_fixture_app(False,populate=True);self.repo=self.app.fixture_bookings;self.client=self.app.test_client()
        self.id=next(r["public_id"] for r in self.app.fixture_supermap.search(parse({}))["items"] if r["stay_kind"]=="lodging")
        self.other={**CONSUMER,"user_id":102}

    def receipt(self,who=CONSUMER,start="2027-01-01",end="2027-01-03",public_id=None):
        key=public_id or self.id
        selection=dict(check_in=start,check_out=end,guests=2)
        q=self.app.fixture_details.quote(key,selection)["quote"]
        return self.app.fixture_details.confirm_quote(who,key,
            {**selection,"request_id":str(uuid4()),"acknowledged":True,"expected_source_version":q["source_version"]})

    @staticmethod
    def command(receipt):return dict(receipt_id=receipt["receipt_id"],request_id=str(uuid4()),acknowledged=True)

    def request(self,who=CONSUMER,start="2027-01-01",end="2027-01-03"):
        return self.repo.request(who,self.command(self.receipt(who,start,end)))

    def test_requested_and_operator_approved_are_not_paid_or_confirmed(self):
        booking=self.request()
        self.assertEqual(booking["status"],"pending_operator");self.assertTrue(booking["inventory_held"])
        self.assertFalse(booking["booking_confirmed"]);self.assertFalse(booking["payment_verified"])
        approved=self.repo.act(WHO,booking["booking_id"],booking["revision"],"approve",operator=True)
        self.assertEqual(approved["status"],"awaiting_payment")
        self.assertFalse(approved["booking_confirmed"])
        with self.assertRaisesRegex(ContractError,"PAYMENT_PROVIDER_UNAVAILABLE"):
            self.repo.act(CONSUMER,approved["booking_id"],approved["revision"],"confirm-payment")

    def test_two_consumers_same_space_concurrently_only_one_hold(self):
        receipts=[self.receipt(CONSUMER),self.receipt(self.other)]
        def run(pair):
            who,receipt=pair
            try:return self.repo.request(who,self.command(receipt))
            except ContractError as error:return str(error)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(run,zip((CONSUMER,self.other),receipts)))
        self.assertEqual(sum(isinstance(r,dict) for r in results),1)
        self.assertTrue(any(r in {"INVENTORY_UNAVAILABLE","BOOKING_INVENTORY_CONFLICT"} for r in results if isinstance(r,str)))
        with connect_fixture() as conn,conn.cursor() as c:
            c.execute("SELECT count(*) FROM hs2_dev.bookings");self.assertEqual(c.fetchone()[0],1)

    def test_same_request_retry_returns_exact_booking_no_extra_hold(self):
        command=self.command(self.receipt())
        with ThreadPoolExecutor(max_workers=2) as pool:
            rows=list(pool.map(lambda _:self.repo.request(CONSUMER,command),range(2)))
        self.assertEqual(rows[0]["booking_id"],rows[1]["booking_id"])
        with self.assertRaisesRegex(ContractError,"BOOKING_RETRY_CONFLICT"):
            self.repo.request(CONSUMER,{**command,"receipt_id":str(uuid4())})

    def test_half_open_checkout_next_checkin_allowed(self):
        first=self.request()
        second=self.request(self.other,"2027-01-03","2027-01-05")
        self.assertNotEqual(first["booking_id"],second["booking_id"])

    def test_consumer_cancel_and_operator_reject_restore_quote_inventory(self):
        first=self.request()
        cancelled=self.repo.act(CONSUMER,first["booking_id"],first["revision"],"cancel")
        self.assertEqual(cancelled["status"],"cancelled");self.assertFalse(cancelled["inventory_held"])
        other=self.request(self.other)
        rejected=self.repo.act(WHO,other["booking_id"],other["revision"],"reject",operator=True)
        self.assertEqual(rejected["status"],"rejected");self.assertFalse(rejected["inventory_held"])
        self.assertEqual(self.request()["status"],"pending_operator")

    def test_expired_hold_lazily_released_and_not_revived_by_retry(self):
        receipt=self.receipt();command=self.command(receipt);booking=self.repo.request(CONSUMER,command)
        with connect_fixture() as conn,conn.cursor() as c:
            c.execute("UPDATE hs2_dev.bookings SET deadline=clock_timestamp()-interval '1 minute' WHERE id=%s",(booking["booking_id"],))
        retried=self.repo.request(CONSUMER,command)
        self.assertEqual(retried["status"],"expired");self.assertFalse(retried["inventory_held"])
        with self.assertRaises(ContractError):self.repo.act(WHO,booking["booking_id"],retried["revision"],"approve",operator=True)
        self.assertEqual(self.request(self.other)["status"],"pending_operator")

    def test_other_member_operator_context_revocation_and_stale_action_denied(self):
        booking=self.request()
        with self.assertRaises(ContractError):self.repo.act(self.other,booking["booking_id"],1,"cancel")
        with self.assertRaises(ContractError):self.repo.act({**WHO,"user_id":102},booking["booking_id"],1,"approve",operator=True)
        with self.assertRaises(ContractError):self.repo.act(WHO,booking["booking_id"],2,"approve",operator=True)
        self.assertEqual(self.repo.list(self.other),[])

    def test_unconfirmed_source_change_requires_new_quote(self):
        booking=self.request();application=next(r for r in self.app.fixture_repo.list(WHO) if r["public_id"]==self.id)
        calendar=self.app.fixture_calendar.read(WHO,application["id"])
        self.app.fixture_calendar.update(WHO,application["id"],calendar["version"],application["revision"],
            dict(start="2027-01-01",end="2027-01-03",action="nightly",values={str(i):250000 for i in range(7)},inclusive=True))
        with self.assertRaisesRegex(ContractError,"QUOTE_SOURCE_CHANGED"):
            self.repo.act(WHO,booking["booking_id"],1,"approve",operator=True)
        self.assertEqual(self.repo.list(CONSUMER)[0]["quote"]["total_krw"],200000)

    def test_verified_fixture_proof_confirms_once_and_future_tariff_preserves_price(self):
        booking=self.request();approved=self.repo.act(WHO,booking["booking_id"],1,"approve",operator=True)
        self.repo.payment_terms_reviewed=lambda _:True
        self.repo.payment_proof=lambda key:dict(verified=True,booking_id=key,paid_krw=200000,currency="KRW",reference="owned-test-proof")
        confirmed=self.repo.act(CONSUMER,booking["booking_id"],approved["revision"],"confirm-payment")
        self.assertTrue(confirmed["booking_confirmed"]);self.assertTrue(confirmed["payment_verified"])
        self.assertEqual(self.repo.act(CONSUMER,booking["booking_id"],approved["revision"],"confirm-payment")["revision"],confirmed["revision"])
        application=next(r for r in self.app.fixture_repo.list(WHO) if r["public_id"]==self.id)
        current=self.app.fixture_calendar.read(WHO,application["id"])
        self.app.fixture_calendar.update(WHO,application["id"],current["version"],application["revision"],
            dict(start="2027-01-01",end="2027-01-03",action="nightly",values={str(i):250000 for i in range(7)},inclusive=True))
        self.assertEqual(self.repo.list(CONSUMER)[0]["quote"]["total_krw"],200000)

    def test_underpayment_currency_and_unreviewed_payment_terms_never_confirm(self):
        booking=self.request();approved=self.repo.act(WHO,booking["booking_id"],1,"approve",operator=True)
        self.repo.payment_terms_reviewed=lambda _:False
        self.repo.payment_proof=lambda key:dict(verified=True,booking_id=key,paid_krw=100,currency="KRW",reference="fixture")
        with self.assertRaisesRegex(ContractError,"PAYMENT_TERMS_REVIEW_REQUIRED"):
            self.repo.act(CONSUMER,booking["booking_id"],approved["revision"],"confirm-payment")
        self.repo.payment_terms_reviewed=lambda _:True
        with self.assertRaisesRegex(ContractError,"VERIFIED_PAYMENT_REQUIRED"):
            self.repo.act(CONSUMER,booking["booking_id"],approved["revision"],"confirm-payment")
        self.assertFalse(self.repo.list(CONSUMER)[0]["booking_confirmed"])

    def test_api_csrf_client_paid_identity_and_private_snapshot_metadata_rejected(self):
        command=self.command(self.receipt())
        self.assertEqual(self.client.post("/hs2/bookings/api/request",json=command).status_code,403)
        headers={"X-CSRF-Token":"isolated-consumer-csrf-not-real-session"}
        self.assertEqual(self.client.post("/hs2/bookings/api/request",json={**command,"paid":True},headers=headers).status_code,400)
        response=self.client.post("/hs2/bookings/api/request",json=command,headers=headers)
        self.assertEqual(response.status_code,200)
        for secret in ("user_id","application_id","snapshot_id","receipt_id","payment_reference","candidate_id"):
            self.assertNotIn(secret,response.get_data(as_text=True))
        self.assertEqual(self.client.get("/hs2/bookings/api/consumer?user_id=102").status_code,400)

    def test_parent_space_blocks_descendant_unit_not_unrelated_sibling(self):
        with connect_fixture() as conn,conn.cursor() as c:
            c.execute("""SELECT l.pool_id,p.registered_building_id FROM hs2_dev.stay_listings l
                JOIN hs2_dev.inventory_pools p ON p.id=l.pool_id
                JOIN hs2_dev.registration_applications a ON a.listing_id=l.id WHERE a.public_id=%s""",(self.id,))
            parent,building=c.fetchone();child,sibling=str(uuid4()),str(uuid4())
            for key in (child,sibling):
                c.execute("INSERT INTO hs2_dev.inventory_pools(id,registered_building_id,unit_key) VALUES(%s,%s,%s)",(key,building,"test-unit-"+key))
            c.execute("INSERT INTO hs2_dev.inventory_members VALUES(%s,%s,%s)",(building,parent,child))
        booking=self.request()
        self.assertFalse(self.repo.inventory_available(child,date(2027,1,1),date(2027,1,3)))
        self.assertTrue(self.repo.inventory_available(sibling,date(2027,1,1),date(2027,1,3)))
        with connect_fixture() as conn,conn.cursor() as c:
            c.execute("INSERT INTO hs2_dev.inventory_members VALUES(%s,%s,%s)",(building,parent,sibling))
        self.assertFalse(self.repo.inventory_available(sibling,date(2027,1,1),date(2027,1,3)))
        self.repo.act(CONSUMER,booking["booking_id"],booking["revision"],"cancel")
        self.assertTrue(self.repo.inventory_available(child,date(2027,1,1),date(2027,1,3)))

    def test_cycle_is_rejected_instead_of_infinite_or_unverified_inventory(self):
        # The original schema already rejects the cycle at write time. Preserve
        # that protection; do not disable its trigger merely to create bad data.
        with self.assertRaises(Exception):
            with connect_fixture() as conn,conn.cursor() as c:
                c.execute("""SELECT l.pool_id,p.registered_building_id FROM hs2_dev.stay_listings l
                    JOIN hs2_dev.inventory_pools p ON p.id=l.pool_id
                    JOIN hs2_dev.registration_applications a ON a.listing_id=l.id WHERE a.public_id=%s""",(self.id,))
                parent,building=c.fetchone();child=str(uuid4())
                c.execute("INSERT INTO hs2_dev.inventory_pools(id,registered_building_id,unit_key) VALUES(%s,%s,%s)",(child,building,"cycle-proof"))
                c.execute("INSERT INTO hs2_dev.inventory_members VALUES(%s,%s,%s),(%s,%s,%s)",(building,parent,child,building,child,parent))

    def test_active_request_cap_and_payment_reference_replay(self):
        for start,end in (("2027-01-01","2027-01-03"),("2027-01-03","2027-01-05"),("2027-01-05","2027-01-07")):
            self.request(start=start,end=end)
        with self.assertRaisesRegex(ContractError,"ACTIVE_BOOKING_LIMIT"):
            self.request(start="2027-01-07",end="2027-01-09")
        bookings=self.repo.list(CONSUMER)
        self.repo.payment_terms_reviewed=lambda _:True
        self.repo.payment_proof=lambda key:dict(verified=True,booking_id=key,paid_krw=200000,currency="KRW",reference="one-owned-financial-proof")
        first,second=bookings[:2]
        first=self.repo.act(WHO,first["booking_id"],first["revision"],"approve",operator=True)
        self.repo.act(CONSUMER,first["booking_id"],first["revision"],"confirm-payment")
        second=self.repo.act(WHO,second["booking_id"],second["revision"],"approve",operator=True)
        with self.assertRaisesRegex(ContractError,"PAYMENT_REFERENCE_REPLAY"):
            self.repo.act(CONSUMER,second["booking_id"],second["revision"],"confirm-payment")

    def test_different_approved_context_same_user_cannot_act_for_wrong_business(self):
        booking=self.request()
        wrong={**WHO,"context_id":WHO["context_id"]+"-different"}
        self.app.fixture_repo.context_is_active=lambda uid,ctx:uid==WHO["user_id"] and ctx in {WHO["context_id"],wrong["context_id"]}
        with self.assertRaises(ContractError):
            self.repo.act(wrong,booking["booking_id"],booking["revision"],"approve",operator=True)
