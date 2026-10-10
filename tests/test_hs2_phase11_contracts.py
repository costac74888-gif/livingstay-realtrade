import json,time,unittest
from uuid import uuid4
from hs2_finance.adapter import OwnedSandbox
from hs2_finance.policy import ReviewedPolicy,money
from hs2_design.domain import ContractError


class FinancialContracts(unittest.TestCase):
    def test_gross_deposit_host_fee_vat_are_exact_separate_integers(self):
        terms=ReviewedPolicy("reviewed-owned",50000,platform_bps=500,reviewed=True,pg_processing_krw=0).terms(200000)
        self.assertEqual((terms["payable_krw"],terms["platform_fee_krw"],terms["platform_vat_krw"],terms["host_payout_krw"]),(250000,10000,1000,189000))
        self.assertEqual(terms["stay_krw"],terms["platform_fee_krw"]+terms["platform_vat_krw"]+terms["host_payout_krw"])

    def test_unreviewed_unknown_deposit_bool_float_negative_and_overflow_rejected(self):
        for value in (None,False,1.5,-1,10**12):
            with self.assertRaises(ContractError):money(value)
        with self.assertRaises(ContractError):ReviewedPolicy("draft",50000).terms(200000)
        with self.assertRaises(ContractError):ReviewedPolicy("owned",None,reviewed=True).terms(200000)

    def test_fee_cannot_exceed_stay_or_use_invalid_release_dates(self):
        for kwargs in (dict(platform_bps=10000),dict(platform_bps=True),dict(platform_vat_bps=-1),dict(deposit_return_days=0)):
            with self.assertRaises(ContractError):ReviewedPolicy("owned",0,reviewed=True,pg_processing_krw=0,**kwargs).terms(200000)

    def test_initial_platform_zero_and_unknown_pg_cost_are_distinct(self):
        with self.assertRaisesRegex(ContractError,"REVIEWED_PG_COST_REQUIRED"):
            ReviewedPolicy("initial",50000,reviewed=True).terms(200000)
        terms=ReviewedPolicy("initial",50000,reviewed=True,pg_processing_krw=3000).terms(200000)
        self.assertEqual(terms["platform_fee_krw"],0);self.assertEqual(terms["platform_vat_krw"],0)
        self.assertEqual(terms["pg_processing_krw"],3000);self.assertEqual(terms["host_payout_krw"],197000)

    def event(self):return dict(event_id=str(uuid4()),contract_id=str(uuid4()),reference="owned:test",kind="capture",amount_krw=250000,currency="KRW",issued_at=int(time.time()))

    def test_provider_signature_is_exact_and_owned_adapter_scoped(self):
        adapter=OwnedSandbox();raw,signature=adapter.sign(self.event())
        self.assertEqual(adapter.verify(raw,signature)["amount_krw"],250000)
        for data,sig in ((raw,b"wrong"),(raw+" ".encode(),signature),(raw,"0"*64)):
            with self.assertRaises(ContractError):adapter.verify(data,sig)
        with self.assertRaises(ContractError):OwnedSandbox().verify(raw,signature)

    def test_signed_stale_foreign_currency_paid_fields_and_nul_rejected(self):
        adapter=OwnedSandbox()
        for patch in (dict(issued_at=0),dict(currency="USD"),dict(amount_krw=True),dict(paid=True),dict(reference="bad\x00ref")):
            raw,sig=adapter.sign({**self.event(),**patch})
            with self.assertRaises(ContractError):adapter.verify(raw,sig)
