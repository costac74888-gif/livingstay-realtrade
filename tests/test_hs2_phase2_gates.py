"""Phase 2 fail-closed receipt and preservation contracts, no database access."""
from copy import deepcopy
import json
from pathlib import Path
import socket
import subprocess
import unittest
from unittest.mock import patch

from hs2_harness import core, phases


class Phase2GateContracts(unittest.TestCase):
    def setUp(self):
        # Child guard forbids Git subprocesses. Historical objects are synthetic
        # inputs here; the parent verifies the real Git objects before every run.
        self.historical_state = {"stages":{"1":deepcopy(core.load(core.STATE)["stages"]["1"])}}
        self.historical_plan = deepcopy(core.load(core.PLAN))
        def historical_read(*args):
            if args[0] != "show":
                raise AssertionError("unexpected Git operation in fixture")
            return json.dumps(self.historical_state if args[1].endswith("state.json") else self.historical_plan)
        self.git_patch=patch.object(core,"git",side_effect=historical_read)
        self.git_patch.start()
        self.addCleanup(self.git_patch.stop)

    def row(self):
        return dict(status="PASS",verification=dict(fingerprint="bytes",results=[
            dict(id="a",status="PASS",exit_code=0),dict(id="b",status="PASS",exit_code=0)]))

    def test_complete_requires_all_current_byte_pass_results(self):
        phases.valid_receipt(self.row(),"bytes",["a","b"])
        for mutation in ("empty","fail","exit","missing","duplicate","stale","status"):
            row=self.row()
            if mutation=="empty":row["verification"]["results"]=[]
            if mutation=="fail":row["verification"]["results"][0]["status"]="FAIL"
            if mutation=="exit":row["verification"]["results"][0]["exit_code"]=1
            if mutation=="missing":row["verification"]["results"].pop()
            if mutation=="duplicate":row["verification"]["results"][1]["id"]="a"
            if mutation=="stale":row["verification"]["fingerprint"]="old"
            if mutation=="status":row["status"]="RUNNING"
            with self.subTest(mutation=mutation), self.assertRaises(core.GateError):
                phases.valid_receipt(row,"bytes",["a","b"])

    def test_phase1_receipt_native_plan_and_pending_stages_preserved(self):
        _,registry=phases.configuration()
        self.assertTrue({"phase1-use-contracts","phase1-graph-contracts","phase2-data-contracts","phase2-gate-contracts"}<=set(registry))
        state=core.load(core.STATE)
        self.assertEqual(state["stages"]["1"]["status"],"COMPLETE")
        self.assertTrue(all(v["status"]=="PENDING" for k,v in state["stages"].items() if k!="1"))
        self.assertTrue(all(v["status"]=="NOT_APPROVED" for v in state["approval_gates"].values()))

    def test_unimplemented_or_changed_phase_acceptance_is_blocked(self):
        original=core.load(phases.PLAN)
        load=core.load
        for mutation in ("missing","scope"):
            changed=deepcopy(original)
            if mutation=="missing":changed["acceptance"].pop()
            else:changed["stop_after_phase"]=3
            with patch.object(core,"load",side_effect=lambda p:changed if p==phases.PLAN else load(p)):
                with self.assertRaises(core.GateError):phases.configuration()

    def test_phase1_completion_mutation_is_rejected(self):
        load=core.load
        changed=deepcopy(load(core.STATE))
        changed["stages"]["1"]["status"]="PASS"
        with patch.object(core,"load",side_effect=lambda p:changed if p==core.STATE else load(p)):
            with self.assertRaises(core.GateError):phases.configuration()

    def test_fixture_capability_cannot_be_granted_to_another_check(self):
        check=core.load(core.CHECKS)["phase2-data-contracts"]
        from hs2_harness.isolated_postgres import run_check
        with self.assertRaises(core.GateError):run_check("unreviewed",check,1)

    def test_normal_suites_keep_database_network_and_process_denials(self):
        import psycopg2
        for call in (lambda:psycopg2.connect(),lambda:socket.create_connection(("localhost",5000)),
                     lambda:subprocess.Popen(["postgres"])):
            with self.assertRaises(RuntimeError):call()

    def test_no_operational_import_or_hidden_dsn_fallback(self):
        root=core.ROOT
        for name in ("app.py","db.py","listing_extensions.py","public_api_client.py"):
            self.assertNotIn("hs2_data",(root/name).read_text())
        for name in ("repository.py",):
            text=(root/"hs2_data"/name).read_text()
            self.assertNotIn("PROD_DATABASE_URL",text)
            self.assertNotIn('os.environ["DATABASE_URL"]',text)
        self.assertEqual(core.preservation(),dict(frozen_files=13,preserved_routes=616,must_exist=10))


if __name__=="__main__":
    unittest.main()
