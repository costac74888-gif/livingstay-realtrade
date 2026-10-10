from hs2_dashboard.fixtures import create_fixture_app as dashboard_app
from hs2_data.repository import connect_fixture
from .repository import WorkspaceRepository,migrate
from .api import create_blueprint


def create_fixture_app(initialize=True,populate=None):
    app=dashboard_app(initialize,populate)
    if initialize:
        with connect_fixture() as conn:migrate(conn)
    app.fixture_workspace=WorkspaceRepository(app.fixture_finance)
    app.fixture_bookings.event_callback=app.fixture_workspace.booking_event
    app.register_blueprint(create_blueprint(app.fixture_workspace,current_consumer=lambda:app.fixture_consumer,
        current_operator=lambda:app.fixture_booking_operator,csrf_for=lambda who:"isolated-workspace-csrf",
        allow_request=lambda:True))
    return app
