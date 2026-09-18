"""Focused partner favorites/weekly-consent and digest contract tests."""

import os
import re
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("SKIP_STARTUP_SCHEMA_INIT", "1")

import app as app_module
import weekly_digest as digest


ROOT = Path(__file__).resolve().parents[1]


class Cursor:
    def __init__(self, fetch_rows=None, fetch_one=None):
        self.fetch_rows = list(fetch_rows or [])
        self.fetch_one = fetch_one
        self.queries = []
        self.params = []
        self.rowcount = 1

    def execute(self, query, params=None):
        self.queries.append(query)
        self.params.append(params)

    def fetchall(self):
        return self.fetch_rows

    def fetchone(self):
        return self.fetch_one

    def close(self):
        pass


class Conn:
    def __init__(self, cursor):
        self.cursor_obj = cursor
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        pass


class SequenceCursor(Cursor):
    def __init__(self, rows):
        super().__init__()
        self.rows = iter(rows)

    def fetchone(self):
        return next(self.rows)


class PartnerFavoritesWeeklyTests(unittest.TestCase):
    def test_partner_schema_has_one_owner_and_non_null_uuid_tokens(self):
        source = (ROOT / "db.py").read_text(encoding="utf-8")
        self.assertIn(
            "CHECK (num_nonnulls(agent_id, operator_id, loan_consultant_id) = 1)",
            source,
        )
        self.assertGreaterEqual(
            source.count("weekly_unsubscribe_token UUID NOT NULL DEFAULT gen_random_uuid()"),
            3,
        )
        for table in ("agents", "operators", "loan_consultants"):
            self.assertIn(
                f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS "
                "weekly_unsubscribe_token UUID DEFAULT gen_random_uuid()",
                source,
            )
            self.assertIn(
                f"ALTER TABLE {table} ALTER COLUMN weekly_unsubscribe_token SET NOT NULL",
                source,
            )
            self.assertIn(
                f"UPDATE {table} SET weekly_unsubscribe_token = gen_random_uuid()",
                source,
            )

    def test_favorites_do_not_change_consent_and_put_is_the_only_opt_in(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        add_source = source[source.index("def _partner_favorites_add"):source.index("def _partner_favorites_remove")]
        self.assertNotIn("weekly_email_enabled=TRUE", add_source)
        pref_source = source[source.index("def _partner_weekly_email"):source.index('@app.route("/api/agent/favorites"')]
        self.assertIn("methods=[\"GET\", \"PUT\"]", source)
        self.assertIn("SET weekly_email_enabled=%s", pref_source)
        self.assertIn("if not isinstance(raw, bool)", pref_source)

    def test_delete_is_owner_scoped_by_building_not_favorite_row(self):
        cursor = Cursor(fetch_one={"id": 77})
        conn = Conn(cursor)
        with app_module.app.test_request_context(
            "/api/agent/favorites/123", method="DELETE"
        ), patch.object(
            app_module, "_partner_favorite_owner",
            return_value={"id": 9, "status": "approved"},
        ), patch.object(app_module, "get_conn", return_value=conn):
            response = app_module._partner_favorites_remove("agent", 123)
        self.assertEqual(response[1] if isinstance(response, tuple) else response.status_code, 200)
        self.assertIn("master_building_id=%s", cursor.queries[0])
        self.assertNotIn("WHERE id=%s", cursor.queries[0])
        self.assertEqual(cursor.params[0], [123, 9])

    def test_favorite_post_leaves_weekly_consent_unchanged(self):
        cursor = SequenceCursor([
            {"id": 123, "building_name": "검색 단지", "road_address": "주소",
             "sgg_text": "구", "umd_nm": "동", "jibun": "1",
             "lodging_type": "호텔", "lodging_subtype": None},
            None, {"c": 0}, {"id": 88}, {"weekly_email_enabled": False},
        ])
        conn = Conn(cursor)
        with app_module.app.test_request_context(
            "/api/agent/favorites", method="POST",
            json={"master_building_id": 123},
        ), patch.object(
            app_module, "_partner_favorite_owner",
            return_value={"id": 9, "status": "approved"},
        ), patch.object(app_module, "get_conn", return_value=conn):
            response = app_module._partner_favorites_add("agent")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(any("weekly_email_enabled=TRUE" in q for q in cursor.queries))
        self.assertFalse(any("UPDATE agents" in q for q in cursor.queries))

    def test_partner_delete_routes_use_building_id(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn('/api/agent/favorites/<int:master_building_id>', source)
        self.assertIn('/api/operator/favorites/<int:master_building_id>', source)
        self.assertIn('/api/loan-consultant/favorites/<int:master_building_id>', source)

    def test_max_and_idempotency_guards_are_present(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        add_source = source[source.index("def _partner_favorites_add"):source.index("def _partner_favorites_remove")]
        self.assertIn("pg_advisory_xact_lock", add_source)
        self.assertIn(">= 30", add_source)
        self.assertIn("idempotent", add_source)
        self.assertIn("if not duplicate", add_source)

    def test_partner_cohorts_are_deterministic(self):
        values = {
            digest.cohort_for_partner("agent", 7),
            digest.cohort_for_partner("operator", 7),
            digest.cohort_for_partner("loan_consultant", 7),
        }
        self.assertTrue(values <= {"tue", "thu"})
        for kind in ("agent", "operator", "loan_consultant"):
            self.assertEqual(
                digest.cohort_for_partner(kind, 42),
                digest.cohort_for_partner(kind, 42),
            )
        self.assertNotIn("return hash(", (ROOT / "weekly_digest.py").read_text(encoding="utf-8"))

    def test_normalized_recipients_include_only_database_eligible_rows(self):
        cursor = Cursor(fetch_rows=[
            {"recipient_type": "agent", "id": 1, "email": "a@example.test",
             "name": "A", "weekly_email_enabled": True},
            {"recipient_type": "operator", "id": 2, "email": "o@example.test",
             "name": "O", "weekly_email_enabled": True},
        ])
        rows = digest._get_weekly_recipients(cursor, "tue")
        self.assertEqual([r["recipient_type"] for r in rows], ["agent"])
        cursor.fetch_rows = [
            {"recipient_type": "operator", "id": 2, "email": "o@example.test",
             "name": "O", "weekly_email_enabled": True},
        ]
        self.assertEqual(
            [r["recipient_type"] for r in digest._get_weekly_recipients(cursor, "thu")],
            ["operator"],
        )
        query = cursor.queries[0]
        self.assertIn("status='approved'", query)
        self.assertIn("weekly_email_enabled IS FALSE", query)
        self.assertIn("weekly_email_updated_at IS NOT NULL", query)
        self.assertIn("updated_weekly_email_at IS NOT NULL", query)
        self.assertIn("FROM agents", query)
        self.assertIn("FROM operators", query)
        self.assertIn("FROM loan_consultants", query)
        self.assertEqual(query.count("status='approved'"), 3)
        self.assertIn("recipient_type", query)

    def test_claim_is_owner_aware_and_fenced(self):
        cursor = Cursor(fetch_one={
            "id": 3, "tracking_token": "track", "claim_token": "lease", "attempts": 1,
        })
        claim = digest._claim_delivery(cursor, 12, date(2026, 9, 15), "tue", "agent")
        self.assertEqual(claim["claim_token"], "lease")
        self.assertIn("agent_id", cursor.queries[0])
        self.assertIn("recipient_type", cursor.queries[0])
        finish = Cursor()
        digest._finish_delivery(finish, 3, "lease", True, "ok", "subject")
        self.assertIn("claim_token=%s", finish.queries[0])
        self.assertIn("status='sending'", finish.queries[0])

    def test_partner_scope_is_favorites_union_live_badges_without_regions(self):
        source = (ROOT / "weekly_digest.py").read_text(encoding="utf-8")
        scope = source[source.index("def _personalize_partner_recipient"):source.index("def _send_claimed_recipient")]
        self.assertIn("partner_favorites", scope)
        self.assertIn("UNION", scope)
        self.assertIn("has_priority_badge=TRUE", scope)
        self.assertIn("premium_expires_at IS NULL OR premium_expires_at > NOW()", scope)
        self.assertNotRegex(scope, r"(agent|operator|loan_consultant)_region")

    def test_successful_user_and_partner_send_paths_recheck_then_send(self):
        for recipient_type in ("user", "agent"):
            cursor = Cursor(fetch_one={"enabled": True})
            conn = Conn(cursor)
            user = {
                "id": 4, "email": "recipient@example.test", "name": "받는이",
                "recipient_type": recipient_type,
            }
            with patch.object(digest, "build_html", return_value="<html>"), \
                    patch.object(digest, "send_email", return_value=(True, "sent")) as sender:
                ok, message = digest._send_claimed_recipient(
                    conn, cursor, user,
                    {"id": 10, "tracking_token": "stable-token",
                     "claim_token": "lease-token", "attempts": 1},
                    "[subject]", [], {}, [], [], [], [], {}, None,
                    "https://example.test/unsubscribe", 0, {}, date(2026, 9, 14),
                    "tue", recipient_type=recipient_type,
                )
            self.assertTrue(ok, (recipient_type, message))
            sender.assert_called_once()
            self.assertIn("SELECT", cursor.queries[0])
            self.assertIn("weekly_email_enabled", cursor.queries[0])

    def test_partner_unsubscribe_requires_type_and_uses_partner_token(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        unsubscribe = source[source.index("def unsubscribe_weekly_email"):source.index("def _agent_me_data")]
        self.assertIn("recipient_type", unsubscribe)
        self.assertIn("weekly_unsubscribe_token", unsubscribe)
        self.assertIn("weekly_email_enabled=FALSE", unsubscribe)
        digest_source = (ROOT / "weekly_digest.py").read_text(encoding="utf-8")
        self.assertIn("quote(recipient_type)", digest_source)

    def test_dashboard_uses_search_and_preserves_consent_on_favorite_changes(self):
        for name in ("agent", "operator", "loan_consultant"):
            source = (ROOT / "static" / f"{name}_dashboard.html").read_text(encoding="utf-8")
            self.assertIn("partnerFavoriteSearch", source)
            self.assertIn("/buildings/search?q=", source)
            self.assertNotIn("partnerFavoriteBuildingId", source)
            self.assertIn("승인된 파트너는 주간 정보를 기본으로 받습니다.", source)
            self.assertIn("아래 토글로 언제든지 끌 수 있으며", source)
            self.assertNotIn("동의 체크를 직접 켜야", source)
            self.assertIn("favorites/${id}", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)