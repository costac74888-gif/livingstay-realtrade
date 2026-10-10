from hs2_details.fixtures import create_fixture_app as detail_app
from hs2_data.repository import connect_fixture
from hs2_supermap.fixtures import WHO
from .repository import BookingRepository,migrate
from .api import create_blueprint


def create_fixture_app(initialize=True,populate=None):
    app=detail_app(initialize,populate=populate)
    if initialize:
        with connect_fixture() as conn:migrate(conn)
    app.fixture_booking_operator=dict(WHO)
    app.fixture_bookings=BookingRepository(app.fixture_details)
    app.fixture_calendar.inventory_is_available=app.fixture_bookings.inventory_available
    app.register_blueprint(create_blueprint(app.fixture_bookings,
        current_consumer=lambda:app.fixture_consumer,current_operator=lambda:app.fixture_booking_operator,
        consumer_csrf=lambda:"isolated-consumer-csrf-not-real-session",
        operator_csrf=lambda:"isolated-booking-operator-csrf-not-real-session",allow_request=lambda:True))
    return app
