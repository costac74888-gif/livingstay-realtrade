"""Fail-closed sequential user-phase receipts, not document-only acceptance."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch
from hs2_harness import core, continuation, phase3
from hs2_harness.phases import valid_receipt


class ContinuationContracts(unittest.TestCase):
    def setUp(self):
        self.original = deepcopy(core.load(core.STATE))
        self.plan = deepcopy(core.load(core.PLAN))
        self.registry = deepcopy(core.load(core.CHECKS))
        phase2_checkpoint = core.load(phase3.PLAN)["previous_checkpoint"]

        def historical(*args):
            if args[0] != "show":
                raise AssertionError("Test forbids actual Git/process writes")
            sha, file = args[1].split(":", 1)
            if file.endswith("state.json"):
                return json.dumps(self.original)
            if file.endswith("stages.json"):
                return json.dumps(self.plan)
            return json.dumps({k: v for k, v in self.registry.items()
                               if not k.startswith(("phase4-", "phase5-"))
                               and (sha != phase2_checkpoint or not k.startswith("phase3-"))})
        mock = patch.object(core, "git", side_effect=historical)
        mock.start()
        self.addCleanup(mock.stop)

    def modified(self, path, value):
        load = core.load
        return patch.object(core, "load", side_effect=lambda p: value if p == path else load(p))

    def test_authorized_user_sequence_not_native_numbering(self):
        p, _ = continuation.configuration()
        self.assertEqual(p["phases"][0]["native_acceptance"], ["S02-A01", "S02-A02"])
        self.assertEqual(p["phases"][-1]["title"], "Cutover/Open")
        self.assertTrue(all(v["status"] == "PENDING" for k, v in self.original["stages"].items() if k != "1"))

    def test_changed_work_source_or_scope_blocked(self):
        for key, value in (("work_route", "external"), ("stop_after_phase", 3)):
            changed = deepcopy(core.load(continuation.PLAN))
            changed[key] = value
            with self.modified(continuation.PLAN, changed), self.assertRaises(core.GateError):
                continuation.configuration()

    def test_reordered_missing_phase_or_changed_title_blocked(self):
        for kind in ("order", "missing", "title"):
            changed = deepcopy(core.load(continuation.PLAN))
            if kind == "order":
                changed["phases"][0], changed["phases"][1] = changed["phases"][1], changed["phases"][0]
            elif kind == "missing":
                changed["phases"].pop()
            else:
                changed["phases"][0]["title"] = "Assumed native stage 4"
            with self.modified(continuation.PLAN, changed), self.assertRaises(core.GateError):
                continuation.configuration()

    def test_source_hash_and_manual_gates_bound(self):
        for kind in ("source", "gate"):
            changed = deepcopy(core.load(continuation.PLAN))
            if kind == "source":
                changed["directive"]["sha256"] = "0" * 64
            else:
                changed["manual_gates"].pop()
            with self.modified(continuation.PLAN, changed), self.assertRaises(core.GateError):
                continuation.configuration()

    def test_historical_completed_phase3_receipt_immutable(self):
        changed = deepcopy(self.original)
        changed["user_phases"]["3"]["status"] = "PASS"
        with self.modified(core.STATE, changed), self.assertRaises(core.GateError):
            continuation.configuration()

    def test_operational_approval_not_inferred(self):
        changed = deepcopy(self.original)
        changed["approval_gates"]["production_publish"]["status"] = "APPROVED"
        with self.modified(core.STATE, changed), self.assertRaises(core.GateError):
            continuation.configuration()

    def test_old_missing_failed_and_skipped_results_reject(self):
        ids = list(self.registry)
        row = {"status": "PASS", "verification": {"fingerprint": "fresh",
               "results": [{"id": k, "status": "PASS", "exit_code": 0} for k in ids]}}
        valid_receipt(row, "fresh", ids)
        for kind in ("stale", "partial", "fail", "skip", "duplicate"):
            r = deepcopy(row)
            if kind == "stale":
                r["verification"]["fingerprint"] = "old"
            elif kind == "partial":
                r["verification"]["results"].pop()
            elif kind == "duplicate":
                r["verification"]["results"].append(deepcopy(r["verification"]["results"][0]))
            else:
                r["verification"]["results"][0]["status"] = "FAIL" if kind == "fail" else "SKIP"
            with self.assertRaises(core.GateError):
                valid_receipt(r, "fresh", ids)

    def test_remote_complete_and_source_bound_before_next_phase(self):
        for field, value in (("checkpoint_head", "wrong"), ("source_fingerprint", "stale"),
                             ("main_unchanged", False), ("status", "NOT_VERIFIED")):
            state = deepcopy(self.original)
            state["user_phases"]["4"] = dict(status="COMPLETE", end={"head": "fixture-head"},
                verification={"fingerprint": "fresh"},
                remote=dict(status="SYNCED", head="fixture-head", checkpoint_head="fixture-head",
                            source_fingerprint="fresh", main_unchanged=True))
            state["user_phases"]["4"]["remote"][field] = value
            with self.modified(core.STATE, state), patch.object(continuation, "configuration",
                    return_value=(core.load(continuation.PLAN), self.registry)), \
                    patch.object(core, "git", return_value=""), \
                    patch.object(continuation, "render") as render, self.assertRaises(core.GateError):
                continuation.begin(5)
            render.assert_not_called()

    def test_same_checkpoint_retry_or_collision(self):
        with patch.object(core, "git", side_effect=["", ""]):
            continuation.checkpoint("fixture-tag", "fixture-head")
        with patch.object(core, "git", side_effect=["fixture-tag", "fixture-head"]):
            continuation.checkpoint("fixture-tag", "fixture-head")
        with patch.object(core, "git", side_effect=["fixture-tag", "other"]), self.assertRaises(core.GateError):
            continuation.checkpoint("fixture-tag", "fixture-head")

    def test_no_new_auth_user_store_or_existing_runtime_mount(self):
        self.assertNotIn("hs2_modes", (core.ROOT / "app.py").read_text())
        api = (core.ROOT / "hs2_modes/api.py").read_text()
        self.assertNotIn("CREATE TABLE", api)
        self.assertNotIn("get_conn(", api)
        self.assertNotIn("os.environ", api)
        self.assertNotIn("requests.", api)
        self.assertEqual(core.preservation()["frozen_files"], 13)

    def test_unknown_and_completed_phase_blocked(self):
        with self.assertRaises(core.GateError):
            continuation.row_for({}, 3)
        with self.assertRaises(core.GateError):
            continuation.row_for({}, 19)
        with self.assertRaises(core.GateError):
            continuation.verify(3)
