"""Real service and HTTP handlers; every provider mocked, network/DB forbidden."""
from copy import deepcopy
import json
import unittest
from flask import Flask
from hs2_registration.api import create_blueprint
from hs2_registration.fixtures import (
    ROAD,MemoryReferenceStore,address_response,title_response,coordinate_response)
from hs2_registration.providers import ReadPorts,LookupError,parse_addresses,parse_buildings,parse_coordinates
from hs2_registration.service import RegistrationService,RegistrationError


class RegistrationContracts(unittest.TestCase):
    def setUp(self):
        self.addresses=address_response();self.titles=title_response();self.coords=coordinate_response();self.masters=[]
        self.now=0;self.store=MemoryReferenceStore()
        self.service=RegistrationService(ReadPorts(lambda q:deepcopy(self.addresses),
            lambda a:deepcopy(self.titles),lambda a:deepcopy(self.coords),lambda i:deepcopy(self.masters)),
            self.store,clock=lambda:self.now)

    def building(self,actor=101):
        s=self.service.start(actor,"검증로 10");key=s["workflow_id"]
        self.assertEqual(s["status"],"ADDRESS_SELECTION_REQUIRED")
        s=self.service.select_address(actor,key,s["addresses"][0]["address_key"])
        s=self.service.select_building(actor,key,s["buildings"][0]["building_key"])
        return key

    def test_happy_path_is_explicit_and_reference_only(self):
        key=self.building();s=self.service.coordinates(101,key)
        self.assertEqual(s["status"],"READY_FOR_REFERENCE")
        self.assertEqual(s["legacy_state"],"SEPARATE_REFERENCE")
        self.assertEqual(s["coordinates"]["precision"],"official_address")
        self.assertEqual(self.store.references,{})
        s=self.service.confirm(101,key)
        self.assertEqual(s["status"],"REFERENCE_CONFIRMED")
        self.assertEqual(self.service.confirm(101,key),s)
        self.assertEqual(len(self.store.references),1)

    def test_every_building_use_is_eligible_without_reclassification(self):
        for use in ("원룸","오피스텔","아파트","빌라","연립","다세대","다가구","단독","도시형생활주택",
                    "숙박시설","농어촌민박","한옥","캠핑","상가","창고","기타","복합","미확인"):
            with self.subTest(use=use):
                self.titles=title_response(use)
                key=self.building()
                s=self.service.coordinates(101,key)
                self.assertEqual(s["building"]["building_use"],use)
                self.assertEqual(s["status"],"READY_FOR_REFERENCE")

    def test_existing_master_exact_optional_read_only_link(self):
        self.masters=[dict(id=42,identity_key="registry:one")]
        key=self.building();s=self.service.coordinates(101,key)
        self.assertEqual(s["legacy_state"],"EXACT_EXISTING")
        self.assertNotIn("legacy_id",s)
        self.service.confirm(101,key)
        self.assertEqual(next(iter(self.store.references.values()))[1][2],42)

    def test_ambiguous_addresses_never_auto_select(self):
        rows=self.addresses["results"]["juso"];second=deepcopy(rows[0]);second["bdMgtSn"]="second"
        self.addresses=address_response(rows+[second])
        s=self.service.start(101,"검증로")
        self.assertEqual(len(s["addresses"]),2);self.assertNotIn("address",s)
        with self.assertRaises(RegistrationError):self.service.coordinates(101,s["workflow_id"])

    def test_multiple_buildings_require_explicit_selection(self):
        self.titles+=title_response(pk="two")
        s=self.service.start(101,"검증로");s=self.service.select_address(101,s["workflow_id"],s["addresses"][0]["address_key"])
        self.assertEqual(len(s["buildings"]),2);self.assertNotIn("building",s)
        s=self.service.select_building(101,s["workflow_id"],"two")
        self.assertEqual(s["building"]["identity_key"],"registry:two")

    def test_empty_address_does_not_fabricate_candidates(self):
        self.addresses=address_response([])
        s=self.service.start(101,"없는 주소")
        self.assertEqual(s["status"],"ADDRESS_NOT_FOUND");self.assertEqual(s["addresses"],[])

    def test_incomplete_or_duplicate_address_result_is_blocked(self):
        self.addresses["results"]["common"]["totalCount"]="9"
        s=self.service.start(101,"검증로");self.assertEqual(s["status"],"ADDRESS_INCOMPLETE")
        self.addresses=address_response(address_response()["results"]["juso"]*2)
        self.assertEqual(self.service.start(101,"검증로")["status"],"ADDRESS_IDENTITY_AMBIGUOUS")

    def test_registry_not_found_is_explicit(self):
        self.titles=[];s=self.service.start(101,"검증로")
        s=self.service.select_address(101,s["workflow_id"],s["addresses"][0]["address_key"])
        self.assertEqual(s["status"],"REGISTRY_UNCONFIRMED")
        with self.assertRaises(RegistrationError):self.service.confirm(101,s["workflow_id"])

    def test_registry_mismatch_or_duplicate_pk_is_blocked(self):
        for titles,status in ((title_response(road="다른 주소"),"REGISTRY_ADDRESS_MISMATCH"),
                              (title_response()*2,"REGISTRY_IDENTITY_AMBIGUOUS")):
            self.titles=titles;s=self.service.start(101,"검증로")
            s=self.service.select_address(101,s["workflow_id"],s["addresses"][0]["address_key"])
            self.assertEqual(s["status"],status);self.assertEqual(s["buildings"],[])

    def test_no_coordinates_is_explicit_without_fallback(self):
        self.coords=coordinate_response([])
        s=self.service.coordinates(101,self.building())
        self.assertEqual(s["status"],"COORDINATES_UNCONFIRMED");self.assertNotIn("coordinates",s)

    def test_coordinate_ambiguity_not_first_result(self):
        self.coords=coordinate_response(coordinate_response()["documents"]*2)
        s=self.service.coordinates(101,self.building())
        self.assertEqual(s["status"],"COORDINATES_AMBIGUOUS");self.assertNotIn("coordinates",s)

    def test_coordinate_response_not_complete(self):
        self.coords["meta"]["is_end"]=False
        self.assertEqual(self.service.coordinates(101,self.building())["status"],"COORDINATES_INCOMPLETE")

    def test_coordinate_address_not_inferred_from_similar_name(self):
        self.coords["documents"][0]["road_address"]["address_name"]=ROAD+" 별관"
        s=self.service.coordinates(101,self.building())
        self.assertEqual(s["status"],"COORDINATE_ADDRESS_MISMATCH")

    def test_nan_infinity_bool_and_out_of_range_rejected(self):
        for x,y in (("nan","37"),("127","inf"),(True,"37"),("181","37"),("127","91")):
            with self.subTest(x=x,y=y):
                self.coords=coordinate_response([dict(x=x,y=y,road_address=dict(address_name=ROAD))])
                self.assertEqual(self.service.coordinates(101,self.building())["status"],"COORDINATES_INVALID")

    def test_kakao_axis_order_preserved(self):
        c=parse_coordinates(self.coords,{"road_address":ROAD})
        self.assertEqual((c["lat"],c["lng"]),(37.5,127.0))

    def test_master_mismatch_duplicate_and_invalid_id_cannot_confirm(self):
        for rows,status in (([dict(id=42,identity_key="wrong")],"MASTER_LINK_MISMATCH"),
                            ([dict(id=True,identity_key="registry:one")],"MASTER_LINK_MISMATCH"),
                            ([dict(id=42,identity_key="registry:one")]*2,"MASTER_LINK_AMBIGUOUS")):
            self.masters=rows;key=self.building()
            self.assertEqual(self.service.coordinates(101,key)["status"],status)
            with self.assertRaises(RegistrationError):self.service.confirm(101,key)

    def test_raw_provider_errors_are_not_exposed(self):
        def fail(_):raise RuntimeError("confmKey=synthetic-secret private raw response")
        for which,fallback in (("addresses","ADDRESS_PROVIDER_FAILED"),("buildings","REGISTRY_PROVIDER_FAILED"),
                               ("coordinates","COORDINATES_PROVIDER_FAILED"),("legacy","MASTER_LOOKUP_FAILED")):
            key=self.building()
            p=self.service.ports
            values={k:getattr(p,k) for k in ("addresses","buildings","coordinates","legacy")};values[which]=fail
            self.service.ports=ReadPorts(**values)
            if which=="addresses":s=self.service.start(101,"검증로")
            elif which=="buildings":s=self.service.select_address(101,key,self.addresses["results"]["juso"][0]["bdMgtSn"])
            else:s=self.service.coordinates(101,key)
            self.assertEqual(s["status"],fallback)
            self.assertNotIn("synthetic-secret",json.dumps(s))
            self.service.ports=p

    def test_actor_owner_isolation_and_auth_validation(self):
        key=self.building()
        for call in (lambda:self.service.read(102,key),lambda:self.service.coordinates(102,key),
                     lambda:self.service.confirm(102,key),lambda:self.service.select_building(102,key,"one")):
            with self.assertRaisesRegex(RegistrationError,"WORKFLOW_NOT_FOUND"):call()
        for actor in (None,True,0,-1,"101"):
            with self.assertRaisesRegex(RegistrationError,"AUTH_REQUIRED"):self.service.start(actor,"검증로")

    def test_expired_workflows_fail_closed(self):
        key=self.building();self.now=901
        with self.assertRaisesRegex(RegistrationError,"WORKFLOW_EXPIRED"):self.service.read(101,key)

    def test_reselection_invalidates_all_downstream_evidence(self):
        key=self.building();s=self.service.coordinates(101,key)
        s=self.service.select_address(101,key,s["address"]["address_key"])
        for field in ("building","coordinates","legacy_state"):self.assertNotIn(field,s)
        with self.assertRaises(RegistrationError):self.service.confirm(101,key)

    def test_forged_address_building_or_workflow_key_rejected(self):
        key=self.building()
        for call in (lambda:self.service.select_address(101,key,"forged"),
                     lambda:self.service.select_building(101,key,"forged"),lambda:self.service.read(101,"forged")):
            with self.assertRaises(RegistrationError):call()

    def test_public_view_does_not_leak_any_join_location_or_id(self):
        s=self.service.coordinates(101,self.building())
        p=self.service.public_view(s)
        self.assertEqual(p,dict(status="NOT_PUBLIC",location_precision="withheld"))
        self.assertNotIn(ROAD,json.dumps(p));self.assertNotIn("127",json.dumps(p))

    def test_inputs_are_bounded_and_not_interpreted_as_coordinates(self):
        for q in ("","x","x"*161,"검증\\x00".replace("\\x00","\x00"),None,{}):
            with self.assertRaises(RegistrationError):self.service.start(101,q)
        s=self.service.start(101,"37.5,127.0")
        self.assertNotIn("coordinates",s)

    def test_saved_workflow_cannot_change_identity(self):
        key=self.building();self.service.coordinates(101,key);self.service.confirm(101,key)
        with self.assertRaises(RegistrationError):self.service.select_building(101,key,"one")
        with self.assertRaises(RegistrationError):self.service.select_address(101,key,"forged")

    def test_store_failure_does_not_report_success(self):
        key=self.building();self.service.coordinates(101,key)
        self.store.save=lambda *a:(_ for _ in ()).throw(RuntimeError("secret"))
        s=self.service.confirm(101,key)
        self.assertEqual(s["status"],"REFERENCE_SAVE_FAILED");self.assertNotIn("reference_id",s)

    def test_no_live_or_default_provider_configuration(self):
        with self.assertRaises(LookupError):ReadPorts(None,None,None,None)
        with self.assertRaises(LookupError):ReadPorts(*([lambda _:None]*4),mode="production")

    def test_response_views_are_detached_from_server_owned_state(self):
        s=self.service.start(101,"검증로");s["addresses"][0]["road_address"]="forged"
        self.assertEqual(self.service.read(101,s["workflow_id"])["addresses"][0]["road_address"],ROAD)

    def test_capacity_is_bounded_and_expired_entries_released(self):
        self.service.max_sessions=1;self.service.start(101,"검증로")
        with self.assertRaisesRegex(RegistrationError,"WORKFLOW_CAPACITY"):self.service.start(101,"검증로")
        self.now=901;self.assertIn("workflow_id",self.service.start(101,"검증로"))


