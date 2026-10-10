"""Entirely synthetic providers and memory persistence for UI/API rehearsal."""
from copy import deepcopy
from uuid import uuid4
from .providers import ReadPorts
from .service import RegistrationService

ROAD="테스트시 가상구 검증로 10"


def address_response(rows=None):
    rows=rows if rows is not None else [
        dict(bdMgtSn="0000000000000000000000001",roadAddrPart1=ROAD,
             jibunAddr="테스트시 가상구 가상동 1",admCd="0000000000")]
    return dict(results=dict(common=dict(errorCode="0",totalCount=str(len(rows))),juso=deepcopy(rows)))


def title_response(use="주택", pk="one", road=ROAD):
    return [dict(mgmBldrgstPk=pk,bldNm="합성 검증건물",dongNm="101동",
                 mainPurpsCdNm=use,etcPurps="",newPlatPlc=road,platPlc="테스트시 가상구 가상동 1")]


def coordinate_response(docs=None):
    docs=docs if docs is not None else [dict(x="127.0",y="37.5",road_address=dict(address_name=ROAD))]
    return dict(meta=dict(is_end=True,total_count=len(docs)),documents=deepcopy(docs))


class MemoryReferenceStore:
    """Test double, never advertised as real DB persistence."""
    def __init__(self):self.references={}
    def save(self, building, coordinates, master_id):
        identity=building["identity_key"];value=(deepcopy(building),deepcopy(coordinates),master_id)
        if identity in self.references:
            key,old=self.references[identity]
            if old!=value:raise ValueError("REFERENCE_CONFLICT")
            return key
        key=str(uuid4());self.references[identity]=(key,value)
        return key


def fixture_service():
    cases={}
    def addresses(query):
        cases.clear();cases["query"]=query
        if query=="오류":raise ValueError("synthetic confidential upstream error")
        if query=="미검색":return address_response([])
        rows=address_response()
        if query=="모호":
            second=deepcopy(rows["results"]["juso"][0]);second["bdMgtSn"]="0000000000000000000000002"
            rows=address_response([rows["results"]["juso"][0],second])
        # Capture scenario in the private address key; no global provider state
        # is used after the search response is returned.
        for r in rows["results"]["juso"]:r["bdMgtSn"]=query+":"+r["bdMgtSn"]
        return rows
    def buildings(address):
        case=address["address_key"].split(":")[0]
        if case=="대장없음":return []
        rows=title_response(use=case if case in {"상가","창고","캠핑","기타"} else "주택")
        if case=="여러동":rows+=title_response(pk="two")
        return rows
    def coords(address):
        case=address["address_key"].split(":")[0]
        if case=="좌표없음":return coordinate_response([])
        if case=="좌표모호":return coordinate_response(coordinate_response()["documents"]*2)
        return coordinate_response()
    def legacy(identity):
        # Synthetic legacy id 42 exists only for one verified fixture identity.
        return [dict(id=42,identity_key=identity)] if identity=="registry:one" else []
    return RegistrationService(ReadPorts(addresses,buildings,coords,legacy),MemoryReferenceStore())
