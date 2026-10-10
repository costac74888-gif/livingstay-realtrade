from pathlib import Path
from flask import Blueprint,jsonify,request,send_from_directory
from hs2_design.domain import ContractError
from .content import content

WEB=Path(__file__).parent/"web"


def create_blueprint(*,content_for=content):
    if not callable(content_for):raise ValueError("Trusted first-party content port required")
    bp=Blueprint("hs2_help",__name__,url_prefix="/hs2/help")

    @bp.after_request
    def headers(r):
        r.headers["Cache-Control"]="no-store";r.headers["X-Content-Type-Options"]="nosniff"
        r.headers["Referrer-Policy"]="same-origin"
        return r

    @bp.errorhandler(ContractError)
    def error(e):return jsonify(ok=False,code=str(e)),400

    @bp.get("/")
    def page():return send_from_directory(WEB,"help.html")

    @bp.get("/assets/<name>")
    def asset(name):
        if name not in {"help.js","help.css"}:raise ContractError("ASSET_NOT_FOUND")
        return send_from_directory(WEB,name)

    @bp.get("/api/content")
    def read():
        if set(request.args)-{"audience","q"}:raise ContractError("UNKNOWN_HELP_FILTER")
        audience=request.args.get("audience","all");q=request.args.get("q","").strip()
        if audience not in {"all","consumer","operator","special"} or len(q)>80:raise ContractError("INVALID_HELP_FILTER")
        body=content_for()
        if not isinstance(body,dict) or body.get("live_operations_approved") is not False or not body.get("version"):raise ContractError("REVIEWED_HELP_CONTENT_REQUIRED")
        body={**body,"faqs":[f for f in body["faqs"] if (audience=="all" or f["audience"]==audience)
            and (not q or q.casefold() in (f["topic"]+f["question"]+f["answer"]).casefold())]}
        return jsonify(ok=True,**body)

    return bp
