from hs2_details.contracts import consumer
from hs2_listings.validation import identifier
from hs2_design.domain import ContractError
import hashlib,json


def request_command(raw):
    if not isinstance(raw,dict) or set(raw)!={"receipt_id","request_id","acknowledged"}:
        raise ContractError("INVALID_BOOKING_REQUEST")
    if raw["acknowledged"] is not True:raise ContractError("BOOKING_ACK_REQUIRED")
    identifier(raw["receipt_id"]);identifier(raw["request_id"])
    return hashlib.sha256(json.dumps(raw,sort_keys=True,separators=(",",":")).encode()).hexdigest()


def revision(value):
    if type(value) is not int or value<1:raise ContractError("BOOKING_REVISION_REQUIRED")
    return value


def proof(value,key,total):
    if (not isinstance(value,dict) or value.get("verified") is not True or value.get("booking_id")!=key
            or type(value.get("paid_krw")) is not int or value["paid_krw"]!=total
            or value.get("currency")!="KRW" or not isinstance(value.get("reference"),str)
            or not 1<=len(value["reference"])<=200 or not value["reference"].isascii()):
        raise ContractError("VERIFIED_PAYMENT_REQUIRED")
    return value["reference"]
