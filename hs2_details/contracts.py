import hashlib
import json
import re
from hs2_design.domain import ContractError
from hs2_listings.validation import identifier
from hs2_supermap.contracts import parse


def selection(raw):
    if not isinstance(raw,dict) or set(raw)-{"check_in","check_out","guests"}:
        raise ContractError("INVALID_DETAIL_SELECTION")
    if (any(type(raw.get(k)) is not str for k in ("check_in","check_out"))
            or type(raw.get("guests")) not in {int,str}):
        raise ContractError("INVALID_DETAIL_SELECTION")
    values=parse({k:str(v) if type(v) is int else v for k,v in raw.items()})
    if not values["check_in"] or type(values["guests"]) is not int or not 1<=values["guests"]<=100:
        raise ContractError("DATES_AND_GUESTS_REQUIRED")
    return values


def command(raw):
    if not isinstance(raw,dict) or set(raw)!={"check_in","check_out","guests","expected_source_version","acknowledged","request_id"}:
        raise ContractError("INVALID_QUOTE_CONFIRMATION")
    if raw["acknowledged"] is not True:
        raise ContractError("EXPLICIT_QUOTE_ACK_REQUIRED")
    if type(raw["guests"]) is not int:
        raise ContractError("INTEGER_GUESTS_REQUIRED")
    version=raw["expected_source_version"]
    if not isinstance(version,str) or not re.fullmatch("[0-9a-f]{64}",version):
        raise ContractError("CURRENT_SOURCE_VERSION_REQUIRED")
    identifier(raw["request_id"])
    selection({k:raw[k] for k in ("check_in","check_out","guests")})
    return dict(raw)


def request_hash(public_id,raw):
    return hashlib.sha256(json.dumps(dict(public_id=public_id,**raw),sort_keys=True,separators=(",",":")).encode()).hexdigest()


def consumer(who):
    if (not isinstance(who,dict) or type(who.get("user_id")) is not int or who["user_id"]<=0
            or who.get("role")!="consumer" or who.get("context_id")!="consumer"
            or who.get("email_verified") is not True):
        raise ContractError("VERIFIED_CONSUMER_REQUIRED")
    return who["user_id"]
