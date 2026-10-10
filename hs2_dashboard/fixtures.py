from hs2_finance.fixtures import create_fixture_app as finance_app
from .repository import DashboardRepository
from .api import create_blueprint


def create_fixture_app(initialize=True,populate=None):
    app=finance_app(initialize,populate)
    app.fixture_dashboard=DashboardRepository(app.fixture_finance)
    app.register_blueprint(create_blueprint(app.fixture_dashboard,
        current_operator=lambda:app.fixture_booking_operator,allow_request=lambda:True))
    return app
