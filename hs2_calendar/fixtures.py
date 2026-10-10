"""Owned fixture composition; no real accounts/provider/DSN fallback."""
from datetime import date
from hs2_data.repository import connect_fixture
from hs2_listings.fixtures import create_fixture_app as listing_app, CANDIDATE, PNG
from hs2_listings.review import review
from .repository import CalendarRepository, migrate
from .api import create_blueprint


def create_fixture_app(initialize=True, populate=None):
    app = listing_app(initialize)
    with connect_fixture() as conn:
        migrate(conn)
    repo = CalendarRepository(app.fixture_repo, inventory_is_available=lambda *_: True,
                              today=lambda: date(2026, 10, 11))
    app.fixture_calendar = repo
    app.register_blueprint(create_blueprint(repo, resolve_context=app.fixture_context,
        csrf_token=app.fixture_csrf_token, check_csrf=app.fixture_check_csrf,
        allow_quote_request=lambda: True))
    if populate is True or (populate is None and initialize):
        who = dict(user_id=101, context_id="operator:fixture:101", role="operator")
        photo = app.fixture_repo.upload(who, PNG, "image/png")["id"]
        for label, kind in (("숙박 검증 공간", "lodging"), ("비숙박 검증 공간", "non_lodging")):
            data = dict(title=label, space_label=label, stay_kind=kind, rooms=0, area_m2="21.5",
                        guests=2, nightly=100000 if kind == "lodging" else None,
                        weekly=300000 if kind == "non_lodging" else None,
                        monthly=1000000 if kind == "non_lodging" else None,
                        min_stay=1 if kind == "lodging" else 7,
                        photos=[photo], responsibility=True)
            row = app.fixture_repo.create(who, CANDIDATE, data)
            app.fixture_repo.change(who, row["id"], 1, "submit")
            review(app.fixture_repo, row["id"], 700, 1, "approve", "격리 검증 등록권한·공개정보 확인",
                   rights=True, disclosure=True)
    return app
