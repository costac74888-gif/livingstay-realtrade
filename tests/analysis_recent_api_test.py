import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import app as server


class RecentAnalysisMemoryDB:
    """Small route-level fake for recent-history behavior; no project DB writes."""

    def __init__(self):
        self.buildings = {
            building_id: {
                "building_name": "건물 {}".format(building_id),
                "road_address": "도로명 {}".format(building_id),
                "jibun_address": "지번 {}".format(building_id),
            }
            for building_id in range(1, 50)
        }
        self.rows = {}
        self.clock = datetime(2026, 9, 25, tzinfo=timezone.utc)

    def connection(self):
        return RecentAnalysisConnection(self)


class RecentAnalysisConnection:
    def __init__(self, database):
        self.database = database

    def cursor(self):
        return RecentAnalysisCursor(self.database)

    def commit(self):
        pass

    def close(self):
        pass


class RecentAnalysisCursor:
    def __init__(self, database):
        self.database = database
        self.one = None
        self.many = []

    def execute(self, query, params=None):
        sql = " ".join(query.split())
        params = tuple(params or ())
        self.one = None
        self.many = []

        if sql.startswith("SELECT id FROM master_buildings WHERE id ="):
            building_id = params[0]
            if building_id in self.database.buildings:
                self.one = {"id": building_id}
        elif sql.startswith("SELECT pg_advisory_xact_lock"):
            return
        elif sql.startswith("INSERT INTO user_recent_analysis"):
            user_id, building_id, mode = params
            self.database.clock += timedelta(microseconds=1)
            self.database.rows[(user_id, building_id)] = {
                "last_mode": mode,
                "analyzed_at": self.database.clock,
            }
        elif sql.startswith("WITH ranked AS"):
            user_id, delete_user_id = params
            assert user_id == delete_user_id
            user_rows = sorted(
                (
                    (key, value)
                    for key, value in self.database.rows.items()
                    if key[0] == user_id
                ),
                key=lambda entry: (entry[1]["analyzed_at"], entry[0][1]),
                reverse=True,
            )
            for key, _ in user_rows[30:]:
                del self.database.rows[key]
        elif sql.startswith("SELECT recent.building_id,"):
            user_id = params[0]
            user_rows = sorted(
                (
                    (key[1], value)
                    for key, value in self.database.rows.items()
                    if key[0] == user_id
                ),
                key=lambda entry: (entry[1]["analyzed_at"], entry[0]),
                reverse=True,
            )[:30]
            for building_id, value in user_rows:
                building = self.database.buildings[building_id]
                self.many.append({
                    "building_id": building_id,
                    "building_name": building["building_name"] or "건물명 미확인",
                    "address": building["road_address"] or building["jibun_address"] or "",
                    "last_mode": value["last_mode"],
                    "analyzed_at": value["analyzed_at"],
                })
        else:
            raise AssertionError("Unexpected SQL in recent-analysis test: " + sql)

    def fetchone(self):
        return self.one

    def fetchall(self):
        return list(self.many)

    def close(self):
        pass


class AnalysisRecentApiTests(unittest.TestCase):
    def setUp(self):
        self.database = RecentAnalysisMemoryDB()
        self.client = server.app.test_client()
        self.other_client = server.app.test_client()
        self.auth_patch = patch.object(
            server,
            "current_user",
            side_effect=lambda: (
                {"id": server.session.get("user_id")}
                if server.session.get("user_id")
                else None
            ),
        )
        self.auth_patch.start()
        self.conn_patch = patch.object(
            server, "get_conn", side_effect=self.database.connection
        )
        self.conn_patch.start()
        with self.client.session_transaction() as session:
            session["user_id"] = 11
        with self.other_client.session_transaction() as session:
            session["user_id"] = 22

    def tearDown(self):
        self.conn_patch.stop()
        self.auth_patch.stop()

    def test_login_is_required_for_get_and_post(self):
        client = server.app.test_client()
        self.assertEqual(client.get("/api/analysis/recent").status_code, 401)
        self.assertEqual(
            client.post(
                "/api/analysis/recent",
                json={"building_id": 1, "mode": "property"},
            ).status_code,
            401,
        )
        admin_client = server.app.test_client()
        with admin_client.session_transaction() as session:
            session["admin"] = True
        self.assertEqual(admin_client.get("/api/analysis/recent").status_code, 401)
        partner_client = server.app.test_client()
        with partner_client.session_transaction() as session:
            session["agent_id"] = 91
        self.assertEqual(partner_client.get("/api/analysis/recent").status_code, 401)

    def test_deduplicates_per_user_and_returns_authoritative_building_data(self):
        self.database.buildings[1]["building_name"] = "마스터 건물명"
        first = self.client.post(
            "/api/analysis/recent",
            json={"building_id": 1, "mode": "property", "building_name": "조작 이름"},
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json["item"]["building_name"], "마스터 건물명")
        self.assertEqual(first.json["item"]["address"], "도로명 1")
        self.assertEqual(
            set(first.json),
            {"ok", "items", "limit", "item"},
        )
        self.assertEqual(
            set(first.json["item"]),
            {"building_id", "building_name", "address", "last_mode", "analyzed_at"},
        )

        updated = self.client.post(
            "/api/analysis/recent",
            json={"building_id": 1, "mode": "rental"},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(len(updated.json["items"]), 1)
        self.assertEqual(updated.json["item"]["last_mode"], "rental")

        other = self.other_client.get("/api/analysis/recent")
        self.assertEqual(other.status_code, 200)
        self.assertEqual(other.json["items"], [])

        self.assertEqual(
            self.other_client.post(
                "/api/analysis/recent",
                json={"building_id": 1, "mode": "operation"},
            ).status_code,
            200,
        )
        own = self.client.get("/api/analysis/recent")
        other = self.other_client.get("/api/analysis/recent")
        self.assertEqual(own.json["items"][0]["last_mode"], "rental")
        self.assertEqual(other.json["items"][0]["last_mode"], "operation")

    def test_only_the_thirty_most_recent_distinct_buildings_are_kept(self):
        for building_id in range(1, 32):
            response = self.client.post(
                "/api/analysis/recent",
                json={"building_id": building_id, "mode": "property"},
            )
            self.assertEqual(response.status_code, 200)
        response = self.client.get("/api/analysis/recent")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["limit"], 30)
        self.assertEqual(len(response.json["items"]), 30)
        ids = [item["building_id"] for item in response.json["items"]]
        self.assertIn(31, ids)
        self.assertNotIn(1, ids)
        self.assertEqual(len(set(ids)), 30)

    def test_invalid_building_ids_modes_and_missing_buildings_are_rejected(self):
        invalid_payloads = [
            {"building_id": True, "mode": "property"},
            {"building_id": -1, "mode": "property"},
            {"building_id": 1.5, "mode": "property"},
            {"building_id": "abc", "mode": "property"},
            {"building_id": 1, "mode": "admin"},
            {"building_id": 1, "mode": ""},
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                self.assertEqual(
                    self.client.post("/api/analysis/recent", json=payload).status_code,
                    400,
                )
        self.assertEqual(
            self.client.post(
                "/api/analysis/recent",
                json={"building_id": 999, "mode": "property"},
            ).status_code,
            404,
        )
        self.assertEqual(self.client.get("/api/analysis/recent").json["items"], [])


if __name__ == "__main__":
    unittest.main()