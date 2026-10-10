from pathlib import Path
from flask import Blueprint, jsonify, request, send_from_directory
from hs2_design.domain import ContractError
from hs2_listings.validation import actor

WEB = Path(__file__).parent / "web"


def create_blueprint(repo, *, resolve_context, csrf_token, check_csrf, allow_quote_request):
    if not all(callable(p) for p in (resolve_context, csrf_token, check_csrf, allow_quote_request)):
        raise ValueError("Trusted context/CSRF/quote-budget ports required")
    bp = Blueprint("hs2_calendar", __name__, url_prefix="/hs2/calendar")

    def who():
        return actor(resolve_context())

    @bp.before_request
    def guard():
        if request.path == "/hs2/calendar/quote" and request.method == "GET":
            if allow_quote_request() is not True:
                raise ContractError("QUOTE_RATE_LIMIT")
            return
        who()
        if request.method not in {"GET", "HEAD", "OPTIONS"} and check_csrf() is not True:
            raise ContractError("CSRF_REQUIRED")

    @bp.after_request
    def safe(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'self'"
        return response

    @bp.errorhandler(ContractError)
    def error(exc):
        code = str(exc)
        status = 429 if code == "QUOTE_RATE_LIMIT" else 401 if code == "AUTH_REQUIRED" else 403 if code in {
            "CSRF_REQUIRED", "ACTIVE_MEMBER_REQUIRED", "APPROVED_BUSINESS_REQUIRED"
        } else 404 if code.endswith("NOT_FOUND") else 409
        return jsonify(ok=False, code=code), status

    @bp.get("/")
    def page():
        return send_from_directory(WEB, "calendar.html")

    @bp.get("/assets/<name>")
    def assets(name):
        if name not in {"calendar.css", "calendar.js"}:
            raise ContractError("ASSET_NOT_FOUND")
        return send_from_directory(WEB, name)

    @bp.get("/meta")
    def meta():
        items = repo.registrations.list(who())
        return jsonify(ok=True, csrf=csrf_token(), today=repo.business_date().isoformat(),
                       items=[dict(id=r["id"], title=r["payload"]["title"], stay_kind=r["payload"]["stay_kind"],
                                   status=r["status"], source_revision=r["revision"], public_id=r["public_id"])
                              for r in items], booking_confirmed=False)

    @bp.get("/applications/<uuid:key>/prices")
    def read(key):
        return jsonify(ok=True, item=repo.read(who(), str(key)))

    @bp.post("/applications/<uuid:key>/prices")
    def write(key):
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or set(body) != {"version", "source_revision", "command"}:
            raise ContractError("INVALID_CALENDAR_INPUT")
        return jsonify(ok=True, item=repo.update(who(), str(key), body["version"], body["source_revision"], body["command"]))

    @bp.get("/quote")
    def quote():
        if set(request.args) != {"public_id", "check_in", "check_out"} or any(len(request.args.getlist(k)) != 1 for k in request.args):
            raise ContractError("INVALID_QUOTE_QUERY")
        return jsonify(ok=True, quote=repo.quote(request.args["public_id"], request.args["check_in"], request.args["check_out"]))

    return bp
