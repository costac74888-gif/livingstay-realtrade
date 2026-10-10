"""Trusted catalog/SDK callbacks, no credential/DB/provider default or live mount."""
from pathlib import Path
from flask import Blueprint, jsonify, request, send_from_directory
from hs2_design.domain import ContractError
from .search import query, search

WEB = Path(__file__).parent / "web"


def create_blueprint(*, public_catalog, map_config):
    bp = Blueprint("hs2_private_consumer", __name__)

    @bp.after_request
    def headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        return response

    @bp.get("/hs2/consumer")
    def main():
        return send_from_directory(WEB, "main.html")

    @bp.get("/hs2/consumer-assets/<path:name>")
    def assets(name):
        if name not in {"main.js", "main.css"}:
            return jsonify(ok=False, code="NOT_FOUND"), 404
        return send_from_directory(WEB, name)

    @bp.get("/hs2/api/consumer/search")
    def results():
        if any(len(request.args.getlist(k)) != 1 for k in request.args):
            return jsonify(ok=False, code="DUPLICATE_FILTER", message="검색 조건이 중복되었습니다."), 400
        try:
            values = query(request.args.to_dict())
        except ContractError as exc:
            return jsonify(ok=False, code=str(exc),
                           message="날짜와 검색 조건을 확인해주세요. 가격은 선택 기간 총액 기준입니다."), 400
        try:
            data = search(values, public_catalog)
            config = map_config()
            # No fake empty success when the data source/SDK callback fails.
            return jsonify(ok=True, query=values, map_config=config, **data)
        except Exception:
            return jsonify(ok=False, code="CATALOG_UNAVAILABLE",
                           message="매물 정보를 확인하지 못했습니다. 다시 시도해주세요."), 503

    return bp
