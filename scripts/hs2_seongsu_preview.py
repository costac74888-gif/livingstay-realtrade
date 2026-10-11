"""Development-only response enrichment; never mounted in app.py or production."""
from pathlib import Path
from flask import jsonify, request, send_from_directory
import hmac
import time
from uuid import uuid4
from datetime import date, timedelta
from hs2_design.domain import ContractError
from hs2_supermap.contracts import parse, slots
from scripts.hs2_seongsu_seed import require_owned, seed_seongsu

ROOT = Path(__file__).resolve().parents[1]


def install(app):
    require_owned(app)
    catalog = seed_seongsu(app)

    def consumer_results():
        if any(len(request.args.getlist(k)) != 1 for k in request.args):
            return jsonify(ok=False, code="DUPLICATE_FILTER"), 400
        try:
            values = parse(request.args.to_dict())
            values["layers"] = ["stay"]
            result = app.fixture_supermap.search(values)
            # Original protected consumer shape is retained. The only extra
            # information is deliberately fictional preview_demo data.
            items = [dict(row, location_precision="withheld") for row in result["items"]]
            return jsonify(ok=True, items=items, query=values, count=len(items),
                unquoted_count=sum(not row.get("quote") for row in items),
                price_basis="selected_stay_total",
                map_config=dict(sdk_url="/hs2/consumer-fixture-sdk.js"))
        except ContractError as exc:
            return jsonify(ok=False, code=str(exc), message="테스트 검색 조건을 확인하세요."), 400

    app.view_functions["hs2_private_consumer.results"] = consumer_results

    @app.get("/__development__/seongsu/")
    def guide():
        return send_from_directory(ROOT / "scripts/hs2_demo_assets", "guide.html")

    @app.get("/__development__/seongsu/catalog")
    def demo_catalog():
        return jsonify(ok=True, synthetic=True, items=list(catalog.values()),
            stay_count=14, native_counts=dict(sale=3, business=3, auction=3),
            default_check_in=min(m["available_from"] for m in catalog.values()),
            actual_toss=False, payment_provider="OwnedSandbox_mock",
            account_mode="shared_auto_fixture_101")

    @app.get("/__development__/seongsu/assets/<name>")
    def asset(name):
        if name not in {f"interior-{n}.jpg" for n in range(1, 5)}:
            return jsonify(ok=False, code="NOT_FOUND"), 404
        return send_from_directory(ROOT / "scripts/hs2_demo_assets", name)

    @app.post("/__development__/seongsu/payments/<key>/capture")
    def mock_capture(key):
        require_owned(app)
        expected = "isolated-consumer-csrf-not-real-session"
        provided = request.headers.get("X-CSRF-Token", "")
        if not provided.isascii() or not hmac.compare_digest(expected, provided):
            return jsonify(ok=False, code="CSRF_REQUIRED"), 403
        if (request.mimetype != "application/json" or request.content_length is None
                or request.content_length > 2048
                or request.get_json(silent=True) != {"acknowledged": True}):
            return jsonify(ok=False, code="EXPLICIT_MOCK_PAYMENT_ACK_REQUIRED"), 400
        try:
            from hs2_finance.fixtures import OwnedSandbox
            provider = app.fixture_payment_provider
            if type(provider) is not OwnedSandbox or provider.sandbox is not True:
                raise RuntimeError("Only owned signed mock provider allowed")
            contract = app.fixture_finance.read(app.fixture_consumer, key)
            if contract["status"] == "captured":
                # Refresh/retry never signs or applies a second capture.
                return jsonify(ok=True, contract=contract, provider="OwnedSandbox_mock",
                    actual_toss=False, actual_money_executed=False)
            if contract["status"] != "awaiting_payment":
                return jsonify(ok=False, code="MOCK_CAPTURE_STATE_REQUIRED"), 409
            raw, signature = provider.sign(dict(
                event_id=str(uuid4()), contract_id=key, reference="owned-seongsu:"+key,
                kind="capture", amount_krw=contract["terms"]["payable_krw"],
                currency="KRW", issued_at=int(time.time())))
            contract = app.fixture_finance.receive(raw, signature)
            return jsonify(ok=True, contract=contract, provider="OwnedSandbox_mock",
                actual_toss=False, actual_money_executed=False)
        except ContractError as exc:
            return jsonify(ok=False, code=str(exc)), 400

    # Existing reviewed owned SDK URL/endpoint, now with actual per-point
    # positioning against an explicitly synthetic district diagram.
    app.view_functions["sdk"] = lambda: send_from_directory(ROOT / "scripts", "hs2_demo_map.js")

    @app.after_request
    def enrich(response):
        if response.mimetype == "text/html":
            response.direct_passthrough = False
            text = response.get_data(as_text=True)
            import re
            text = re.sub(r"(<body\b)", r'\1 data-hs2-demo="seongsu"', text, count=1)
            text = text.replace('href="/hs2/mode"', 'href="/__development__/seongsu/"')
            response.set_data(text)
        if response.is_json and response.status_code == 200:
            data = response.get_json()
            occupied = {}
            if request.path.startswith(("/hs2/api/consumer/", "/hs2/search/api/", "/hs2/details/api/items/")):
                from hs2_supermap.fixtures import WHO
                for booking in app.fixture_bookings.list(WHO, operator=True):
                    if not booking["inventory_held"] and booking["status"] != "confirmed":
                        continue
                    start = date.fromisoformat(booking["check_in"])
                    end = date.fromisoformat(booking["check_out"])
                    occupied.setdefault(booking["public_id"], set()).update(
                        (start + timedelta(days=n)).isoformat() for n in range((end-start).days))
            def decorate(value):
                if isinstance(value, dict):
                    key = value.get("public_id")
                    if key in catalog:
                        meta = dict(catalog[key])
                        meta["blocked_dates"] = sorted(
                            set(meta["blocked_dates"]) | occupied.get(key, set()))
                        value["preview_demo"] = meta
                        if "layer" in value or "marker_shape" in value:
                            value["point"] = dict(**meta["point"], precision="exact",
                                radius_m=0, label="가상 좌표 · 실제 주소 아님")
                    for key, child in list(value.items()):
                        if key != "preview_demo":
                            decorate(child)
                elif isinstance(value, list):
                    for child in value:
                        decorate(child)
            decorate(data)
            if request.path == "/hs2/finance/api/session":
                data["preview_demo_capture_available"] = True
            if request.path == "/hs2/search/api/results" and isinstance(data.get("items"), list):
                data["markers"] = slots(data["items"])
                data["withheld_count"] = 0
            response.set_data(app.json.dumps(data))
        return response
