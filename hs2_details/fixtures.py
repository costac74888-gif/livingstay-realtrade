from hs2_supermap.fixtures import create_fixture_app as supermap_app
from hs2_data.repository import connect_fixture
from .repository import DetailRepository,migrate
from .api import create_blueprint

CONSUMER=dict(user_id=101,context_id="consumer",role="consumer",email_verified=True)


def create_fixture_app(initialize=True,populate=None):
    app=supermap_app(initialize,populate=populate)
    if initialize:
        with connect_fixture() as conn:migrate(conn)
    app.fixture_consumer=dict(CONSUMER)
    app.fixture_details=DetailRepository(app.fixture_supermap,member_is_active=lambda uid:uid in {101,102})
    app.register_blueprint(create_blueprint(app.fixture_details,current_consumer=lambda:app.fixture_consumer,
        csrf_token=lambda:"isolated-consumer-csrf-not-real-session",allow_request=lambda:True))
    return app
