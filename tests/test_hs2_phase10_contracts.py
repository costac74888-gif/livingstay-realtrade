import unittest
from hs2_booking.contracts import request_command,revision,proof
from hs2_design.domain import ContractError

DATA=dict(receipt_id="00000000-0000-4000-8000-000000000001",
          request_id="00000000-0000-4000-8000-000000000002",acknowledged=True)


class BookingContracts(unittest.TestCase):
    def test_request_rejects_client_identity_amount_status_and_implicit_ack(self):
        self.assertEqual(len(request_command(DATA)),64)
        for patch in (dict(user_id=101),dict(paid=True),dict(total_krw=0),dict(acknowledged=1),dict(receipt_id="x")):
            with self.assertRaises(ContractError):request_command({**DATA,**patch})

    def test_retry_payload_hash_and_revision_are_strict(self):
        self.assertEqual(request_command(DATA),request_command(dict(reversed(list(DATA.items())))))
        self.assertNotEqual(request_command(DATA),request_command({**DATA,"receipt_id":DATA["request_id"]}))
        for invalid in (True,0,-1,"1",None):
            with self.assertRaises(ContractError):revision(invalid)

    def test_trusted_payment_must_bind_booking_full_integer_total_currency_and_reference(self):
        good=dict(booking_id="booking",paid_krw=100000,currency="KRW",reference="fixture-reference",verified=True)
        self.assertEqual(proof(good,"booking",100000),"fixture-reference")
        for patch in (dict(verified=False),dict(booking_id="another"),dict(paid_krw=0),dict(paid_krw=True),dict(paid_krw="100000"),dict(currency="USD"),dict(reference="")):
            with self.assertRaises(ContractError):proof({**good,**patch},"booking",100000)
