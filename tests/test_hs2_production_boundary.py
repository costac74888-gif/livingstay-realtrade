"""Negative publish mutations: owned PostgreSQL only, no provider calls."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.hs2_production_preflight import check_publish_flow, run_probe


class ProductionBoundaryTests(unittest.TestCase):
    def rejected(self, reason, **mutation):
        code, log = run_probe(**mutation)
        self.assertEqual(code, 42, log[-4000:])
        self.assertIn(reason, log)
        self.assertNotIn("PRODUCTION_BOUNDARY_PASS", log)

    def test_approved_production_and_unused_fixture_imports_pass(self):
        code, log = run_probe(app_suffix="""
from hs2_admin.fixtures import create_fixture_app as unused_admin_factory
from hs2_workspace.fixtures import create_fixture_app as unused_workspace_factory
from hs2_finance.adapter import OwnedSandbox as unused_provider_type
""")
        self.assertEqual(code, 0, log[-4000:])
        self.assertIn("PRODUCTION_BOUNDARY_PASS", log)

    def test_admin_factory_construction_is_rejected_before_db_access(self):
        self.rejected("PRODUCTION_FIXTURE_FACTORY", app_suffix="""
from hs2_admin.fixtures import create_fixture_app as factory_alias
unused_result = factory_alias(initialize=False)
""")

    def test_workspace_factory_replacing_wsgi_app_is_rejected(self):
        self.rejected("PRODUCTION_FIXTURE_FACTORY", app_suffix="""
from hs2_workspace.fixtures import create_fixture_app as factory_alias
app = factory_alias(initialize=False)
""")

    def test_fixture_callback_registered_but_not_called_is_rejected(self):
        self.rejected("PRODUCTION_FIXTURE_REFERENCE", app_suffix="""
from hs2_workspace.fixtures import create_fixture_app as renamed_callback
app.add_url_rule('/unexpected-fixture', view_func=renamed_callback)
""")

    def test_financial_seed_called_is_rejected(self):
        self.rejected("PRODUCTION_FIXTURE_FACTORY", app_suffix="""
from hs2_finance.fixture_http import seed_paid
seed_paid(app)
""")

    def test_owned_payment_provider_constructor_is_rejected(self):
        self.rejected("PRODUCTION_FIXTURE_FACTORY", app_suffix="""
from hs2_finance.adapter import OwnedSandbox as Gateway
app.payment_provider = Gateway()
""")

    def test_mock_provider_reachable_through_repository_is_rejected(self):
        self.rejected("PRODUCTION_SANDBOX_PROVIDER", app_suffix="""
from hs2_finance.api import create_blueprint
class MockGateway:
    sandbox = True
class FinancePort:
    def __init__(self):
        self.provider = MockGateway()
repo = FinancePort()
app.register_blueprint(create_blueprint(repo,
    current_consumer=lambda:None, current_operator=lambda:None,
    consumer_csrf=lambda:'unused', operator_csrf=lambda:'unused',
    allow_request=lambda:True))
""")

    def test_anonymous_consumer_cannot_get_inline_default_actor(self):
        self.rejected("PRODUCTION_DEFAULT_ACTOR", app_suffix="""
from hs2_workspace.api import create_blueprint
app.register_blueprint(create_blueprint(object(),
    current_consumer=lambda:{'user_id':1,'status':'active','phone_verified':True},
    current_operator=lambda:None,csrf_for=lambda who:'unused',
    allow_request=lambda:True))
""")

    def test_development_session_flag_cannot_grant_admin_role(self):
        self.rejected("PRODUCTION_DEFAULT_ACTOR", app_suffix="""
class AdminPort:
    def __init__(self):
        self.resolve_admin = lambda:700 if session.get('fixture_admin') else None
app.admin_repository = AdminPort()
""")

    def test_valid_anonymous_resolvers_do_not_fail_by_source_presence(self):
        code, log = run_probe(app_suffix="""
from hs2_workspace.api import create_blueprint
app.register_blueprint(create_blueprint(object(),
    current_consumer=lambda:None,current_operator=lambda:None,
    csrf_for=lambda who:'unused',allow_request=lambda:True))
