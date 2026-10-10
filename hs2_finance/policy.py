from dataclasses import dataclass,asdict
from hs2_design.domain import ContractError


def money(value,*,positive=False):
    if type(value) is not int or value<(1 if positive else 0) or value>10**11:
        raise ContractError("INTEGER_KRW_REQUIRED")
    return value


@dataclass(frozen=True)
class ReviewedPolicy:
    version:str
    deposit_krw:int
    platform_bps:int=0
    platform_vat_bps:int=1000
    deposit_return_days:int=7
    settlement_days:int=1
    reviewed:bool=False
    pg_processing_krw:int|None=None

    def terms(self,gross):
        money(gross,positive=True);money(self.deposit_krw)
        if self.reviewed is not True or not isinstance(self.version,str) or not self.version.strip() or len(self.version)>100:
            raise ContractError("REVIEWED_FINANCIAL_POLICY_REQUIRED")
        for value in (self.platform_bps,self.platform_vat_bps):
            if type(value) is not int or not 0<=value<=10000:raise ContractError("INVALID_FEE_POLICY")
        for value in (self.deposit_return_days,self.settlement_days):
            if type(value) is not int or not 1<=value<=90:raise ContractError("INVALID_RELEASE_POLICY")
        fee=gross*self.platform_bps//10000;vat=fee*self.platform_vat_bps//10000
        if fee+vat>gross:raise ContractError("INVALID_FEE_POLICY")
        if self.pg_processing_krw is None:raise ContractError("REVIEWED_PG_COST_REQUIRED")
        pg=money(self.pg_processing_krw)
        if fee+vat+pg>gross:raise ContractError("INVALID_FEE_POLICY")
        total=money(gross+self.deposit_krw,positive=True)
        return dict(policy=asdict(self),stay_krw=gross,deposit_krw=self.deposit_krw,
                    payable_krw=total,platform_fee_krw=fee,platform_vat_krw=vat,
                    pg_processing_krw=pg,host_payout_krw=gross-fee-vat-pg,currency="KRW")
