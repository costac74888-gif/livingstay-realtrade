from pathlib import Path
from flask import Blueprint,jsonify,request,send_from_directory
from hs2_design.domain import ContractError
from hs2_details.contracts import consumer
import secrets

WEB=Path(__file__).parent/"web"


def create_blueprint(repo,*,current_consumer,current_operator,csrf_for,allow_request):
    if not all(callable(p) for p in (current_consumer,current_operator,csrf_for,allow_request)):raise ValueError("Trusted identity and budget ports required")
    bp=Blueprint("hs2_workspace",__name__,url_prefix="/hs2/workspace")

    @bp.before_request
    def budget():
        if "/api/" not in request.path:return
        if allow_request() is not True:raise ContractError("WORKSPACE_RATE_LIMIT")
        if set(request.args)-{"view"} or request.args.get("view","consumer") not in {"consumer","operator"}:raise ContractError("INVALID_WORKSPACE_FILTER")
        if request.method not in {"GET","HEAD"}:
            who=current_consumer()
            consumer(who)
            token=csrf_for(who)
            provided=request.headers.get("X-HS2-CSRF","")
            if type(token) is not str or not token or not token.isascii() or not provided.isascii() or not secrets.compare_digest(provided,token):raise ContractError("CSRF_REQUIRED")

    @bp.after_request
    def headers(r):
        r.headers["Cache-Control"]="no-store";r.headers["X-Content-Type-Options"]="nosniff";r.headers["Referrer-Policy"]="same-origin"
        return r

    @bp.errorhandler(ContractError)
    def error(e):
        code=str(e)
        return jsonify(ok=False,code=code),429 if code=="WORKSPACE_RATE_LIMIT" else 404 if code.endswith("NOT_FOUND") else 403

    def identity():
        operator=request.args.get("view")=="operator"
        return (current_operator() if operator else current_consumer()),operator

    def data(keys):
        raw=request.get_json(silent=True)
        if type(raw) is not dict or set(raw)!=set(keys):raise ContractError("INVALID_WORKSPACE_COMMAND")
        return raw

    @bp.get("/")
    def page():return send_from_directory(WEB,"workspace.html")

    @bp.get("/assets/<name>")
    def asset(name):
        if name not in {"workspace.js","workspace.css"}:raise ContractError("ASSET_NOT_FOUND")
        return send_from_directory(WEB,name)

    @bp.get("/api/meta")
    def meta():
        who,operator=identity()
        with repo.registrations.transaction() as c:repo.active(c,who,operator)
        return jsonify(ok=True,view="operator" if operator else "consumer",csrf=csrf_for(current_consumer()),live_delivery_enabled=False)

    @bp.get("/api/favorites")
    def favorites():return jsonify(ok=True,items=repo.favorites(current_consumer()))

    @bp.put("/api/favorites/<key>")
    def favorite(key):return jsonify(ok=True,item=repo.favorite(current_consumer(),key,data(["enabled"])["enabled"]))

    @bp.get("/api/threads")
    def threads():
        who,operator=identity()
        return jsonify(ok=True,items=repo.threads(who,operator))

    @bp.post("/api/threads")
    def open_thread():
        raw=request.get_json(silent=True)
        if type(raw) is not dict or set(raw) not in ({"public_id"},{"booking_id"}):raise ContractError("ONE_CHAT_REFERENCE_REQUIRED")
        return jsonify(ok=True,**repo.open_thread(current_consumer(),**raw))

    @bp.get("/api/threads/<key>/messages")
    def messages(key):
        who,operator=identity()
        return jsonify(ok=True,items=repo.messages(who,key,operator))

    @bp.post("/api/threads/<key>/messages")
    def send(key):
        raw=data(["body","request_id"]);who,operator=identity()
        return jsonify(ok=True,**repo.send(who,key,raw["body"],raw["request_id"],operator))

    @bp.post("/api/threads/<key>/read")
    def read_thread(key):
        raw=data(["through_message_id"]);who,operator=identity()
        return jsonify(ok=True,**repo.read_thread(who,key,raw["through_message_id"],operator))

    @bp.get("/api/preferences")
    def prefs():return jsonify(ok=True,preferences=repo.preferences(current_consumer()))

    @bp.put("/api/preferences")
    def save_prefs():return jsonify(ok=True,preferences=repo.preferences(current_consumer(),data(["email_enabled","sms_enabled"])))

    @bp.get("/api/notifications")
    def notifications():return jsonify(ok=True,items=repo.notifications(current_consumer()))

    @bp.post("/api/notifications/<key>/read")
    def read_notification(key):
        data([])
        return jsonify(ok=True,**repo.read_notification(current_consumer(),key))

    @bp.post("/api/deliveries/<key>/retry")
    def retry(key):
        data([])
        return jsonify(ok=True,**repo.retry_delivery(current_consumer(),key))

    return bp