""")
        self.assertEqual(code, 0, log[-4000:])
        self.assertIn("PRODUCTION_BOUNDARY_PASS", log)

    def test_parameterized_consumer_port_cannot_copy_default_actor(self):
        self.rejected("PRODUCTION_DEFAULT_ACTOR", app_suffix="""
class FinancePort:
    def __init__(self):
        self.consumer_for = lambda uid:{'user_id':uid,'status':'active','phone_verified':True}
app.finance_repository = FinancePort()
""")

    def test_app_import_cannot_change_database_after_start_script(self):
        self.rejected("PRODUCTION_DATABASE_SELECTION", app_suffix="""
os.environ['DATABASE_URL']='postgresql://hs2_fixture@/postgres?host=/tmp/hs2-pg-injected/socket'
""")

    def test_start_script_cannot_select_owned_fixture_database(self):
        self.rejected("PRODUCTION_FIXTURE_DATABASE", start_suffix="""
export HS2_FIXTURE_SOCKET=/tmp/hs2-pg-injected/socket
export HS2_FIXTURE_TEST=test_hs2_phase15_db.py
""")

    def test_start_script_cannot_override_production_database(self):
        self.rejected("PRODUCTION_DATABASE_SELECTION", start_suffix="""
export DATABASE_URL='postgresql://hs2_fixture@/postgres?host=/tmp/hs2-pg-injected/socket'
""")

    def test_start_script_cannot_target_preview_wsgi(self):
        self.rejected("UNAPPROVED_PRODUCTION_ENTRYPOINT",
                      start_replace=("app:app", "'hs2_workspace.fixtures:create_fixture_app()'"))

    def test_tcp_dns_and_live_database_are_blocked_before_app_import(self):
        code, log = run_probe(app_suffix="""
import socket,psycopg2
for attempt in (
    lambda:socket.create_connection(('127.0.0.1',9)),
    lambda:socket.getaddrinfo('payments.invalid',443),
    lambda:psycopg2.connect('postgresql://invalid@foreign.invalid/postgres'),
):
    try:
        attempt()
    except (OSError,RuntimeError):
        pass
    else:
        raise AssertionError('transport guard missing')
print('OWNED_EGRESS_VERIFIED')
""")
        self.assertEqual(code, 0, log[-4000:])
        self.assertIn("OWNED_EGRESS_VERIFIED", log)

    def test_publish_flow_changes_are_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = {"scripts": {"build:frontend": "python scripts/build_frontend.py"}}
            (root / "package.json").write_text(json.dumps(package))
            for changed, reason in (
                ('run=["python","scripts/hs2_dev_preview.py"]\n'
                 'build=["npm","run","build:frontend"]', "UNAPPROVED_PUBLISH_RUN"),
                ('run=["bash","scripts/start-prod.sh"]\n'
                 'build=["npm","run","build:js"]', "UNAPPROVED_PUBLISH_BUILD"),
            ):
                (root / ".replit").write_text("[deployment]\n" + changed)
                with self.assertRaisesRegex(RuntimeError, reason):
                    check_publish_flow(root)
            (root / ".replit").write_text(
                '[deployment]\nrun=["bash","scripts/start-prod.sh"]\n'
                'build=["npm","run","build:frontend"]')
            package["scripts"]["build:frontend"] = "python scripts/hs2_dev_preview.py"
            (root / "package.json").write_text(json.dumps(package))
            with self.assertRaisesRegex(RuntimeError, "UNAPPROVED_PUBLISH_BUILDER"):
                check_publish_flow(root)

    def test_failed_gate_precedes_all_build_work_and_marker_promotion(self):
        spec = importlib.util.spec_from_file_location(
            "boundary_test_builder", ROOT / "scripts/build_frontend.py")
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        with (
            patch("scripts.hs2_production_preflight.run_probe",
                  side_effect=lambda:run_probe(app_suffix="""
from hs2_admin.fixtures import create_fixture_app
app = create_fixture_app(initialize=False)
""")),
            patch.object(builder, "run_building_photo_selection_preflight") as photos,
            patch.object(builder, "build_external_scripts") as scripts,
            patch.object(builder, "promote") as promote,
        ):
            with self.assertRaisesRegex(SystemExit, "Production wiring preflight failed"):
                builder.main()
            photos.assert_not_called()
            scripts.assert_not_called()
            promote.assert_not_called()


if __name__ == "__main__":
    unittest.main()
