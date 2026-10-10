from pathlib import Path
from flask import Blueprint, Response, jsonify, request, send_from_directory
from hs2_design.domain import ContractError
from .validation import actor, identifier
from .review import review

WEB = Path(__file__).parent / "web"


def create_blueprint(repo, *, resolve_context, resolve_admin, check_csrf, csrf_token, references, verify_reference):
    bp = Blueprint("hs2_listings", __name__, url_prefix="/hs2/listings")
    ports = (resolve_context, resolve_admin, check_csrf, csrf_token, references, verify_reference)
    if not all(callable(p) for p in ports):
        raise ValueError("All trusted identity/reference/CSRF ports required")

    def who():
        return actor(resolve_context())

    def admin():
        uid = resolve_admin()
        if type(uid) is not int or uid <= 0:
            raise ContractError("ADMIN_REQUIRED")
        return uid

    def data(keys):
        value = request.get_json(silent=True)
        if not isinstance(value, dict) or set(value) != set(keys):
            raise ContractError("INVALID_INPUT")
        return value

    @bp.before_request
    def guard():
        if request.path.startswith("/hs2/listings/assets/"):
            try:
                who()
            except ContractError:
                admin()
        elif request.path.startswith("/hs2/listings/admin"):
            admin()
        else:
            who()
        if request.method not in {"GET", "HEAD", "OPTIONS"} and not check_csrf():
            raise ContractError("CSRF_REQUIRED")

    @bp.after_request
    def headers(response):
        response.headers["Cache-Control"] = "no-store, private"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; connect-src 'self'; frame-ancestors 'self'; object-src 'none'"
        return response

    @bp.errorhandler(ContractError)
    def error(exc):
        code = str(exc)
        status = 401 if code == "AUTH_REQUIRED" else 403 if code in {"ADMIN_REQUIRED", "CSRF_REQUIRED", "APPROVED_BUSINESS_REQUIRED", "ACTIVE_MEMBER_REQUIRED"} else 404 if code.endswith("NOT_FOUND") else 409
        return jsonify(ok=False, code=code, message=code), status

    @bp.get("/")
    def page():
        return send_from_directory(WEB, "listings.html")

    @bp.get("/admin")
    def admin_page():
        return send_from_directory(WEB, "admin.html")

    @bp.get("/assets/<name>")
    def assets(name):
        if name not in {"listings.js", "listings.css", "admin.js", "favicon.svg"}:
            raise ContractError("ASSET_NOT_FOUND")
        return send_from_directory(WEB, name)

    @bp.get("/meta")
    def meta():
        context = who()
        return jsonify(ok=True, context=context, csrf=csrf_token(),
                       references=references(context), publication="admin_review",
                       classification_source="operator_declared_admin_reviewed")

    @bp.get("/applications")
    def applications():
        return jsonify(ok=True, items=repo.list(who()))

    @bp.post("/applications")
    def create():
        body = data({"workflow_id", "payload"})
        context = who()
        reference = verify_reference(context, identifier(body["workflow_id"]))
        if not isinstance(reference, dict) or reference.get("status") != "REFERENCE_CONFIRMED":
            raise ContractError("OWNED_CONFIRMED_REFERENCE_REQUIRED")
        return jsonify(ok=True, item=repo.create(context, identifier(reference["reference_id"]), body["payload"])), 201

    @bp.get("/applications/<uuid:key>")
    def read(key):
        return jsonify(ok=True, item=repo.read(who(), str(key)))

    @bp.route("/applications/<uuid:key>", methods=["PUT", "DELETE"])
    def edit(key):
        body = data({"revision", "payload"} if request.method == "PUT" else {"revision"})
        action = "save" if request.method == "PUT" else "withdraw"
        return jsonify(ok=True, item=repo.change(who(), str(key), body["revision"], action, body.get("payload")))

    @bp.post("/applications/<uuid:key>/submit")
    def submit(key):
        body = data({"revision"})
        return jsonify(ok=True, item=repo.change(who(), str(key), body["revision"], "submit"))

    @bp.post("/photos")
    def photo_upload():
        file = request.files.get("file")
        if file is None:
            raise ContractError("PHOTO_REQUIRED")
        content = file.stream.read(524289)
        return jsonify(ok=True, **repo.upload(who(), content, file.mimetype)), 201

    @bp.get("/photos/<uuid:key>")
    def photo(key):
        mime, content = repo.photo(who(), str(key))
        return Response(content, mimetype=mime)

    @bp.get("/admin/meta")
    def admin_meta():
        return jsonify(ok=True, admin_id=admin(), csrf=csrf_token())

    @bp.get("/admin/applications")
    def admin_applications():
        return jsonify(ok=True, items=repo.list())

    @bp.post("/admin/applications/<uuid:key>/review")
    def review_application(key):
        body = data({"revision", "decision", "note", "rights", "disclosure"})
        return jsonify(ok=True, item=review(repo, str(key), admin(), body["revision"],
                         body["decision"], body["note"], rights=body["rights"], disclosure=body["disclosure"]))

    @bp.get("/admin/photos/<uuid:key>")
    def admin_photo(key):
        mime, content = repo.photo(None, str(key), admin=True)
        return Response(content, mimetype=mime)

    return bp
