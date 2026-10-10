from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from flask import Blueprint, jsonify, request, send_from_directory
from hs2_design.domain import ContractError
from .contracts import parse

WEB = Path(__file__).parent / "web"


def create_blueprint(repo, *, map_config, allow_request):
    if not all(callable(p) for p in (map_config, allow_request)):
        raise ValueError("Trusted SDK/budget ports required")
    bp = Blueprint("hs2_supermap", __name__, url_prefix="/hs2/search")

    @bp.before_request
    def budget():
        if "/api/" in request.path and allow_request() is not True:
            raise ContractError("MAP_RATE_LIMIT")

    @bp.after_request
    def headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @bp.errorhandler(ContractError)
    def error(exc):
        code = str(exc)
        return jsonify(ok=False, code=code), 429 if code == "MAP_RATE_LIMIT" else 404 if code.endswith("NOT_FOUND") else 400

    @bp.get("/")
    def page():
        return send_from_directory(WEB, "search.html")

    @bp.get("/assets/<name>")
    def assets(name):
        if name not in {"search.js", "search.css", "controller.js"}:
            raise ContractError("ASSET_NOT_FOUND")
        return send_from_directory(WEB, name)

    def values():
        if any(len(request.args.getlist(k)) != 1 for k in request.args):
            raise ContractError("DUPLICATE_FILTER")
        return parse(request.args.to_dict())

    @bp.get("/api/results")
    def results():
        parsed = values()
        config = map_config()
        if not isinstance(config, dict) or not isinstance(config.get("sdk_url"), str):
            raise ContractError("SDK_CONFIG_REQUIRED")
        try:
            url = urlsplit(config["sdk_url"])
            fixture = config["sdk_url"] == "/hs2/supermap-fixture-sdk.js"
            kakao = (url.scheme == "https" and url.hostname == "dapi.kakao.com"
                and url.port in {None, 443} and url.path == "/v2/maps/sdk.js"
                and not url.username and not url.password and not url.fragment
                and not set(parse_qs(url.query)) - {"appkey", "autoload", "libraries"})
            if not (fixture or kakao):
                raise ValueError()
        except ValueError:
            raise ContractError("SDK_CONFIG_REQUIRED") from None
        # A trusted SDK port still cannot accidentally serialize other config
        # values into a public API. The frontend validates the SDK URL host/path.
        return jsonify(ok=True, query=parsed, map_config={"sdk_url": config["sdk_url"]}, **repo.search(parsed))

    @bp.get("/api/detail/<layer>/<key>")
    def detail(layer, key):
        return jsonify(ok=True, **repo.detail(layer, key, values()))

    return bp
