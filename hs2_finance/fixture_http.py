from wsgiref.simple_server import make_server,WSGIRequestHandler
from hs2_registration.fixture_http import LocalServer
from .fixtures import create_fixture_app
from hs2_details.fixtures import CONSUMER
from hs2_supermap.fixtures import WHO
from hs2_supermap.contracts import parse
from uuid import uuid4
import time


def seed_paid(app):
    public=next(r["public_id"] for r in app.fixture_supermap.search(parse({}))["items"] if r["stay_kind"]=="lodging")
    selection=dict(check_in="2027-01-11",check_out="2027-01-13",guests=2)
    quote=app.fixture_details.quote(public,selection)["quote"]
    receipt=app.fixture_details.confirm_quote(CONSUMER,public,dict(**selection,request_id=str(uuid4()),acknowledged=True,expected_source_version=quote["source_version"]))
    booking=app.fixture_bookings.request(CONSUMER,dict(receipt_id=receipt["receipt_id"],request_id=str(uuid4()),acknowledged=True))
    app.fixture_bookings.act(WHO,booking["booking_id"],1,"approve",operator=True)
    preview=app.fixture_finance.quote(CONSUMER,booking["booking_id"])
    contract=app.fixture_finance.create(CONSUMER,dict(booking_id=booking["booking_id"],request_id=str(uuid4()),acknowledged=True,expected_terms_sha256=preview["terms_sha256"]))
    raw,sig=app.fixture_payment_provider.sign(dict(event_id=str(uuid4()),contract_id=contract["contract_id"],
        reference="owned-http-fixture",kind="capture",amount_krw=250000,currency="KRW",issued_at=int(time.time())))
    app.fixture_finance.receive(raw,sig)


def server(port=0):
    app=create_fixture_app()
    seed_paid(app)
    return make_server("127.0.0.1",port,app,server_class=LocalServer,handler_class=WSGIRequestHandler)
