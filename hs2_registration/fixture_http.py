"""Test-only WSGI fixture. No app import, DB, default provider or real identity."""
from socketserver import TCPServer
from wsgiref.simple_server import WSGIServer,WSGIRequestHandler,make_server
from flask import Flask
from .api import create_blueprint
from .fixtures import fixture_service


def create_fixture_app():
    app=Flask("hs2_private_fixture")
    app.register_blueprint(create_blueprint(fixture_service(),lambda:1,
        lambda:__import__("flask").request.headers.get("X-HS2-CSRF")=="fixture-only"))
    return app


class LocalServer(WSGIServer):
    def server_bind(self):
        # No DNS lookup; literal loopback only, inherited guard otherwise intact.
        if self.server_address[0]!="127.0.0.1":raise ValueError("fixture loopback only")
        TCPServer.server_bind(self)
        self.server_name="hs2-fixture";self.server_port=self.server_address[1]
        self.setup_environ()


def server(port=0):
    return make_server("127.0.0.1",port,create_fixture_app(),
                       server_class=LocalServer,handler_class=WSGIRequestHandler)
