import unittest
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from hs2_data.repository import connect_fixture
from hs2_design.domain import ContractError
from hs2_details.fixtures import create_fixture_app,CONSUMER
from hs2_supermap.contracts import parse
from hs2_supermap.fixtures import WHO


class DetailSQL(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        create_fixture_app()

    def setUp(self):
        with connect_fixture() as conn,conn.cursor() as c:
            c.execute("""TRUNCATE hs2_dev.consumer_quote_receipts,hs2_dev.calendar_versions,
                hs2_dev.registration_events,hs2_dev.registration_applications,hs2_dev.registration_photos,
                hs2_dev.price_snapshots,hs2_dev.tariff_versions,hs2_dev.classification_decisions,
                hs2_dev.stay_listings,hs2_dev.grant_units,hs2_dev.registration_grants,
                hs2_dev.inventory_members,hs2_dev.inventory_pools,hs2_dev.registered_buildings CASCADE""")
        self.app=create_fixture_app(False,populate=True)
        self.repo=self.app.fixture_details;self.client=self.app.test_client()
        self.id=next(r["public_id"] for r in self.app.fixture_supermap.search(parse({}))["items"] if r["stay_kind"]=="lodging")
        self.selection=dict(check_in="2027-01-01",check_out="2027-01-03",guests=2)
        self.q=self.repo.quote(self.id,self.selection)["quote"]
        self.command={**self.selection,"request_id":str(uuid4()),"expected_source_version":self.q["source_version"],"acknowledged":True}

    def test_detail_matches_search_privacy_and_real_selected_price(self):
        detail=self.repo.detail(self.id)
        self.assertEqual(detail["item"]["summary"]["rooms"],0)
        self.assertEqual(detail["photos"],[])
        self.assertEqual(detail["deposit_status"],"not_configured")
        self.assertEqual(self.q["total_krw"],200000)
        self.assertEqual(sum(r["amount_krw"] for r in self.q["lines"]),200000)
        self.assertFalse(self.q["booking_confirmed"])
        for secret in ("NEVER_PUBLIC","candidate_id","space_label","master_building_id"):
            self.assertNotIn(secret,str(detail))

    def test_original_immutable_fk_snapshot_and_consumer_receipt_not_booking(self):
        receipt=self.repo.confirm_quote(CONSUMER,self.id,self.command)
        self.assertFalse(receipt["booking_confirmed"]);self.assertFalse(receipt["inventory_held"])
        self.assertEqual(self.repo.read_receipt(CONSUMER,receipt["receipt_id"])["quote"]["total_krw"],200000)
        with connect_fixture() as conn,conn.cursor() as c:
            c.execute("SELECT count(*) FROM hs2_dev.price_snapshots s JOIN hs2_dev.consumer_quote_receipts q ON q.snapshot_id=s.id")
            self.assertEqual(c.fetchone()[0],1)
        with self.assertRaises(Exception):
            with connect_fixture() as conn,conn.cursor() as c:
                c.execute("UPDATE hs2_dev.consumer_quote_receipts SET guests=1")

    def test_retry_and_concurrent_identical_command_exactly_one_receipt(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            receipts=list(pool.map(lambda _:self.repo.confirm_quote(CONSUMER,self.id,self.command),range(2)))
        self.assertEqual(receipts[0]["receipt_id"],receipts[1]["receipt_id"])
        with connect_fixture() as conn,conn.cursor() as c:
            c.execute("SELECT count(*) FROM hs2_dev.consumer_quote_receipts");self.assertEqual(c.fetchone()[0],1)
            c.execute("SELECT count(*) FROM hs2_dev.price_snapshots");self.assertEqual(c.fetchone()[0],1)
        with self.assertRaises(ContractError):
            self.repo.confirm_quote(CONSUMER,self.id,{**self.command,"guests":1})

    def test_other_member_cannot_read_own_or_missing_receipt(self):
        receipt=self.repo.confirm_quote(CONSUMER,self.id,self.command)
        with self.assertRaises(ContractError):self.repo.read_receipt({**CONSUMER,"user_id":102},receipt["receipt_id"])
        with self.assertRaises(ContractError):self.repo.read_receipt(CONSUMER,str(uuid4()))
        with self.assertRaises(ContractError):self.repo.confirm_quote({**CONSUMER,"role":"operator"},self.id,self.command)

    def test_new_calendar_version_invalidates_receipt_but_not_snapshot(self):
        receipt=self.repo.confirm_quote(CONSUMER,self.id,self.command)
        application=next(r for r in self.app.fixture_repo.list(WHO) if r["public_id"]==self.id)
        current=self.app.fixture_calendar.read(WHO,application["id"])
        self.app.fixture_calendar.update(WHO,application["id"],current["version"],application["revision"],
            dict(start="2027-01-01",end="2027-01-03",action="nightly",values={"0":250000,"1":250000,"2":250000,"3":250000,"4":250000,"5":250000,"6":250000},inclusive=True))
        with self.assertRaises(ContractError):self.repo.read_receipt(CONSUMER,receipt["receipt_id"])
        with self.assertRaises(ContractError):self.repo.confirm_quote(CONSUMER,self.id,self.command)
        with connect_fixture() as conn,conn.cursor() as c:
            c.execute("SELECT public_quote->>'total_krw' FROM hs2_dev.consumer_quote_receipts")
            self.assertEqual(c.fetchone()[0],"200000")

    def test_withdrawn_revoked_and_inventory_unavailable_no_receipt(self):
        self.app.fixture_calendar.inventory_is_available=lambda *_:False
        with self.assertRaises(ContractError):self.repo.confirm_quote(CONSUMER,self.id,self.command)
        self.app.fixture_calendar.inventory_is_available=lambda *_:True
        row=next(r for r in self.app.fixture_repo.list(WHO) if r["public_id"]==self.id)
        self.app.fixture_repo.change(WHO,row["id"],row["revision"],"withdraw")
        with self.assertRaises(ContractError):self.repo.quote(self.id,self.selection)
        with connect_fixture() as conn,conn.cursor() as c:
            c.execute("SELECT count(*) FROM hs2_dev.consumer_quote_receipts");self.assertEqual(c.fetchone()[0],0)

    def test_capacity_unknown_and_over_capacity_dont_reveal_private_summary(self):
        with self.assertRaises(ContractError):self.repo.quote(self.id,{**self.selection,"guests":3})
        application=next(r for r in self.app.fixture_repo.list(WHO) if r["public_id"]==self.id)
        from hs2_details.repository import DetailRepository
        for count in (1,100):
            with self.assertRaisesRegex(ContractError,"PUBLIC_CAPACITY_REQUIRED"):
                DetailRepository.guests({**application,"payload":{**application["payload"],"public_summary":False}},count)

    def test_source_expected_ack_guest_and_body_csrf_are_server_enforced(self):
        path=f"/hs2/details/api/items/{self.id}/confirm-quote"
        self.assertEqual(self.client.post(path,json=self.command).status_code,403)
        headers={"X-CSRF-Token":"isolated-consumer-csrf-not-real-session"}
        for patch in (dict(acknowledged=False),dict(expected_source_version="a"*64),dict(guests=3),dict(role="consumer")):
            self.assertIn(self.client.post(path,json={**self.command,**patch},headers=headers).status_code,{400,409})
        self.assertEqual(self.client.post(path,json=self.command,headers=headers).status_code,200)
        self.app.fixture_consumer=None
        self.assertEqual(self.client.post(path,json=self.command,headers=headers).status_code,403)

    def test_non_lodging_week_month_minimum_and_exact_composition(self):
        key=next(r["public_id"] for r in self.app.fixture_supermap.search(parse({}))["items"] if r["stay_kind"]=="non_lodging")
        self.assertEqual(self.repo.quote(key,dict(check_in="2027-01-01",check_out="2027-01-15",guests=2))["quote"]["total_krw"],600000)
        self.assertEqual(self.repo.quote(key,dict(check_in="2027-01-31",check_out="2027-02-28",guests=2))["quote"]["total_krw"],1000000)
        with self.assertRaises(ContractError):self.repo.quote(key,self.selection)
        with self.assertRaises(ContractError):self.repo.quote(key,dict(check_in="2027-01-01",check_out="2027-01-09",guests=2))

    def test_api_receipts_do_not_expose_internal_snapshot_or_classification_ids(self):
        path=f"/hs2/details/api/items/{self.id}/confirm-quote"
        result=self.client.post(path,json=self.command,headers={"X-CSRF-Token":"isolated-consumer-csrf-not-real-session"})
        self.assertEqual(result.status_code,200)
        text=result.get_data(as_text=True)
        for secret in ("snapshot_id","listing_id","candidate_id","user_id","context_id","classification_evidence","tariff_version"):
            self.assertNotIn(secret,text)
        key=result.get_json()["receipt"]["receipt_id"]
        self.assertEqual(self.client.get(f"/hs2/details/api/receipts/{key}").status_code,200)

    def test_expired_immutable_receipt_cannot_be_read_or_confirmed(self):
        receipt=self.repo.confirm_quote(CONSUMER,self.id,self.command)
        expired=str(uuid4())
        with connect_fixture() as conn,conn.cursor() as c:
            snap=str(uuid4())
            c.execute("""INSERT INTO hs2_dev.price_snapshots
                SELECT %s,listing_id,check_in,check_out,kind,currency,tariff_version,terms_version,
                classification_evidence,classification_version,total_krw,payload
                FROM hs2_dev.price_snapshots LIMIT 1""",(snap,))
            c.execute("""INSERT INTO hs2_dev.consumer_quote_receipts
                SELECT %s,user_id,public_id,%s,%s,request_hash,source_version,application_revision,guests,
                public_quote,clock_timestamp()-interval '20 minutes',clock_timestamp()-interval '10 minutes'
                FROM hs2_dev.consumer_quote_receipts WHERE id=%s""",(expired,snap,str(uuid4()),receipt["receipt_id"]))
        with self.assertRaisesRegex(ContractError,"QUOTE_RECEIPT_EXPIRED"):self.repo.read_receipt(CONSUMER,expired)

    def test_duplicate_json_unknown_filters_and_malformed_guest_never_server_error(self):
        path=f"/hs2/details/api/items/{self.id}/confirm-quote"
        response=self.client.post(path,data='{"guests":1,"guests":2}',content_type="application/json",
            headers={"X-CSRF-Token":"isolated-consumer-csrf-not-real-session"})
        self.assertEqual(response.status_code,400)
        self.assertEqual(response.get_json()["code"],"DUPLICATE_BODY_FIELD")
        for guest in ([],{},None,True):
            with self.assertRaises(ContractError):self.repo.quote(self.id,{**self.selection,"guests":guest})
        self.assertEqual(self.client.get(f"/hs2/details/api/items/{self.id}/quote?check_in=2027-01-01&check_out=2027-01-03&guests=2&role=consumer").status_code,400)
