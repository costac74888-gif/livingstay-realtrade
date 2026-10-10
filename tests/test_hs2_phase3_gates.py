from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from hs2_harness import core,phase3,phases


class Phase3Gates(unittest.TestCase):
    def setUp(self):
        self.state=deepcopy(core.load(core.STATE));self.registry=deepcopy(core.load(core.CHECKS));self.plan=deepcopy(core.load(core.PLAN))
        def historical(*args):
            if args[0]!="show":raise AssertionError("Unexpected Git operation")
            path=args[1].split(":",1)[1]
            return json.dumps(self.state if path.endswith("state.json") else
                {k:v for k,v in self.registry.items() if not k.startswith("phase3-")} if path.endswith("checks.json") else self.plan)
        p=patch.object(core,"git",side_effect=historical);p.start();self.addCleanup(p.stop)

    def test_prior_receipts_and_native_plan_preserved(self):
        phase3.configuration()
        self.assertEqual(self.state["user_phases"]["2"]["status"],"COMPLETE")
        self.assertTrue(all(r["status"]=="PENDING" for k,r in self.state["stages"].items() if k!="1"))

    def test_changed_phase2_receipt_rejected(self):
        changed=deepcopy(self.state);changed["user_phases"]["2"]["status"]="PASS";load=core.load
        with patch.object(core,"load",side_effect=lambda p:changed if p==core.STATE else load(p)):
            with self.assertRaises(core.GateError):phase3.configuration()

    def test_missing_acceptance_or_wider_authorization_rejected(self):
        for kind in ("missing","scope"):
            changed=deepcopy(core.load(phase3.PLAN));load=core.load
            if kind=="missing":changed["acceptance"].pop()
            else:changed["stop_after_phase"]=4
            with patch.object(core,"load",side_effect=lambda p:changed if p==phase3.PLAN else load(p)):
                with self.assertRaises(core.GateError):phase3.configuration()

    def test_operational_gate_not_implicitly_approved(self):
        changed=deepcopy(self.state);changed["approval_gates"]["production_migration"]["status"]="APPROVED";load=core.load
        with patch.object(core,"load",side_effect=lambda p:changed if p==core.STATE else load(p)):
            with self.assertRaises(core.GateError):phase3.configuration()

    def test_full_fresh_pass_required_for_phase3(self):
        row=dict(status="PASS",verification=dict(fingerprint="fresh",results=[dict(id=k,status="PASS",exit_code=0) for k in self.registry]))
        phases.valid_receipt(row,"fresh",list(self.registry))
        for kind in ("stale","partial","fail"):
            x=deepcopy(row)
            if kind=="stale":x["verification"]["fingerprint"]="old"
            elif kind=="partial":x["verification"]["results"].pop()
            else:x["verification"]["results"][0]["status"]="FAIL"
            with self.assertRaises(core.GateError):phases.valid_receipt(x,"fresh",list(self.registry))

    def test_no_existing_app_routes_or_writes_mounted(self):
        self.assertEqual(core.preservation(),dict(frozen_files=13,preserved_routes=616,must_exist=10))
        for name in ("app.py","db.py","public_api_client.py","geocode_buildings.py"):
            self.assertNotIn("hs2_registration",(core.ROOT/name).read_text())

    def test_existing_real_registry_mapper_is_reused(self):
        from hs2_registration.providers import parse_buildings
        from hs2_registration.fixtures import title_response,ROAD
        with patch("building_registry._title_row_to_dict",wraps=__import__("building_registry")._title_row_to_dict) as mapper:
            r=parse_buildings(title_response("창고"),{"road_address":ROAD})
            self.assertEqual(mapper.call_count,1);self.assertEqual(r[0]["building_use"],"창고")

    def test_default_ports_have_no_secret_or_operational_dsn(self):
        for name in ("providers.py","service.py","store.py","fixtures.py","api.py","fixture_http.py"):
            source=(core.ROOT/"hs2_registration"/name).read_text()
            for key in ("PROD_DATABASE_URL","os.environ","from db import","from app import","requests.get"):
                self.assertNotIn(key,source)

    def test_unreviewed_browser_or_db_capability_cannot_run(self):
        from hs2_harness import isolated_browser,isolated_postgres
        with self.assertRaises(core.GateError):isolated_browser.run_check("unknown",{"file":"tests/hs2_phase3_ui_test.cjs"},1)
        with self.assertRaises(core.GateError):isolated_postgres.run_check("unknown",{"file":"tests/test_hs2_phase3_db.py"},1)
