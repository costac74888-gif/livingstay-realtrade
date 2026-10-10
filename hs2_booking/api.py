from pathlib import Path
import json,secrets
from flask import Blueprint,jsonify,request,send_from_directory
from hs2_design.domain import ContractError
from hs2_details.contracts import consumer
from hs2_listings.validation import actor

WEB=Path(__file__).parent/"web"


def create_blueprint(repo,*,current_consumer,current_operator,consumer_csrf,operator_csrf,allow_request):
    if not all(callable(p) for p in (current_consumer,current_operator,consumer_csrf,operator_csrf,allow_request)):
        raise ValueError("Trusted session,scope,CSRF and rate-budget callbacks required")
    bp=Blueprint("hs2_bookings",__name__,url_prefix="/hs2/bookings")

    @bp.before_request
    def budget():
        if "/api/" in request.path and allow_request() is not True:raise ContractError("BOOKING_RATE_LIMIT")

    @bp.after_request
    def headers(r):
        r.headers["Cache-Control"]="no-store";r.headers["X-Content-Type-Options"]="nosniff"
        r.headers["Referrer-Policy"]="same-origin";return r

    @bp.errorhandler(ContractError)
    def error(exc):
        code=str(exc)
        status=429 if code=="BOOKING_RATE_LIMIT" else 503 if code=="PAYMENT_PROVIDER_UNAVAILABLE" else 403 if code in {
            "VERIFIED_CONSUMER_REQUIRED","ACTIVE_CONSUMER_REQUIRED","APPROVED_BUSINESS_REQUIRED",
            "ACTIVE_MEMBER_REQUIRED","OPERATOR_CONTEXT_REQUIRED","CSRF_REQUIRED"} else 404 if code.endswith("NOT_FOUND") else 409 if code in {
            "BOOKING_RETRY_CONFLICT","BOOKING_REVISION_CHANGED","BOOKING_STATE_CHANGED","BOOKING_INVENTORY_CONFLICT",
            "INVENTORY_UNAVAILABLE","QUOTE_RECEIPT_ALREADY_USED","QUOTE_RECEIPT_EXPIRED","QUOTE_SOURCE_CHANGED",
            "ACTIVE_BOOKING_LIMIT","PAYMENT_TERMS_REVIEW_REQUIRED","VERIFIED_PAYMENT_REQUIRED","PAYMENT_REFERENCE_REPLAY"} else 400
        return jsonify(ok=False,code=code),status

    def body(operator=False):
        who=current_operator() if operator else current_consumer()
        actor(who) if operator else consumer(who)
        expected=operator_csrf() if operator else consumer_csrf()
        provided=request.headers.get("X-CSRF-Token","")
        if not isinstance(expected,str) or not expected or not expected.isascii() or not provided.isascii() or not secrets.compare_digest(expected,provided):
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
            value=json.loads(request.get_data(),object_pairs_hook=pairs,
                parse_constant=lambda _:(_ for _ in ()).throw(ContractError("INVALID_JSON")))
        except ContractError:raise
        except (ValueError,UnicodeError):raise ContractError("INVALID_JSON") from None
        return who,value

    @bp.get("/")
    def page():return send_from_directory(WEB,"bookings.html")

    @bp.get("/assets/<name>")
    def asset(name):
        if name not in {"bookings.js","bookings.css"}:raise ContractError("ASSET_NOT_FOUND")
        return send_from_directory(WEB,name)

    @bp.get("/api/session")
    def session():
        can_consumer=can_operator=False
        try:consumer(current_consumer());can_consumer=True
        except ContractError:pass
        try:actor(current_operator());can_operator=True
        except ContractError:pass
        return jsonify(ok=True,can_consumer=can_consumer,can_operator=can_operator,
            consumer_csrf=consumer_csrf() if can_consumer else None,
            operator_csrf=operator_csrf() if can_operator else None,
            payment_available=repo.payment_proof is not None and callable(repo.payment_terms_reviewed))

    @bp.get("/api/consumer")
    def consumer_list():
        if request.args:raise ContractError("UNKNOWN_BOOKING_FILTER")
        return jsonify(ok=True,bookings=repo.list(current_consumer()))

    @bp.get("/api/operator")
    def operator_list():
        if request.args:raise ContractError("UNKNOWN_BOOKING_FILTER")
        return jsonify(ok=True,bookings=repo.list(current_operator(),operator=True))

    @bp.post("/api/request")
    def create():
        who,value=body()
        return jsonify(ok=True,booking=repo.request(who,value))

    def action(key,operator=False):
        who,value=body(operator)
        if not isinstance(value,dict) or set(value)!={"action","revision"}:raise ContractError("INVALID_BOOKING_ACTION")
        return jsonify(ok=True,booking=repo.act(who,key,value["revision"],value["action"],operator=operator))

    @bp.post("/api/consumer/<key>/action")
    def consumer_action(key):return action(key)

    @bp.post("/api/operator/<key>/action")
    def operator_action(key):return action(key,True)

    return bp
