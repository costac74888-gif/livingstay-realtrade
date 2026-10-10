from pathlib import Path
from flask import Blueprint,jsonify,request,send_from_directory
from hs2_design.domain import ContractError
from hs2_listings.validation import actor

WEB=Path(__file__).parent/"web"


def create_blueprint(repo,*,current_operator,allow_request):
    if not all(callable(p) for p in (current_operator,allow_request)):raise ValueError("Trusted operator/budget ports required")
    bp=Blueprint("hs2_dashboard",__name__,url_prefix="/hs2/dashboard")

    @bp.before_request
    def budget():
        if "/api/" in request.path and allow_request() is not True:raise ContractError("DASHBOARD_RATE_LIMIT")

    @bp.after_request
    def headers(r):
        r.headers["Cache-Control"]="no-store";r.headers["X-Content-Type-Options"]="nosniff";r.headers["Referrer-Policy"]="same-origin"
        from hs2_design.security import harden
        return harden(r)

    @bp.errorhandler(ContractError)
    def error(e):
        code=str(e)
        return jsonify(ok=False,code=code),429 if code=="DASHBOARD_RATE_LIMIT" else 404 if code.endswith("NOT_FOUND") else 403

    def who():
        v=current_operator();actor(v)
        with repo.registrations.transaction() as c:repo.registrations.active(c,v)
        return v

    @bp.get("/")
    def page():return send_from_directory(WEB,"dashboard.html")

    @bp.get("/assets/<name>")
    def asset(name):
        if name not in {"dashboard.js","dashboard.css"}:raise ContractError("ASSET_NOT_FOUND")
        return send_from_directory(WEB,name)

    @bp.get("/api/session")
    def session():
        try:
            v=who()
            return jsonify(ok=True,can_operator=True,context_id=v["context_id"])
        except ContractError:return jsonify(ok=True,can_operator=False,context_id=None)

    @bp.get("/api/overview")
    def overview():
        if request.args:raise ContractError("UNKNOWN_DASHBOARD_FILTER")
        return jsonify(ok=True,dashboard=repo.overview(who()))

    return bp
