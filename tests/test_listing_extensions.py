"""Offline contracts for channel/target separation, privacy and publication."""
import ast
import copy
import json
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from flask import Flask, jsonify, request, session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import listing_extensions as ext


def source_contracts():
    tree = ast.parse(Path("app.py").read_text())
    functions = {
        "_parse_listing_krw", "_parse_whole_date", "_parse_building_info_overrides",
        "_parse_listing_ratio", "_whole_listing_values",
        "_masked_permit_number",
        "_normalize_permit_number",
        "_apply_public_business_listing_summary", "_apply_limited_whole_listing_privacy",
        "public_listings", "create_listing_request",
    }
    constants = {
        "_LISTING_TARGETS", "_WHOLE_LISTING_DEAL_TYPES", "_LISTING_DEAL_TYPES",
        "_WHOLE_OPERATION_STATUSES", "_WHOLE_DISCLOSURE_SCOPES", "_WHOLE_BUILDING_INFO_KEYS",
    }
    nodes = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in constants for t in node.targets):
            nodes.append(node)
        if isinstance(node, ast.FunctionDef) and node.name in functions:
            node = copy.deepcopy(node)
            node.decorator_list = []
            nodes.append(node)
    scope = {"datetime": datetime, "json": json, "re": __import__("re"), "request": request,
             "jsonify": jsonify, "current_user": lambda: None}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "app-contracts", "exec"), scope)
    return scope


class BusinessContractTests(unittest.TestCase):
    def setUp(self):
        self.ns = source_contracts()

    def test_all_targets_and_legacy_transfer_are_valid(self):
        for target, deal in (("unit", "매매"), ("whole", "매매"),
                             ("whole", "운영권양도"), ("business_rights", "")):
            with self.subTest(target=target, deal=deal):
                values, error = self.ns["_whole_listing_values"]({"transaction_target": target, "deal_type": deal})
                self.assertIsNone(error)
                self.assertEqual(values["transaction_target"], target)
        values, _ = self.ns["_whole_listing_values"]({"transaction_target": "business_rights"})
        self.assertEqual(values["deal_type"], "영업권양도")

    def test_business_metrics_optional_and_zero_preserved(self):
        values, error = self.ns["_whole_listing_values"]({
            "transaction_target": "business_rights", "price_krw": 0, "key_money_krw": 0,
            "monthly_rent_krw": 0, "monthly_revenue_krw": 0,
            "business_rights_info": {"occ": 0, "review_count": 0, "adr_krw": 0,
                                     "furniture_included": False},
        })
        self.assertIsNone(error)
        for key in ("price_krw", "key_money_krw", "monthly_rent_krw", "monthly_revenue_krw"):
            self.assertEqual(values[key], 0)
        self.assertEqual(values["business_rights_info"]["review_count"], 0)
        self.assertIs(values["business_rights_info"]["furniture_included"], False)

    def test_invalid_metrics_rejected(self):
        for key, value in (("occ", 101), ("rating", 5.1), ("review_count", 1.5),
                           ("adr_krw", float("nan")), ("revpar_krw", float("inf")),
                           ("staff_transfer", "yes"), ("review_count", True)):
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    ext.validate_business_info({key: value})
        self.assertEqual(ext.validate_business_info({"private_token": "never-public"}), {})

    def test_legacy_null_target_is_unit(self):
        value = self.ns["_apply_public_business_listing_summary"]({"transaction_target": None})
        self.assertEqual(value["transaction_target"], "unit")

    def test_rights_financial_gate_and_limited_identity(self):
        source = {"transaction_target": "business_rights", "building_id": 7, "lat": 1,
                  "lng": 2, "building_name": "hidden", "sgg_text": "서울특별시 마포구",
                  "umd_nm": "서교동", "photos": ["secret"], "photo_url": "secret",
                  "key_money_krw": 5000, "business_rights_info": {"facility_name": "hidden", "occ": 70}}
        value = self.ns["_apply_public_business_listing_summary"](source)
        value = self.ns["_apply_limited_whole_listing_privacy"](value)
        for key in ("building_id", "lat", "lng", "photo_url", "photos"):
            self.assertNotIn(key, value)
        self.assertNotIn("facility_name", value["business_rights_info"])
        self.assertIsNone(value["key_money_krw"])
        self.assertTrue(value["is_limited_listing"])

    def test_public_channel_predicate_does_not_publish_legacy_broker_leads(self):
        sql = ext.public_channel_sql()
        for text in ("publication_status='approved'", "broker_agent_id", "bm.status='active'", "ba.status='approved'"):
            self.assertIn(text, sql)
        with self.assertRaises(ValueError):
            ext.public_channel_sql("untrusted")

    def test_listing_filters_are_parameterized_and_channel_retained(self):
        app = Flask(__name__)
        conn, cur = MagicMock(), MagicMock()
        conn.cursor.return_value = cur
        cur.fetchall.return_value = []
        self.ns.update(get_conn=lambda: conn, current_user=lambda: None, os=__import__("os"),
                       _sido_norm_sql=lambda name: name)
        with app.test_request_context("/api/listings?channel=broker&transaction_target=business_rights"):
            response = self.ns["public_listings"]()
        self.assertTrue(response.json["ok"])
        sql, params = cur.execute.call_args.args
        self.assertEqual(params[:3], ["broker", "broker", "business_rights"])
        self.assertIn("publication_status='approved'", sql)
        self.assertIn("IN ('whole','business_rights')", sql)

    def test_invalid_listing_filters_fail_before_db(self):
        app = Flask(__name__)
        for query in ("channel=private", "transaction_target=invalid"):
            with app.test_request_context("/api/listings?" + query):
                _, status = self.ns["public_listings"]()
                self.assertEqual(status, 400)


class BrokerAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.secret_key = "offline-test-only"

    def test_role_context_and_exact_membership_required(self):
        cur = MagicMock()
        with self.app.test_request_context():
            self.assertIsNone(ext.broker_context(cur, {"id": 9}))
            cur.execute.assert_not_called()
            session.update(active_role="agent", active_business_table="agents", active_business_id=11)
            cur.fetchone.return_value = None
            self.assertIsNone(ext.broker_context(cur, {"id": 9}))
            sql, params = cur.execute.call_args.args
            self.assertEqual(params, [11, 9])
            self.assertIn("m.status='active'", sql)
            self.assertIn("a.status='approved'", sql)

    def test_migration_is_additive_and_idempotent(self):
        cur = MagicMock()
        ext.ensure_listing_extensions(cur)
        for call in cur.execute.call_args_list:
            sql = call.args[0]
            self.assertIn("IF NOT EXISTS", sql)
            self.assertNotIn("DROP", sql)
            self.assertNotIn("master_buildings", sql)

    def test_all_six_registration_combinations_and_pending_broker_review(self):
        ns = source_contracts()
        conn, cur = MagicMock(), MagicMock()
        conn.cursor.return_value = cur

        def execute(sql, params=None):
            if "SELECT phone, phone_verified" in sql:
                cur.fetchone.return_value = {"phone": "01000000000", "phone_verified": True}
            elif "FROM agents a" in sql:
                cur.fetchone.return_value = {"id": 11, "office_name": "offline test"}
            elif "FROM master_buildings" in sql:
                cur.fetchone.return_value = {"id": 7, "building_name": "offline building"}
            elif "RETURNING id" in sql:
                cur.fetchone.return_value = {"id": 100}
            else:
                cur.fetchone.return_value = {}

        cur.execute.side_effect = execute
        ns.update(
            app=self.app, current_user=lambda: {"id": 9}, get_conn=lambda: conn,
            _route_lead=lambda *a: (11, "test", []),
            _notify_lead_agents=MagicMock(return_value=([], None)),
            _urgent_tier_for_listing=lambda *a: None,
            _is_public_direct_listing=lambda *a: False,
            _best_effort_weekly_email_opt_in=lambda *a, **k: None,
        )
        for mode, publish in (("direct", False), ("broker", True), ("broker", False)):
            for target in ("unit", "whole", "business_rights"):
                with self.subTest(mode=mode, publish=publish, target=target):
                    data = dict(master_building_id=7, transaction_target=target, deal_type="매매",
                                deal_mode=mode, publish_as_broker=publish, contact_phone="01000000000",
                                price_krw=10000, business_rights_info={"occ": 0})
                    with self.app.test_request_context(json=data):
                        session.update(active_role="agent", active_business_table="agents",
                                       active_business_id=11)
                        response = ns["create_listing_request"]()
                    self.assertTrue(response.json["ok"])
                    self.assertEqual(response.json["publication_status"], "pending" if publish else None)
        # The only delivery entrypoint is mocked: never send real SMS/email.
        self.assertEqual(ns["_notify_lead_agents"].call_count, 9)


class ReviewRouteTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.secret_key = "offline-test-only"
        self.conn, self.cur = MagicMock(), MagicMock()
        self.conn.cursor.return_value = self.cur
        ext.register_listing_extension_routes(self.app, lambda f: f,
                                              lambda: {"id": 9}, lambda name: name)
        self.client = self.app.test_client()
        self.row = dict(status="submitted", agent_status="approved", active_member=True,
                        office_name="test office", owner_name="test broker", reg_number="test-reg",
                        office_address="test address", broker_phone="01000000000",
                        review_version="revision-1")

    def review(self, decision="approved", reason="", version="revision-1"):
        self.cur.fetchone.return_value = self.row
        with patch.object(ext, "get_conn", return_value=self.conn):
            return self.client.post("/api/admin/broker-listings/1/review",
                                    json=dict(decision=decision, reason=reason, review_version=version))

    def test_approval_audited_and_committed(self):
        self.assertEqual(self.review().status_code, 200)
        self.conn.commit.assert_called_once()
        self.assertTrue(any("listing_request_history" in c.args[0] for c in self.cur.execute.call_args_list))

    def test_withdrawal_cannot_be_reapproved(self):
        self.row["status"] = "철회됨"
        self.assertEqual(self.review().status_code, 409)
        self.conn.commit.assert_not_called()

    def test_revoked_membership_not_approved(self):
        self.row["active_member"] = False
        self.assertEqual(self.review().status_code, 400)
        self.conn.commit.assert_not_called()

    def test_missing_advertising_information_not_approved(self):
        self.row["reg_number"] = ""
        self.assertEqual(self.review().status_code, 400)

    def test_changed_submission_must_be_reviewed_again(self):
        self.assertEqual(self.review(version="stale-version").status_code, 409)

    def test_rejection_reason_required(self):
        self.assertEqual(self.review(decision="rejected").status_code, 400)
        self.assertEqual(self.review(decision="rejected", reason="missing information").status_code, 200)


if __name__ == "__main__":
    unittest.main()
