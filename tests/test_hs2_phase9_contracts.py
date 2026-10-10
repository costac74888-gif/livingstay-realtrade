import unittest
from hs2_details.contracts import selection,command,consumer,request_hash
from hs2_design.domain import ContractError

DATA=dict(check_in="2027-01-01",check_out="2027-01-03",guests=2,
    expected_source_version="a"*64,acknowledged=True,request_id="00000000-0000-4000-8000-000000000001")


class DetailContracts(unittest.TestCase):
    def test_strict_positive_guest_dates_no_unknown_or_client_authority(self):
        self.assertEqual(selection(dict(check_in=DATA["check_in"],check_out=DATA["check_out"],guests="2"))["guests"],2)
        for patch in (dict(guests=True),dict(guests=[]),dict(guests="101"),dict(guests="0"),dict(check_in=None),dict(check_out="2027-01-01"),dict(role="consumer")):
            raw=dict(check_in=DATA["check_in"],check_out=DATA["check_out"],guests=2,**{})
            raw.update(patch)
            with self.assertRaises(ContractError):selection(raw)

    def test_confirmation_ack_source_id_and_integer_required(self):
        self.assertEqual(command(DATA),DATA)
        for patch in (dict(acknowledged=False),dict(guests="2"),dict(expected_source_version="private-id"),dict(request_id="x"),dict(booking_confirmed=True)):
            with self.assertRaises(ContractError):command({**DATA,**patch})

    def test_verified_consumer_only_never_operator_or_client_context(self):
        who=dict(user_id=101,context_id="consumer",role="consumer",email_verified=True)
        self.assertEqual(consumer(who),101)
        for patch in (dict(user_id=True),dict(role="operator"),dict(context_id="operator:101"),dict(email_verified=False)):
            with self.assertRaises(ContractError):consumer({**who,**patch})

    def test_retry_digest_binds_public_id_dates_guests_terms_and_ack(self):
        self.assertEqual(request_hash("public",DATA),request_hash("public",dict(reversed(list(DATA.items())))))
        self.assertNotEqual(request_hash("public",DATA),request_hash("other",DATA))
        self.assertNotEqual(request_hash("public",DATA),request_hash("public",{**DATA,"guests":1}))
