from wsgiref.simple_server import make_server,WSGIRequestHandler
from hs2_registration.fixture_http import LocalServer
from .fixtures import create_fixture_app


def server(port=0):
    return make_server("127.0.0.1",port,create_fixture_app(),server_class=LocalServer,handler_class=WSGIRequestHandler)
