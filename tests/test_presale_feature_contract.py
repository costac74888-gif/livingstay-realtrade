"""분양 기능의 배포 안전 계약(외부 DB 없이 소스 단위로 검증)."""
from pathlib import Path
import os
import io
import unittest


class PresaleFeatureContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Path("app.py").read_text(encoding="utf-8")
        cls.db = Path("db.py").read_text(encoding="utf-8")
        cls.storage = Path("storage_util.py").read_text(encoding="utf-8")
        cls.start = Path("scripts/start-prod.sh").read_text(encoding="utf-8")

    def test_schema_and_production_boot_ensure_presale_tables(self):
        self.assertIn('SCHEMA_VERSION = "2026-09-05-07"', self.db)
        for table in ("presale_projects", "presale_promotions", "presale_audit_log"):
            self.assertIn(f"CREATE TABLE IF NOT EXISTS {table}", self.db)
        self.assertIn("ensure_presale_schema.py", self.start)
        self.assertIn("ADD COLUMN IF NOT EXISTS remaining_units", self.db)
        self.assertIn("NOT VALID", self.db)

    def test_registration_cta_has_a_real_page(self):
        self.assertIn('@app.route("/apply/presale")', self.app)
        page = Path("static/apply_presale.html").read_text(encoding="utf-8")
        self.assertIn("/api/building/", page)
        self.assertIn("URLSearchParams", page)
        self.assertNotIn("<form", page.lower())

    def test_public_queries_use_real_precompletion_rule_and_allowlist(self):
        self.assertIn("building_status IN ('허가','착공')", self.app)
        self.assertIn("NULLIF(b.use_apr_day,'') IS NULL", self.app)
        self.assertIn("NULLIF(use_apr_day,'') IS NULL", self.app)
        self.assertIn("def _presale_public_project", self.app)
        self.assertNotIn('"banner_object_key": promo', self.app)
        self.assertIn("LEFT JOIN LATERAL", self.app)
        self.assertIn("p.project_status IN ('presale','scheduled')", self.app)
        self.assertIn("b.id AS master_building_id", self.app)

    def test_banner_namespace_and_https_cta_guards_are_dedicated(self):
        self.assertIn("PRESALE_BANNER_REF_RE", self.storage)
        self.assertIn("def _presale_safe_url", self.app)
        self.assertIn('parsed.scheme != "https"', self.app)
        self.assertIn("ipaddress.ip_address(host).is_global", self.app)
        self.assertIn("is_valid_presale_banner_ref(key)", self.app)
        self.assertIn('or "." not in host', self.app)

    def test_admin_writes_are_guarded_and_audited(self):
        self.assertGreaterEqual(self.app.count("@require_admin"), 4)
        self.assertIn("_presale_audit(cur,", self.app)
        self.assertIn("이미 현재 분양 프로젝트", self.app)
        self.assertIn("프로모션 이력이 있는 초안", self.app)

    def test_payload_domain_ranges_phone_and_public_allowlist(self):
        # Importing helpers with startup DDL disabled makes this a focused unit test.
        os.environ["SKIP_STARTUP_SCHEMA_INIT"] = "1"
        import app as server
        payload = server._presale_project_payload({
            "title": "테스트", "unit_count": 10, "remaining_units": 3,
            "price_min": 10000, "price_max": 20000, "contact_phone": "010-1234-5678",
        })
        self.assertEqual(payload["project_status"], "presale")
        self.assertEqual(payload["project_type"], "mixed")
        self.assertEqual(payload["contact_phone"], "01012345678")
        with self.assertRaises(ValueError):
            server._presale_project_payload({"title": "x", "unit_count": 2, "remaining_units": 3})
        safe = server._presale_public_project({
            "id": 1, "master_building_id": 9, "project_status": "presale", "project_type": "living",
            "unit_count": 10, "remaining_units": 2, "price_min": 1, "price_max": 2,
            "contact_phone": "01012345678", "editorial_body": "private", "created_by": 44,
        })
        self.assertEqual(safe["master_building_id"], 9)
        self.assertNotIn("contact_phone", safe)
        self.assertNotIn("editorial_body", safe)
        self.assertNotIn("created_by", safe)

    def test_safe_url_rejects_private_local_and_credentials(self):
        os.environ["SKIP_STARTUP_SCHEMA_INIT"] = "1"
        import app as server
        self.assertEqual(server._presale_safe_url("https://example.com/a"), "https://example.com/a")
        for url in ("http://example.com", "https://localhost/x", "https://foo.local/x",
                    "https://127.0.0.1/x", "https://user:pass@example.com/x", "https://intranet/x"):
            self.assertIsNone(server._presale_safe_url(url), url)

    def test_public_stats_uses_one_set_based_query_and_safe_candidate_id(self):
        os.environ["SKIP_STARTUP_SCHEMA_INIT"] = "1"
        import app as server
        class Cursor:
            def __init__(self): self.sql = []; self.n = 0
            def execute(self, sql, args=None): self.sql.append(sql); self.n += 1
            def fetchall(self):
                if self.n == 1:
                    return [{"id": 1, "master_building_id": 8, "title": "A", "summary": "s",
                             "project_status": "presale", "project_type": "living", "unit_count": 10,
                             "remaining_units": 2, "price_min": 100, "price_max": 200, "sale_start_date": None,
                             "sale_end_date": None, "move_in_date": None, "company_name": "C",
                             "building_name": "B", "road_address": "R", "lat": 37.1, "lng": 127.1, "is_paid": True,
                             "contact_phone": "secret", "editorial_body": "secret"}]
                return [{"master_building_id": 9, "building_name": "candidate", "road_address": "R", "lat": 1, "lng": 2, "completion_expected_date": None}]
            def close(self): pass
        class Conn:
            def __init__(self): self.cur = Cursor()
            def cursor(self): return self.cur
            def close(self): pass
        conn = Conn(); original = server.get_conn; server.get_conn = lambda: conn
        try:
            response = server.app.test_client().get("/api/stats/presale")
        finally:
            server.get_conn = original
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["candidates"][0]["master_building_id"], 9)
        self.assertTrue(data["projects"][0]["is_paid"])
        self.assertNotIn("contact_phone", data["projects"][0])
        self.assertNotIn("editorial_body", data["projects"][0])
        self.assertIn("LEFT JOIN LATERAL", conn.cur.sql[0])
        self.assertIn("p.status='published'", conn.cur.sql[0])
        self.assertIn("p.project_status IN ('presale','scheduled')", conn.cur.sql[0])

    def test_expired_or_unauthorized_banner_never_downloads_object(self):
        os.environ["SKIP_STARTUP_SCHEMA_INIT"] = "1"
        import app as server
        key = "presale_banners/" + "a" * 32 + ".jpg"
        class Cursor:
            def execute(self, *args): self.sql = args[0]
            def fetchone(self): return None  # SQL's NOW window rejects expired promotion.
            def close(self): pass
        class Conn:
            def cursor(self): return Cursor()
            def close(self): pass
        original_conn, original_download = server.get_conn, server.storage_util.download_bytes
        server.get_conn = lambda: Conn()
        server.storage_util.download_bytes = lambda _key: self.fail("unauthorized banner was downloaded")
        try:
            response = server.app.test_client().get("/api/presale/banner/" + key)
        finally:
            server.get_conn, server.storage_util.download_bytes = original_conn, original_download
        self.assertEqual(response.status_code, 404)

    def test_banner_upload_rejects_small_dimensions_before_storage(self):
        os.environ["SKIP_STARTUP_SCHEMA_INIT"] = "1"
        import app as server
        from PIL import Image
        image = Image.new("RGB", (10, 10)); binary = io.BytesIO(); image.save(binary, "PNG"); binary.seek(0)
        client = server.app.test_client()
        with client.session_transaction() as session: session["admin"] = True
        response = client.post("/api/admin/presale/banners", data={"file": (binary, "banner.png")})
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()