from hs2_booking.fixtures import create_fixture_app as booking_app
from hs2_data.repository import connect_fixture
from hs2_details.fixtures import CONSUMER
from .policy import ReviewedPolicy
from .repository import FinanceRepository,migrate
from .adapter import OwnedSandbox
from .api import create_blueprint


def create_fixture_app(initialize=True,populate=None):
    app=booking_app(initialize,populate=populate)
    if initialize:
        with connect_fixture() as conn:migrate(conn)
    app.fixture_financial_policy=ReviewedPolicy("owned-initial-zero-platform",50000,reviewed=True,pg_processing_krw=0)
    app.fixture_payment_provider=OwnedSandbox()
    app.fixture_finance=FinanceRepository(app.fixture_bookings,
        policy_for=lambda key:app.fixture_financial_policy,
        consumer_for=lambda uid:{**CONSUMER,"user_id":uid},provider=app.fixture_payment_provider)
    app.fixture_bookings.paid_cancellation=app.fixture_finance.paid_cancelled
    app.register_blueprint(create_blueprint(app.fixture_finance,
        current_consumer=lambda:app.fixture_consumer,current_operator=lambda:app.fixture_booking_operator,
        consumer_csrf=lambda:"isolated-consumer-csrf-not-real-session",
        operator_csrf=lambda:"isolated-finance-operator-csrf-not-real-session",allow_request=lambda:True))
    return app
