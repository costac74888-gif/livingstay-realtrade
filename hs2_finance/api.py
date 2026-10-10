from pathlib import Path
import json,secrets
from flask import Blueprint,jsonify,request,send_from_directory
from hs2_design.domain import ContractError
from hs2_details.contracts import consumer
from hs2_listings.validation import actor

WEB=Path(__file__).parent/"web"


def create_blueprint(repo,*,current_consumer,current_operator,consumer_csrf,operator_csrf,allow_request):
    if not all(callable(p) for p in (current_consumer,current_operator,consumer_csrf,operator_csrf,allow_request)):
        raise ValueError("Trusted identity/CSRF/budget ports required")
    bp=Blueprint("hs2_finance",__name__,url_prefix="/hs2/finance")

    @bp.before_request
    def budget():
        if "/api/" in request.path and allow_request() is not True:raise ContractError("FINANCIAL_RATE_LIMIT")

    @bp.after_request
    def headers(r):
        r.headers["Cache-Control"]="no-store";r.headers["X-Content-Type-Options"]="nosniff";r.headers["Referrer-Policy"]="same-origin"
        return r

    @bp.errorhandler(ContractError)
    def error(exc):
        code=str(exc)
        status=429 if code=="FINANCIAL_RATE_LIMIT" else 503 if code in {"LIVE_PAYMENT_NOT_APPROVED","LIVE_SETTLEMENT_NOT_APPROVED"} else 404 if code.endswith("NOT_FOUND") else 403 if code in {
            "CSRF_REQUIRED","PROVIDER_SIGNATURE_REQUIRED","VERIFIED_CONSUMER_REQUIRED","ACTIVE_CONSUMER_REQUIRED",
            "APPROVED_BUSINESS_REQUIRED","ACTIVE_MEMBER_REQUIRED","OPERATOR_CONTEXT_REQUIRED"} else 409 if code in {
            "BOOKING_STATE_CHANGED","BOOKING_DEADLINE_EXPIRED","FINANCIAL_RETRY_CONFLICT","PROVIDER_EVENT_REPLAY",
            "PROVIDER_REFERENCE_REPLAY","REVIEWED_FINANCIAL_POLICY_REQUIRED","POST_CHECKIN_MANUAL_REVIEW_REQUIRED",
            "SETTLEMENT_REVIEW_NOT_ELIGIBLE","VERIFIED_PAYMENT_REQUIRED","FINANCIAL_TERMS_CHANGED","REVIEWED_PG_COST_REQUIRED"} else 400
        return jsonify(ok=False,code=code),status

    def who(operator=False,write=False):
        value=current_operator() if operator else current_consumer()
        actor(value) if operator else consumer(value)
        if write:
            expected=operator_csrf() if operator else consumer_csrf();provided=request.headers.get("X-CSRF-Token","")
            if not isinstance(expected,str) or not expected or not expected.isascii() or not provided.isascii() or not secrets.compare_digest(expected,provided):
                raise ContractError("CSRF_REQUIRED")
        return value

    def body():
        if request.mimetype!="application/json" or request.content_length is None or request.content_length>8192:
            raise ContractError("JSON_BODY_REQUIRED")
        def pairs(rows):
            obj={}
            for k,v in rows:
                if k in obj:raise ContractError("DUPLICATE_BODY_FIELD")
                obj[k]=v
            return obj
        try:return json.loads(request.get_data(),object_pairs_hook=pairs,
            parse_constant=lambda _:(_ for _ in ()).throw(ContractError("INVALID_JSON")))
        except ContractError:raise
        except (ValueError,UnicodeError):raise ContractError("INVALID_JSON") from None

    @bp.get("/")
    def page():return send_from_directory(WEB,"finance.html")

    @bp.get("/assets/<name>")
    def asset(name):
        if name not in {"finance.css","finance.js"}:raise ContractError("ASSET_NOT_FOUND")
        return send_from_directory(WEB,name)

    @bp.get("/api/session")
    def session():
        can_consumer=can_operator=False
        try:who();can_consumer=True
        except ContractError:pass
        try:who(True);can_operator=True
        except ContractError:pass
        return jsonify(ok=True,can_consumer=can_consumer,can_operator=can_operator,
            consumer_csrf=consumer_csrf() if can_consumer else None,operator_csrf=operator_csrf() if can_operator else None,
            sandbox=repo.provider is None or repo.provider.sandbox,provider_available=repo.provider_ready(),actual_execution_available=False)

    @bp.get("/api/consumer")
    def own_list():
        if request.args:raise ContractError("UNKNOWN_FINANCIAL_FILTER")
        return jsonify(ok=True,contracts=repo.list(who()))

    @bp.get("/api/operator")
    def operator_list():
        if request.args:raise ContractError("UNKNOWN_FINANCIAL_FILTER")
        return jsonify(ok=True,contracts=repo.list(who(True),operator=True))

    @bp.get("/api/consumer/<key>")
    def own_read(key):
        return jsonify(ok=True,contract=repo.read(who(),key))

    @bp.post("/api/contracts")
    def create():return jsonify(ok=True,contract=repo.create(who(write=True),body()))

    @bp.get("/api/quote/<key>")
    def quote(key):return jsonify(ok=True,quote=repo.quote(who(),key))

    @bp.post("/api/provider-event")
    def receive():
        if request.mimetype!="application/json" or request.content_length is None or request.content_length>8192:
            raise ContractError("JSON_BODY_REQUIRED")
        return jsonify(ok=True,contract=repo.receive(request.get_data(),request.headers.get("X-Provider-Signature","")))

    @bp.post("/api/consumer/<key>/cancel")
    def cancel(key):
        value=who(write=True)
        if body()!={"acknowledged":True}:raise ContractError("FINANCIAL_ACK_REQUIRED")
        return jsonify(ok=True,contract=repo.cancel(value,key))

    @bp.post("/api/operator/<key>/release-review")
    def release(key):
        value=who(True,True)
        if body()!={"acknowledged":True}:raise ContractError("FINANCIAL_ACK_REQUIRED")
        return jsonify(ok=True,contract=repo.release_reviews(value,key))

    @bp.post("/api/operator/<key>/execute")
    def execute(key):
        value=who(True,True);repo.read(value,key,operator=True)
        return repo.execute_live()

    return bp
