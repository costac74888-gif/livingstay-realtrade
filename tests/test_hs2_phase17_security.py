import unittest,ast,os
from pathlib import Path
from unittest.mock import patch
from flask import Response
from urllib.parse import quote
from hs2_design.security import harden
from hs2_consumer.search import query
from secret_redaction import redact_exception


class SecurityContracts(unittest.TestCase):
    def test_strict_existing_csp_and_private_cache_are_not_weakened(self):
        r=Response();r.headers["Content-Security-Policy"]="default-src 'none'";r.headers["Cache-Control"]="no-store, private"
        harden(r);self.assertEqual(r.headers["Content-Security-Policy"],"default-src 'none'")
        self.assertEqual(r.headers["Cache-Control"],"no-store, private")
        self.assertIn("payment=()",r.headers["Permissions-Policy"])
        r=harden(Response());self.assertNotIn("'unsafe-eval'",r.headers["Content-Security-Policy"])
        self.assertIn("object-src 'none'",r.headers["Content-Security-Policy"])

    def test_geocode_errors_redact_encoded_tokens_without_using_real_secrets(self):
        key="synthetic-fixture-token/+?"
        with patch.dict(os.environ,{"KAKAO_REST_API_KEY":key},clear=True):
            result=redact_exception(Exception(key+" "+quote(quote(key,safe=""),safe="")),["KAKAO_REST_API_KEY"])
        self.assertNotIn(key,result);self.assertNotIn(quote(key,safe=""),result)
        for name in ("geocode_buildings.py","geocode_brokers.py"):
            self.assertIn('redact_exception(e, ["KAKAO_REST_API_KEY"])',Path(name).read_text())

    def test_all_additive_api_headers_call_runtime_hardening(self):
        for root in Path(".").glob("hs2_*/api.py"):
            functions=[n for n in ast.walk(ast.parse(root.read_text())) if isinstance(n,ast.FunctionDef) and n.name in ("headers","private_response")]
            for f in functions:
                self.assertTrue(any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=="harden" for n in ast.walk(f)),str(root))
        parsed=query({"q":"'; DROP TABLE users;--"})
        self.assertEqual(parsed["q"],"'; DROP TABLE users;--") # It is only a filter parser, never an SQL executor.
        self.assertNotIn("fast-glob",Path("artifacts/mockup-sandbox/package.json").read_text())


if __name__=="__main__":unittest.main()
