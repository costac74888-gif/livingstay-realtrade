from flask import session
from hs2_finance.fixtures import create_fixture_app as finance_app
from hs2_data.repository import connect_fixture
from hs2_help.api import create_blueprint as help_blueprint
from .repository import AdminRepository,migrate
from .api import create_blueprint


def create_fixture_app(initialize=True,populate=None):
    app=finance_app(initialize,populate=populate)
    if initialize:
        with connect_fixture() as conn:migrate(conn)
    # Same signed-session resolver used by Phase6's existing admin route.
    app.fixture_admin_repo=AdminRepository(app.fixture_finance,
        resolve_admin=lambda:700 if session.get("fixture_admin") is True else None,
        fallback_policy=lambda key:app.fixture_financial_policy)
    app.fixture_finance.policy_for=app.fixture_admin_repo.policy_for
    app.register_blueprint(create_blueprint(app.fixture_admin_repo,csrf_for=lambda uid:session["fixture_csrf"],allow_request=lambda:True))
    app.register_blueprint(help_blueprint(content_for=app.fixture_admin_repo.help_content))
    return app
