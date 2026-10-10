"""The sandbox signs owned synthetic evidence; it never calls a payment API."""
import hashlib,hmac,json,re,secrets,time
from hs2_design.domain import ContractError
from hs2_listings.validation import identifier
from .policy import money


class OwnedSandbox:
    sandbox=True

    def __init__(self):self._key=secrets.token_bytes(32)

    def sign(self,payload):
        raw=json.dumps(payload,sort_keys=True,separators=(",",":")).encode()
        return raw,hmac.new(self._key,raw,hashlib.sha256).hexdigest()

    def verify(self,raw,signature):
        if not isinstance(raw,bytes) or len(raw)>8192 or not isinstance(signature,str) or not signature.isascii():
            raise ContractError("PROVIDER_SIGNATURE_REQUIRED")
        expected=hmac.new(self._key,raw,hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected,signature):raise ContractError("PROVIDER_SIGNATURE_REQUIRED")
        def pairs(rows):
            result={}
            for k,v in rows:
                if k in result:raise ContractError("DUPLICATE_PROVIDER_FIELD")
                result[k]=v
            return result
        try:p=json.loads(raw,object_pairs_hook=pairs)
        except (ValueError,UnicodeError):raise ContractError("INVALID_PROVIDER_EVENT") from None
        if not isinstance(p,dict) or set(p)!={"event_id","contract_id","reference","kind","amount_krw","currency","issued_at"}:
            raise ContractError("INVALID_PROVIDER_EVENT")
        identifier(p["event_id"]);identifier(p["contract_id"]);money(p["amount_krw"],positive=True)
        if p["kind"]!="capture" or p["currency"]!="KRW" or not isinstance(p["reference"],str) or not re.fullmatch(r"[A-Za-z0-9._:-]{1,120}",p["reference"]):
            raise ContractError("INVALID_PROVIDER_EVENT")
        if type(p["issued_at"]) is not int or abs(time.time()-p["issued_at"])>300:
            raise ContractError("PROVIDER_EVENT_EXPIRED")
        return p
