from copy import deepcopy
from unittest.mock import patch
import unittest
from hs2_harness import core


class ContactChangeApproval(unittest.TestCase):
    def setUp(self):
        self.path = core.DOC / "contact_log_change_approval.json"
        self.approval = core.load(self.path)

    def override(self, approval):
        load = core.load
        return patch.object(core, "load", side_effect=lambda p: approval if p == self.path else load(p))

    def test_exact_logging_revisions_pass_without_changing_original_baseline_or_routes(self):
        baseline = core.load(core.BASELINE)
        for name, record in self.approval["files"].items():
            self.assertEqual(record["baseline_sha256"], baseline["frozen_files"][name])
            self.assertEqual(record["approved_sha256"], core.digest(core.ROOT/name))
            self.assertNotEqual(record["approved_sha256"], record["baseline_sha256"])
        result = core.preservation()
        self.assertEqual(result["frozen_files"], 13)
        self.assertGreaterEqual(result["preserved_routes"], 616)

    def test_any_subsequent_change_remains_blocked(self):
        digest = core.digest
        for name in self.approval["files"]:
            with patch.object(core, "digest", side_effect=lambda p: "f"*64 if p==core.ROOT/name else digest(p)):
                with self.assertRaises(core.GateError):
                    core.preservation()

    def test_approval_cannot_add_files_or_change_scope(self):
        for kind in ("file", "scope", "baseline"):
            a=deepcopy(self.approval)
            if kind=="file":a["files"]["db.py"]={"approved_sha256":"f"*64,"baseline_sha256":"f"*64}
            elif kind=="scope":a["scope"]="operational"
            else:a["files"]["sync_batch.py"]["baseline_sha256"]="f"*64
            with self.override(a),self.assertRaises(core.GateError):
                core.preservation()


if __name__=="__main__":unittest.main()