class APIContracts(unittest.TestCase):
    def setUp(self):
        from hs2_registration.fixtures import fixture_service
        self.actor=101;self.csrf=True;self.service=fixture_service()
        self.app=Flask("phase3_test");self.app.register_blueprint(create_blueprint(self.service,lambda:self.actor,lambda:self.csrf))
        self.client=self.app.test_client();self.base="/hs2/registration"

    def start(self):
        r=self.client.post(self.base+"/start",json={"query":"검증로"});self.assertEqual(r.status_code,200)
        return r.get_json()

    def test_real_http_handler_full_workflow(self):
        s=self.start();path=self.base+"/"+s["workflow_id"]
        s=self.client.post(path+"/address",json={"address_key":s["addresses"][0]["address_key"]}).get_json()
        s=self.client.post(path+"/building",json={"building_key":s["buildings"][0]["building_key"]}).get_json()
        self.assertEqual(s["status"],"COORDINATES_REQUIRED")
        s=self.client.post(path+"/coordinates",json={}).get_json();self.assertEqual(s["status"],"READY_FOR_REFERENCE")
        r=self.client.post(path+"/confirm",json={});self.assertEqual(r.get_json()["status"],"REFERENCE_CONFIRMED")
        self.assertIn("no-store",r.headers["Cache-Control"]);self.assertIn("connect-src 'self'",r.headers["Content-Security-Policy"])

    def test_guest_cannot_read_api_or_ui(self):
        self.actor=None
        for method,path in (("GET",self.base+"/"),("POST",self.base+"/start")):
            self.assertEqual(self.client.open(path,method=method,json={}).status_code,401)

    def test_csrf_required_for_mutations(self):
        self.csrf=False;self.assertEqual(self.client.post(self.base+"/start",json={"query":"주소"}).status_code,403)

    def test_other_actor_cannot_read_state(self):
        s=self.start();self.actor=102
        self.assertEqual(self.client.get(self.base+"/"+s["workflow_id"]).status_code,404)

    def test_payload_cannot_override_actor_coordinates_or_master(self):
        s=self.start();path=self.base+"/"+s["workflow_id"]
        for body in ({"lat":37,"lng":127},{"actor":101},{"master_id":42}):
            self.assertEqual(self.client.post(path+"/coordinates",json=body).status_code,409)
        self.assertEqual(self.client.post(self.base+"/start",json={"query":"주소","actor":102}).status_code,409)

    def test_wrong_order_is_explicit_http_error(self):
        s=self.start();self.assertEqual(self.client.post(self.base+"/"+s["workflow_id"]+"/confirm",json={}).status_code,409)

    def test_non_json_and_unknown_actions_fail_closed(self):
        self.assertEqual(self.client.post(self.base+"/start",data="not-json").status_code,409)
        s=self.start();self.assertEqual(self.client.post(self.base+"/"+s["workflow_id"]+"/unknown",json={}).status_code,409)

    def test_identity_csrf_adapters_are_mandatory(self):
        with self.assertRaises(ValueError):create_blueprint(self.service,None,None)
