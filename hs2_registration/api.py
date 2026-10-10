"""Unmounted private Blueprint. Authentication/CSRF are injected, never defaulted."""
from pathlib import Path
from flask import Blueprint, jsonify, request, send_from_directory
from .service import RegistrationError

WEB=Path(__file__).parent/"web"


def create_blueprint(service, resolve_actor, check_csrf):
    if not callable(resolve_actor) or not callable(check_csrf):
        raise ValueError("Trusted identity and CSRF adapters required")
    bp=Blueprint("hs2_registration",__name__,url_prefix="/hs2/registration")

    @bp.before_request
    def guard():
        try:service.actor(resolve_actor())
        except RegistrationError:return jsonify(error="AUTH_REQUIRED"),401
        if request.method=="POST" and not check_csrf():return jsonify(error="CSRF_REQUIRED"),403

    @bp.after_request
    def private(response):
        response.headers["Cache-Control"]="no-store, private"
        response.headers["X-Content-Type-Options"]="nosniff"
        response.headers["Content-Security-Policy"]="default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'self'"
        return response

    @bp.errorhandler(RegistrationError)
    def invalid(e):
        code=str(e)
        return jsonify(error=code),404 if code in {"WORKFLOW_NOT_FOUND","WORKFLOW_EXPIRED"} else 409

    @bp.get("/")
    def page():return send_from_directory(WEB,"registration.html")

    @bp.get("/assets/<path:filename>")
    def asset(filename):return send_from_directory(WEB,filename)

    @bp.post("/start")
    def start():
        data=request.get_json(silent=True)
        if not isinstance(data,dict) or set(data)!={"query"}:raise RegistrationError("INVALID_INPUT")
        return jsonify(service.start(resolve_actor(),data["query"]))

    @bp.get("/<uuid:key>")
    def read(key):return jsonify(service.read(resolve_actor(),str(key)))

    @bp.post("/<uuid:key>/<action>")
    def action(key,action):
        data=request.get_json(silent=True)
        if not isinstance(data,dict):raise RegistrationError("INVALID_INPUT")
        actor=resolve_actor();key=str(key)
        if action=="address" and set(data)=={"address_key"}:
            return jsonify(service.select_address(actor,key,data["address_key"]))
        if action=="building" and set(data)=={"building_key"}:
            return jsonify(service.select_building(actor,key,data["building_key"]))
        if action=="coordinates" and not data:return jsonify(service.coordinates(actor,key))
        if action=="confirm" and not data:return jsonify(service.confirm(actor,key))
        raise RegistrationError("INVALID_ACTION")

    return bp
