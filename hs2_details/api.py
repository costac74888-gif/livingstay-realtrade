import json
import secrets
from pathlib import Path
from flask import Blueprint,jsonify,request,send_from_directory
from hs2_design.domain import ContractError
from .contracts import consumer

WEB=Path(__file__).parent/"web"


def create_blueprint(repo,*,current_consumer,csrf_token,allow_request):
    if not all(callable(p) for p in (current_consumer,csrf_token,allow_request)):
        raise ValueError("Trusted consumer session,CSRF,budget callbacks required")
    bp=Blueprint("hs2_details",__name__,url_prefix="/hs2/details")

    @bp.before_request
    def budget():
        if "/api/" in request.path and allow_request() is not True:
            raise ContractError("DETAIL_RATE_LIMIT")

    @bp.after_request
    def headers(response):
        response.headers["Cache-Control"]="no-store"
        response.headers["X-Content-Type-Options"]="nosniff"
        response.headers["Referrer-Policy"]="same-origin"
        return response

    @bp.errorhandler(ContractError)
    def error(exc):
        code=str(exc)
        status=429 if code=="DETAIL_RATE_LIMIT" else 403 if code in {"VERIFIED_CONSUMER_REQUIRED","ACTIVE_CONSUMER_REQUIRED","CSRF_REQUIRED"} else 404 if code.endswith("NOT_FOUND") else 409 if code in {"QUOTE_SOURCE_CHANGED","QUOTE_RETRY_CONFLICT","QUOTE_RECEIPT_EXPIRED"} else 400
        return jsonify(ok=False,code=code),status

    @bp.get("/")
    def page():
        return send_from_directory(WEB,"detail.html")

    @bp.get("/assets/<name>")
    def assets(name):
        if name not in {"detail.js","detail.css"}:raise ContractError("ASSET_NOT_FOUND")
        return send_from_directory(WEB,name)

    @bp.get("/api/session")
    def session():
        who=current_consumer()
        try:
            consumer(who);eligible=True
        except ContractError:
            eligible=False
        return jsonify(ok=True,can_confirm_quote=eligible,csrf_token=csrf_token() if eligible else None,
                       booking_confirmed=False,inventory_held=False)

    @bp.get("/api/items/<key>")
    def detail(key):
        if request.args:raise ContractError("UNKNOWN_DETAIL_FILTER")
        return jsonify(ok=True,**repo.detail(key))

    @bp.get("/api/items/<key>/quote")
    def quote(key):
        if any(len(request.args.getlist(k))!=1 for k in request.args):raise ContractError("DUPLICATE_FILTER")
        return jsonify(ok=True,**repo.quote(key,request.args.to_dict()))

    @bp.post("/api/items/<key>/confirm-quote")
    def confirm(key):
        who=current_consumer();consumer(who)
        expected=csrf_token();provided=request.headers.get("X-CSRF-Token","")
        if not isinstance(expected,str) or not expected or not expected.isascii() or not provided.isascii() or not secrets.compare_digest(provided,expected):
            raise ContractError("CSRF_REQUIRED")
        if request.mimetype!="application/json" or request.content_length is None or request.content_length>8192:
            raise ContractError("JSON_BODY_REQUIRED")
        def pairs(rows):
            result={}
            for k,v in rows:
                if k in result:raise ContractError("DUPLICATE_BODY_FIELD")
                result[k]=v
            return result
        try:
            body=json.loads(request.get_data(),object_pairs_hook=pairs,
                            parse_constant=lambda _:(_ for _ in ()).throw(ContractError("INVALID_JSON")))
        except ContractError:
            raise
        except (ValueError,UnicodeError):
            raise ContractError("INVALID_JSON") from None
        return jsonify(ok=True,receipt=repo.confirm_quote(who,key,body))

    @bp.get("/api/receipts/<key>")
    def receipt(key):
        return jsonify(ok=True,receipt=repo.read_receipt(current_consumer(),key))

    return bp
