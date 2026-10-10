from wsgiref.simple_server import make_server,WSGIRequestHandler
from hs2_registration.fixture_http import LocalServer
from hs2_finance.fixture_http import seed_paid
from .fixtures import create_fixture_app


def server(port=0):
    app=create_fixture_app()
    seed_paid(app)
    return make_server("127.0.0.1",port,app,server_class=LocalServer,handler_class=WSGIRequestHandler)
