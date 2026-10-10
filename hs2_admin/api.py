from pathlib import Path
import secrets
from flask import Blueprint,jsonify,request,send_from_directory
from hs2_design.domain import ContractError
from .validation import KINDS

WEB=Path(__file__).parent/"web"


def create_blueprint(repo,*,csrf_for,allow_request):
    if not callable(csrf_for) or not callable(allow_request):raise ValueError("Trusted CSRF/budget required")
    bp=Blueprint("hs2_admin",__name__,url_prefix="/hs2/admin")

    @bp.before_request
    def guard():
        uid=repo.who()
        if allow_request() is not True:raise ContractError("ADMIN_RATE_LIMIT")
        if request.args:raise ContractError("INVALID_ADMIN_FILTER")
        if request.method not in {"GET","HEAD","OPTIONS"}:
            token=csrf_for(uid);given=request.headers.get("X-HS2-CSRF","")
            if type(token) is not str or not token or not token.isascii() or not given.isascii() or not secrets.compare_digest(token,given):raise ContractError("CSRF_REQUIRED")

    @bp.after_request
    def headers(r):
        r.headers["Cache-Control"]="no-store, private";r.headers["X-Content-Type-Options"]="nosniff"
        r.headers["Referrer-Policy"]="same-origin";return r

    @bp.errorhandler(ContractError)
    def error(e):
        code=str(e)
        return jsonify(ok=False,code=code),429 if code=="ADMIN_RATE_LIMIT" else 409 if code=="STALE_ADMIN_REVISION" else 403 if code in {"ADMIN_REQUIRED","CSRF_REQUIRED"} else 400

    def data(keys):
        raw=request.get_json(silent=True)
        if type(raw) is not dict or set(raw)!=set(keys):raise ContractError("INVALID_ADMIN_COMMAND")
        return raw

    @bp.get("/")
    def page():return send_from_directory(WEB,"admin.html")

    @bp.get("/assets/<name>")
    def asset(name):
        if name not in {"admin.js","admin.css"}:raise ContractError("ASSET_NOT_FOUND")
        return send_from_directory(WEB,name)

    @bp.get("/api/meta")
    def meta():return jsonify(ok=True,csrf=csrf_for(repo.who()),kinds=sorted(KINDS),live_operations_approved=False)

    @bp.get("/api/overview")
    def overview():return jsonify(ok=True,**repo.overview())

    @bp.post("/api/records")
    def create():
        raw=data(["kind","payload"]);return jsonify(ok=True,item=repo.create(raw["kind"],raw["payload"]))

    @bp.post("/api/records/<key>/change")
    def update(key):
        raw=data(["revision","action","note","payload"])
        return jsonify(ok=True,item=repo.change(key,raw["revision"],raw["action"],raw["note"],raw["payload"]))

    @bp.post("/api/applications/<key>/review")
    def review(key):return jsonify(ok=True,item=repo.review_application(key,request.get_json(silent=True)))

    return bp
