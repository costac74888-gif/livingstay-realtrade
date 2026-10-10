from pathlib import Path
from flask import Flask,send_from_directory
from wsgiref.simple_server import make_server,WSGIRequestHandler
from hs2_registration.fixture_http import LocalServer
from .api import create_blueprint

ROOT=Path(__file__).resolve().parent.parent


def app():
    result=Flask("owned_help",static_folder=None)
    result.register_blueprint(create_blueprint())
    @result.get("/static/home_stay_share.png")
    def brand():return send_from_directory(ROOT/"static","home_stay_share.png")
    @result.get("/hs2/consumer-assets/main.css")
    def css():return send_from_directory(ROOT/"hs2_consumer/web","main.css")
    return result


def server(port=0):return make_server("127.0.0.1",port,app(),server_class=LocalServer,handler_class=WSGIRequestHandler)
