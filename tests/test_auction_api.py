"""온비드 네트워크/알림을 발송하지 않는 공개 API·권한·노출기간 검사."""
import json
import unittest
import uuid
from unittest.mock import patch, MagicMock

import app as app_module
import auction_service
from auction_domain import CURRENT_SQL, EFFECTIVE_STATUS_SQL, ELIGIBLE_SQL
from db import get_conn


class AuctionApiTest(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()
        self.client.environ_base["HTTP_USER_AGENT"] = "Mozilla/5.0 AuctionValidation"

    def test_public_list_filters_and_private_field_exclusion(self):
        for query in ("", "?sort=discount", "?sort=new", "?status=bidding", "?category=호텔", "?ratio_min=30&ratio_max=100&failed_min=2"):
            response = self.client.get("/api/auctions" + query)
            self.assertEqual(response.status_code, 200)
            data = response.get_json()
            self.assertTrue(data["ok"])
            self.assertLessEqual(len(data["items"]), 20)
            self.assertEqual(len({i["source_item_id"] for i in data["items"]}), len(data["items"]))
            for item in data["items"]:
                self.assertNotIn("raw", item)
                self.assertNotIn("detail_fingerprint", item)
                if "status=bidding" in query:
                    self.assertEqual(item["status"], "bidding")

    def test_officetel_removed_from_public_surfaces_without_destroying_history(self):
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT a.id FROM auction_items a WHERE NOT {ELIGIBLE_SQL} LIMIT 1")
                excluded = cur.fetchone()
                cur.execute(CURRENT_SQL + " SELECT COUNT(*) AS n FROM current_auctions")
                expected_count = cur.fetchone()["n"]
        if excluded:
            item_id = excluded["id"]
            for path in (f"/api/auctions/{item_id}", f"/api/auctions/{item_id}/survey-info",
                         f"/auctions/{item_id}", f"/auctions/{item_id}/survey"):
                self.assertEqual(self.client.get(path).status_code, 404, path)
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT id FROM auction_items WHERE id=%s", [item_id])
                    self.assertIsNotNone(cur.fetchone(), "Keep historical references intact")
        response = self.client.get("/api/auctions?page_size=100").get_json()
        self.assertEqual(response["total"], expected_count)
        self.assertTrue(all("오피스텔" not in (item["usage_name"] or "") and
                            "오피스텔" not in (item["lodging_category"] or "") for item in response["items"]))
        for item in response["items"]:
            self.assertIn("management_no", item)
            for field in ("land_area_m2", "building_area_m2"):
                self.assertTrue(item[field] is None or isinstance(item[field], (int, float)))
        self.assertEqual(self.client.get("/api/auctions?category=오피스텔").status_code, 400)
        self.assertTrue(all(item["lodging_category"] != "오피스텔" for item in
                            self.client.get("/api/auctions/map?bbox=124,33,132,39").get_json()["items"]))

    def test_invalid_filters_and_nonfinite_bbox(self):
        for path in ("/api/auctions?sort=wrong", "/api/auctions?ratio_max=nan",
                     "/api/auctions?status=bad", "/api/auctions?page=-1",
                     "/api/auctions/map?bbox=NaN,33,132,39", "/api/auctions/map?bbox=132,39,124,33"):
            self.assertEqual(self.client.get(path).status_code, 400)

    def test_numeric_sort_directions_and_missing_values_last(self):
        for sort, field, descending in (
            ("deadline", "bid_end_at", False),
            ("deadline_desc", "bid_end_at", True),
            ("appraisal_asc", "appraisal_price", False),
            ("appraisal_desc", "appraisal_price", True),
            ("price_asc", "min_bid_price", False),
            ("price_desc", "min_bid_price", True),
            ("new_asc", "first_seen_at", False),
            ("new", "first_seen_at", True),
            ("ratio_asc", "min_bid_ratio", False),
            ("ratio_desc", "min_bid_ratio", True),
            ("failed_asc", "failed_count", False),
            ("failed_desc", "failed_count", True),
        ):
            with self.subTest(sort=sort):
                response = self.client.get("/api/auctions?sort=" + sort)
                self.assertEqual(response.status_code, 200)
                items = response.get_json()["items"]
                self.assertTrue(items)
                values = [item[field] for item in items if item[field] is not None]
                self.assertEqual(values, sorted(values, reverse=descending))
                missing_seen = False
                for item in items:
                    if item[field] is None:
                        missing_seen = True
                    else:
                        self.assertFalse(missing_seen)
                self.assertEqual(len({item["source_item_id"] for item in items}), len(items))

    def test_allowed_page_sizes_and_pagination(self):
        for size in (10, 20, 50, 100):
            with self.subTest(size=size):
                first = self.client.get(f"/api/auctions?page_size={size}&sort=price_asc").get_json()
                second = self.client.get(f"/api/auctions?page_size={size}&sort=price_asc&page=2").get_json()
                self.assertEqual(first["page_size"], size)
                self.assertEqual(len(first["items"]), min(size, first["total"]))
                self.assertEqual(first["pages"], (first["total"] + size - 1) // size)
                self.assertEqual(second["page"], 2)
                self.assertFalse({item["id"] for item in first["items"]} & {item["id"] for item in second["items"]})
        for size in ("0", "-1", "11", "101", "100000", "nan"):
            self.assertEqual(self.client.get("/api/auctions?page_size=" + size).status_code, 400)

    def test_legacy_pages_redirect_and_success_timestamp(self):
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id,master_building_id FROM auction_items ORDER BY id LIMIT 1")
                item = cur.fetchone()
        for suffix in ("", "/survey"):
            response = self.client.get(f"/auctions/{item['id']}" + suffix)
            self.assertEqual(response.status_code, 301)
            resolved = self.client.get("/api/auctions/" + str(item["id"])).get_json()["item"]
            self.assertEqual(response.headers["Location"],
                             auction_service.auction_deep_link(item["id"], resolved["master_building_id"]))
        self.assertIn("last_success_at", self.client.get("/api/auctions").get_json())
        for key in ("status", "category", "address", "area"):
            for direction in ("asc", "desc"):
                self.assertEqual(self.client.get(f"/api/auctions?sort={key}_{direction}").status_code, 200)

    def test_failure_streak_and_preserved_ledger(self):
        from sync_onbid import record_sync_outcome
        conn = get_conn()
        key = "test:onbid-outcome:" + uuid.uuid4().hex
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS n FROM auction_items")
                before = cur.fetchone()["n"]
                cur.execute("SELECT COUNT(*) AS n FROM admin_notifications WHERE title='온비드 공매 수집 2회 연속 실패'")
                alerts = cur.fetchone()["n"]
                record_sync_outcome(cur, {"state":"failed"}, key)
                cur.execute("SELECT COUNT(*) AS n FROM admin_notifications WHERE title='온비드 공매 수집 2회 연속 실패'")
                self.assertEqual(cur.fetchone()["n"], alerts)
                record_sync_outcome(cur, {"state":"failed"}, key)
                cur.execute("SELECT COUNT(*) AS n FROM admin_users")
                admins = cur.fetchone()["n"]
                cur.execute("SELECT COUNT(*) AS n FROM admin_notifications WHERE title='온비드 공매 수집 2회 연속 실패'")
                self.assertEqual(cur.fetchone()["n"], alerts + admins)
                record_sync_outcome(cur, {"state":"waiting_quota","list_complete":False}, key)
                cur.execute("SELECT value FROM app_meta WHERE key=%s", [key + ":failure_streak"])
                self.assertEqual(cur.fetchone()["value"], "2")
                record_sync_outcome(cur, {"state":"done","list_complete":True}, key)
                cur.execute("SELECT value FROM app_meta WHERE key=%s", [key + ":failure_streak"])
                self.assertEqual(cur.fetchone()["value"], "0")
                cur.execute("SELECT COUNT(*) AS n FROM auction_items")
                self.assertEqual(cur.fetchone()["n"], before)
        finally:
            conn.rollback()
            conn.close()

    def test_detail_photos_rounds_building_and_unknown_id(self):
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id,master_building_id FROM auction_items WHERE master_building_id IS NOT NULL LIMIT 1")
                row = cur.fetchone()
        self.assertIsNotNone(row)
        response = self.client.get("/api/auctions/" + str(row["id"]))
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertNotIn("raw", data["item"])
        self.assertEqual(data["building"]["id"], row["master_building_id"])
        self.assertEqual(sum(bool(r["is_current"]) for r in data["rounds"]), 1)
        self.assertTrue(all(not any("user_id" in k for k in p) for p in data["photos"]))
        response = self.client.get("/api/building/" + str(row["master_building_id"]) + "/auctions")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["items"])
        self.assertEqual(self.client.get("/api/auctions/2147483647").status_code, 404)

    def test_list_only_detail_resolves_existing_building_and_photo(self):
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f""" SELECT a.id FROM auction_items a
                  WHERE a.source_item_id='2026-0500-027097' AND {ELIGIBLE_SQL}
                  AND a.raw->'list'->>'thnlImgUrlAdr' IS NOT NULL
                  AND NOT EXISTS (SELECT 1 FROM auction_photos p
                    JOIN auction_items owner ON owner.id=p.auction_item_id
                    WHERE owner.source=a.source AND owner.source_item_id=a.source_item_id)
                  LIMIT 1""")
                row = cur.fetchone()
        self.assertIsNotNone(row, "Validate a real unmatched item with a list-only thumbnail")
        response = self.client.get("/api/auctions/" + str(row["id"]))
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIsNotNone(data["building"])
        self.assertEqual(data["building"]["id"], data["item"]["master_building_id"])
        self.assertEqual(data["building"]["jibun_address"], "부산광역시 해운대구 중동 1124-8")
        self.assertTrue(data["item"]["thumbnail_url"])
        self.assertEqual(data["photos"][0]["url"], data["item"]["thumbnail_url"])
        self.assertEqual(data["photos"][0]["source"], "auction")
        self.assertNotIn("raw", data["item"])
        listed = next(item for item in self.client.get("/api/auctions?page_size=100").get_json()["items"]
                      if item["source_item_id"] == data["item"]["source_item_id"])
        self.assertEqual(listed["master_building_id"], data["building"]["id"])
        history = self.client.get("/api/building/" + str(data["building"]["id"]) + "/auctions").get_json()
        self.assertIn(row["id"], [item["id"] for item in history["items"]])
        self.assertIn(data["item"]["thumbnail_url"], [photo["url"] for photo in history["photos"]])
        survey = self.client.get("/api/auctions/" + str(row["id"]) + "/survey-info").get_json()
        self.assertIsNone(survey["item"])
        self.assertTrue(survey["membership_access"]["required"])

    def test_detail_photo_fallback_safety_and_existing_photo_priority(self):
        item = {"id": 123, "thumbnail_url": "https://www.onbid.co.kr/list.jpg"}
        photo = {"id": 1, "url": "https://www.onbid.co.kr/detail.jpg", "sort_order": 0}
        self.assertEqual(auction_service.auction_detail_photos([photo, photo], item),
                         [{**photo, "source": "auction"}])
        self.assertEqual(auction_service.auction_detail_photos([], item)[0]["url"],
                         item["thumbnail_url"])
        self.assertEqual(auction_service.auction_detail_photos(
            [{"url": "javascript:alert(1)"}], item)[0]["url"], item["thumbnail_url"])
        for url in (None, "", "javascript:alert(1)", "https://www.onbid.co.kr/x?serviceKey=secret"):
            self.assertEqual(auction_service.auction_detail_photos(
                [], {**item, "thumbnail_url": url}), [])

    def test_admin_auth_and_detached_claim_contract(self):
        self.assertEqual(self.client.get("/api/admin/onbid-status").status_code, 401)
        self.assertEqual(self.client.post("/api/admin/sync-onbid").status_code, 401)
        key = "test:onbid:" + uuid.uuid4().hex
        with self.client.session_transaction() as sess:
            sess["admin"] = True
        process = MagicMock()
        process.wait.return_value = 0
        try:
            with patch.object(auction_service, "STATUS_KEY", key), patch.object(app_module.subprocess, "Popen", return_value=process) as spawn:
                response = self.client.post("/api/admin/sync-onbid", headers={"Sec-Fetch-Site": "same-origin"})
                self.assertEqual(response.status_code, 202)
                self.assertTrue(spawn.call_args.kwargs["start_new_session"])
                self.assertIn("sync_onbid.py", " ".join(spawn.call_args.args[0]))
                self.assertEqual(self.client.post("/api/admin/sync-onbid").status_code, 409)
                self.assertEqual(self.client.post("/api/admin/sync-onbid", headers={"Sec-Fetch-Site": "cross-site"}).status_code, 403)
                response = self.client.get("/api/admin/onbid-status")
                self.assertEqual(response.status_code, 200)
        finally:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM app_meta WHERE key=%s", [key])

    def test_watch_requires_login(self):
        for method in ("get", "post", "delete"):
            self.assertEqual(getattr(self.client, method)("/api/building/1/auction-watch").status_code, 401)

    def test_new_auction_notification_is_opt_in_and_idempotent(self):
        from sync_onbid import notify_auction_watchers
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM users ORDER BY id LIMIT 1")
                user = cur.fetchone()
                cur.execute("""SELECT a.id,a.master_building_id,b.building_name,b.road_address,
                  a.source,a.source_item_id,a.sale_kind,a.min_bid_price
                  FROM auction_items a JOIN master_buildings b ON b.id=a.master_building_id
                  WHERE a.detail_fingerprint IS NOT NULL LIMIT 1""")
                item = dict(cur.fetchone())
                cur.execute("""INSERT INTO user_favorites(user_id,building_name,address,master_building_id)
                  VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                            [user["id"], item["building_name"], item["road_address"], item["master_building_id"]])
                cur.execute("""INSERT INTO auction_watches(user_id,master_building_id,created_at)
                  VALUES(%s,%s,NOW()-INTERVAL '1 day') ON CONFLICT(user_id,master_building_id)
                  DO UPDATE SET created_at=EXCLUDED.created_at,enabled=TRUE""",
                            [user["id"], item["master_building_id"]])
                cur.execute("SELECT COUNT(*) AS n FROM notifications WHERE user_id=%s", [user["id"]])
                before = cur.fetchone()["n"]
                notify_auction_watchers(cur, item["id"], item)
                notify_auction_watchers(cur, item["id"], item)
                cur.execute("SELECT COUNT(*) AS n FROM notifications WHERE user_id=%s", [user["id"]])
                self.assertEqual(cur.fetchone()["n"], before + 1)
                cur.execute("""SELECT m.value FROM app_meta m JOIN notifications n
                  ON m.key='auction_notification_link:' || n.id::text
                  WHERE n.user_id=%s ORDER BY n.id DESC LIMIT 1""", [user["id"]])
                self.assertEqual(cur.fetchone()["value"], auction_service.auction_deep_link(item["id"], item["master_building_id"]))
                cur.execute("UPDATE auction_watches SET enabled=FALSE WHERE user_id=%s AND master_building_id=%s",
                            [user["id"], item["master_building_id"]])
                notify_auction_watchers(cur, item["id"], {**item, "source_item_id": "test-" + uuid.uuid4().hex})
                cur.execute("SELECT COUNT(*) AS n FROM notifications WHERE user_id=%s", [user["id"]])
                self.assertEqual(cur.fetchone()["n"], before + 1)
        finally:
            # 알림·관심단지·설정·멱등 키 모두 미커밋 상태로 검사한 뒤 폐기한다.
            conn.rollback()
            conn.close()

    def test_visibility_retention_next_round_and_live_time(self):
        conn = get_conn()
        unique = uuid.uuid4().hex
        try:
            with conn.cursor() as cur:
                for ident, condition, state, age, round_no, start in (
                    ("sold", "1", "sold", "31 days", 1, "-1 day"),
                    ("canceled", "1", "canceled", "8 days", 1, "-1 day"),
                    ("failed", "1", "failed", "1 day", 1, "-1 day"),
                    ("next", "1", "failed", "1 day", 1, "-1 day"),
                    ("next", "2", "scheduled", "0 days", 2, "3 days"),
                    ("live", "1", "scheduled", "0 days", 1, "-1 hour"),
                ):
                    cur.execute("""INSERT INTO auction_items(source,source_item_id,pbct_cdtn_no,status,
                      status_changed_at,round_no,bid_start_at,bid_end_at)
                      VALUES('manual',%s,%s,%s,NOW()-%s::interval,%s,NOW()+%s::interval,NOW()+INTERVAL '5 days')""",
                                [unique + ident, condition, state, age, round_no, start])
                cur.execute(CURRENT_SQL + f""" SELECT source_item_id,({EFFECTIVE_STATUS_SQL}) AS state
                  FROM current_auctions a WHERE a.source='manual' AND a.source_item_id LIKE %s""", [unique + "%"])
                found = {r["source_item_id"][len(unique):]: r["state"] for r in cur.fetchall()}
                self.assertEqual(found, {"failed": "failed", "next": "scheduled", "live": "bidding"})
        finally:
            conn.rollback()
            conn.close()


if __name__ == "__main__":
    unittest.main()