"""Real PostgreSQL SQL + isolated Flask routes; only temporary tables are written."""
import json
import unittest
import uuid
from unittest.mock import Mock, patch

from flask import Flask
import auction_building_enrichment as lookup
import auction_service
import building_registry
from auction_building_matching import build_indexes
from db import get_conn
from lodging_staging import assert_development_connection


class _Limiter:
    def limit(self, *args, **kwargs):
        return lambda fn: fn


class LookupIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conn = get_conn()
        assert_development_connection(cls.conn)
        # Same real column types/constraints, but no production or real source rows.
        with cls.conn.cursor() as cur:
            for name in ("master_buildings", "auction_items", "auction_rounds", "auction_photos"):
                cur.execute(f"CREATE TEMP TABLE {name} (LIKE public.{name} INCLUDING ALL)")
            cur.execute("""CREATE TEMP TABLE app_meta(
              key TEXT PRIMARY KEY,value TEXT NOT NULL,updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
        cls.conn.commit()
        cls.patches = [
            patch.object(lookup, "get_conn", return_value=cls.conn),
            patch.object(auction_service, "get_conn", return_value=cls.conn),
            patch("auction_building_matching.get_indexes", return_value=build_indexes([])),
            patch("stats_cache.mark_master_stats_invalidated"),
        ]
        for owned in cls.patches:
            owned.start()
        app = Flask(__name__)
        auction_service.register_auction_routes(
            app, _Limiter(), lambda path: "", lambda fn: fn, Mock(),
            lambda *a: [], lambda *a: [], lambda: None)
        cls.client = app.test_client()

    @classmethod
    def tearDownClass(cls):
        for owned in reversed(cls.patches):
            owned.stop()
        with cls.conn.cursor() as cur:
            cur.execute("DROP TABLE pg_temp.auction_photos,pg_temp.auction_rounds,"
                        "pg_temp.auction_items,pg_temp.master_buildings,pg_temp.app_meta")
        cls.conn.commit()
        cls.conn.close()

    def setUp(self):
        with self.conn.cursor() as cur:
            cur.execute("TRUNCATE app_meta,auction_items,master_buildings")
            cur.execute("""INSERT INTO auction_items(source_item_id,title,address_jibun,
              usage_name,lodging_category,area_m2,status) VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                        [uuid.uuid4().hex, "인천광역시 서구 석남동 9999-9999 검증숙박 B동 407호",
                         "인천광역시 서구 석남동 9999-9999", "생활숙박시설", "생활", 26.12, "bidding"])
            self.id = cur.fetchone()["id"]
        self.conn.commit()
        self.title = {"mgmBldrgstPk": "isolated-" + uuid.uuid4().hex,
                      "platPlc": "인천광역시 서해구 석남동 9999-9999",
                      "newPlatPlc": "인천광역시 서해구 검증로 9999", "dongNm": "B동",
                      "bldNm": "검증숙박", "mainPurpsCdNm": "숙박시설",
                      "etcPurps": "생활숙박시설", "totArea": "1200",
                      "hoCnt": "50", "useAprDay": "20210102"}

    def claim(self):
        with patch.object(lookup.subprocess, "Popen") as spawn:
            spawn.return_value.wait.return_value = 0
            response = self.client.post(f"/api/auctions/{self.id}/building-lookup")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["lookup"]["state"], "running")
        with self.conn.cursor() as cur:
            cur.execute("SELECT value FROM app_meta WHERE key=%s", [lookup.PREFIX + str(self.id)])
            return json.loads(cur.fetchone()["value"])["run_id"]

    def test_real_sql_claim_duplicate_run_store_link_and_immediate_detail(self):
        run_id = self.claim()
        with patch.object(lookup.subprocess, "Popen") as spawn:
            self.assertEqual(self.client.post(f"/api/auctions/{self.id}/building-lookup")
                             .json["lookup"]["state"], "running")
            spawn.assert_not_called()
        with patch.object(building_registry, "_fetch_title_rows", return_value=[self.title]) as fetch:
            lookup.run_lookup(self.id, run_id)
        fetch.assert_called_once()
        self.assertEqual(fetch.call_args.kwargs["purpose"], "realtime")
        self.assertEqual(fetch.call_args.kwargs["max_pages"], 3)
        response = self.client.get(f"/api/auctions/{self.id}/building-lookup")
        self.assertEqual(response.json["lookup"]["state"], "done")
        building_id = response.json["lookup"]["building_id"]
        detail = self.client.get(f"/api/auctions/{self.id}").json
        self.assertEqual(detail["item"]["master_building_id"], building_id)
        self.assertEqual(detail["building"]["id"], building_id)
        with self.conn.cursor() as cur:
            cur.execute("SELECT lodging_type,tot_area,units FROM master_buildings WHERE id=%s", [building_id])
            row = cur.fetchone()
        self.assertEqual(row["lodging_type"], "생활")
        self.assertEqual(row["tot_area"], 1200)
        self.assertEqual(row["units"], 50)
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_empty_failed_ambiguous_leave_master_and_link_untouched(self):
        for results in ([], RuntimeError("secret must never appear"), [
            self.title, {**self.title, "mgmBldrgstPk": "different", "dongNm": "B동"}]):
            with self.conn.cursor() as cur:
                cur.execute("DELETE FROM app_meta")
            self.conn.commit()
            run_id = self.claim()
            kwargs = {"side_effect": results} if isinstance(results, Exception) else {"return_value": results}
            with patch.object(building_registry, "_fetch_title_rows", **kwargs):
                lookup.run_lookup(self.id, run_id)
            response = self.client.get(f"/api/auctions/{self.id}/building-lookup")
            expected = "failed" if isinstance(results, Exception) else ("empty" if not results else "ambiguous")
            self.assertEqual(response.json["lookup"]["state"], expected)
            self.assertNotIn("secret", response.get_data(as_text=True))
            with self.conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS n FROM master_buildings")
                self.assertEqual(cur.fetchone()["n"], 0)
                cur.execute("SELECT master_building_id FROM auction_items WHERE id=%s", [self.id])
                self.assertIsNone(cur.fetchone()["master_building_id"])

    def test_read_only_status_cross_site_and_missing_item_never_spawn(self):
        with patch.object(lookup.subprocess, "Popen") as spawn:
            response = self.client.get(f"/api/auctions/{self.id}/building-lookup")
            self.assertEqual(response.json["lookup"]["state"], "idle")
            self.assertEqual(self.client.post(f"/api/auctions/{self.id}/building-lookup",
                                             headers={"Origin": "https://evil.example"}).status_code, 403)
            self.assertEqual(self.client.post("/api/auctions/999999999/building-lookup").status_code, 404)
            spawn.assert_not_called()

    def test_deleted_or_unlinked_building_does_not_loop_on_stale_done_status(self):
        with self.conn.cursor() as cur:
            cur.execute("INSERT INTO app_meta(key,value) VALUES(%s,%s)",
                        [lookup.PREFIX + str(self.id),
                         json.dumps({"state": "done", "run_id": "old", "building_id": 999})])
        self.conn.commit()
        self.assertEqual(self.client.get(f"/api/auctions/{self.id}/building-lookup")
                         .json["lookup"]["state"], "idle")
        with patch.object(lookup.subprocess, "Popen"):
            self.assertEqual(self.client.post(f"/api/auctions/{self.id}/building-lookup")
                             .json["lookup"]["state"], "running")

    def test_global_concurrency_daily_budget_and_stale_runner(self):
        with self.conn.cursor() as cur:
            for index in range(lookup.MAX_RUNNING):
                cur.execute("INSERT INTO app_meta(key,value) VALUES(%s,%s)",
                            [lookup.PREFIX + str(-index - 1), '{"state":"running"}'])
        self.conn.commit()
        with patch.object(lookup.subprocess, "Popen") as spawn:
            self.assertEqual(self.client.post(f"/api/auctions/{self.id}/building-lookup")
                             .json["lookup"]["state"], "busy")
            spawn.assert_not_called()
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM app_meta")
            cur.execute("""INSERT INTO app_meta(key,value)
              VALUES('auction_lookup_budget:' || CURRENT_DATE::text,%s)""", [str(lookup.MAX_DAILY)])
        self.conn.commit()
        self.assertEqual(self.client.post(f"/api/auctions/{self.id}/building-lookup")
                         .json["lookup"]["state"], "quota")
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM app_meta")
        self.conn.commit()
        run_id = self.claim()
        with self.conn.cursor() as cur:
            cur.execute("UPDATE app_meta SET value=%s WHERE key=%s",
                        [json.dumps({"state": "running", "run_id": "replacement"}), lookup.PREFIX + str(self.id)])
        self.conn.commit()
        with patch.object(building_registry, "_fetch_title_rows") as fetch:
            lookup.run_lookup(self.id, run_id)
            fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
