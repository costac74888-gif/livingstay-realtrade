"""Strict adapters for existing JUSO, building-HUB and Kakao response contracts.

Read callables must be explicitly supplied. No network/default credential path.
"""
import math
from dataclasses import dataclass


class LookupError(ValueError):
    pass


def text(value):
    if not isinstance(value, str) or not value.strip() or any(ord(c)<32 for c in value):
        raise LookupError("INVALID_PROVIDER_DATA")
    return value.strip()


def address_key(value):
    # Whitespace equivalence only; no province aliases, inferred lot or address.
    return " ".join(text(value).split())


def count(value):
    if isinstance(value, bool) or not str(value).isdigit():
        raise LookupError("INVALID_PROVIDER_DATA")
    return int(value)


@dataclass(frozen=True)
class ReadPorts:
    addresses: object
    buildings: object
    coordinates: object
    legacy: object
    # All calls in this phase are mocks or owned fixture reads, never live.
    mode: str = "isolated-fixture"

    def __post_init__(self):
        if self.mode != "isolated-fixture" or not all(callable(x) for x in (
                self.addresses,self.buildings,self.coordinates,self.legacy)):
            raise LookupError("UNAPPROVED_PROVIDER")


def parse_addresses(raw):
    result=raw["results"];common=result["common"];rows=result["juso"]
    if str(common["errorCode"]) != "0":
        raise LookupError("ADDRESS_PROVIDER_FAILED")
    if not isinstance(rows,list) or count(common["totalCount"]) != len(rows):
        raise LookupError("ADDRESS_INCOMPLETE")
    if len(rows)>100:
        raise LookupError("REFINE_ADDRESS")
    values=[];seen=set()
    for r in rows:
        key=text(r["bdMgtSn"])
        if key in seen:raise LookupError("ADDRESS_IDENTITY_AMBIGUOUS")
        seen.add(key)
        # bdMgtSn (building-management no) is NOT building-registry PK.
        values.append(dict(address_key=key,road_address=text(r["roadAddrPart1"]),
                           jibun_address=text(r["jibunAddr"]),adm_code=text(r["admCd"])))
    return values


def parse_buildings(raw, address):
    if not isinstance(raw,list) or len(raw)>500:
        raise LookupError("REGISTRY_INVALID")
    # Reuse the real existing field converter, not lodging-only eligibility.
    from building_registry import _title_row_to_dict
    values=[];seen=set()
    for item in raw:
        r=_title_row_to_dict(item)
        pk=text(r["mgm_bldrgst_pk"])
        if pk in seen:raise LookupError("REGISTRY_IDENTITY_AMBIGUOUS")
        seen.add(pk)
        if address_key(r["new_plat_plc"])!=address_key(address["road_address"]):
            raise LookupError("REGISTRY_ADDRESS_MISMATCH")
        values.append(dict(building_key=pk,identity_key="registry:"+pk,
                           name=r["bld_nm"],dong=r["dong_nm"],
                           building_use=text(r["main_purps"]),road_address=r["new_plat_plc"],
                           jibun_address=r["plat_plc"],evidence_version="building-hub:fixture:v1"))
    return values


def parse_coordinates(raw, address):
    docs=raw["documents"];meta=raw["meta"]
    if not isinstance(docs,list) or meta["is_end"] is not True or count(meta["total_count"])!=len(docs):
        raise LookupError("COORDINATES_INCOMPLETE")
    if not docs:raise LookupError("COORDINATES_UNCONFIRMED")
    if len(docs)!=1:raise LookupError("COORDINATES_AMBIGUOUS")
    doc=docs[0]
    if address_key(doc["road_address"]["address_name"])!=address_key(address["road_address"]):
        raise LookupError("COORDINATE_ADDRESS_MISMATCH")
    # Kakao x=longitude, y=latitude. No centroid, nearest result or (0,0) fallback.
    if isinstance(doc["x"],bool) or isinstance(doc["y"],bool):
        raise LookupError("COORDINATES_INVALID")
    lng,lat=float(doc["x"]),float(doc["y"])
    if not math.isfinite(lat) or not math.isfinite(lng) or not (-90<=lat<=90 and -180<=lng<=180):
        raise LookupError("COORDINATES_INVALID")
    return dict(lat=lat,lng=lng,precision="official_address",
                evidence_version="kakao-address:fixture:v1")


def exact_legacy(rows, identity):
    if not isinstance(rows,list):raise LookupError("MASTER_LOOKUP_FAILED")
    if any(r.get("identity_key")!=identity or type(r.get("id")) is not int or r["id"]<=0 for r in rows):
        raise LookupError("MASTER_LINK_MISMATCH")
    if len(rows)>1:raise LookupError("MASTER_LINK_AMBIGUOUS")
    return rows[0]["id"] if rows else None
