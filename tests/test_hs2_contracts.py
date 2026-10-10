"""Static contracts for the harness/spec only, not future product acceptance."""
import json
import os
import socket
import unittest
from pathlib import Path
from hs2_harness import core


class HarnessContracts(unittest.TestCase):
    def test_plan_has_all_fixed_requirements_and_unimplemented_tests_block(self):
        plan, registry = core.configuration()
        self.assertEqual(len(plan["stages"]), 18)
        self.assertTrue(all(a["check"] is None or a["check"] in registry
                            for s in plan["stages"] for a in s["acceptance"]))
        spec = (core.DOC / "MASTER_SPEC.md").read_text()
        for requirement in ["PRESERVE-01", "STAY-01", "STAY-02", "PRICE-01", "PRICE-02",
                            "BOOKING-01", "MAP-01", "MAP-02", "MAP-03", "MAP-04",
                            "GATE-01", "GATE-02", "GATE-03", "머무는 곳을, 집처럼."]:
            self.assertIn(requirement, spec)

    def test_preservation_baseline_matches_existing_source(self):
        self.assertGreaterEqual(core.preservation()["preserved_routes"], 616)

    def test_guard_blocks_network_even_localhost(self):
        if os.environ.get("HS2_HARNESS_GUARD") != "1":
            self.skipTest("Must run via safe harness; never probe live services")
        with self.assertRaises(RuntimeError):
            socket.create_connection(("127.0.0.1", 5000))

    def test_guard_blocks_app_import_and_db(self):
        if os.environ.get("HS2_HARNESS_GUARD") != "1":
            self.skipTest("Must run via safe harness; never import live app")
        with self.assertRaises(ImportError):
            __import__("app")
        import psycopg2
        with self.assertRaises(RuntimeError):
            psycopg2.connect("dbname=never-connect")

    def test_regression_registry_contains_each_protected_domain(self):
        registry = core.load(core.CHECKS)
        self.assertTrue({"lodging-status", "lodging-types", "auction-domain", "relay",
                         "map-legacy", "admin-scope", "privacy-ui"}.issubset(registry))


if __name__ == "__main__":
    unittest.main()
