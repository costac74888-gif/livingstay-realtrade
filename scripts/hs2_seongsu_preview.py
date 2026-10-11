"""Development-only response enrichment; never mounted in app.py or production."""
from pathlib import Path
from flask import jsonify, request, send_from_directory, session, Response
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
    from scripts.hs2_rate_preview import install as install_rate_preview
    install_rate_preview(app)

    @app.before_request
    def include_new_owned_registrations():
        # Approval stays in the existing reviewed repository. Do not silently
        # auto-approve or turn an unreviewed registration into a public listing.
        from hs2_supermap.fixtures import WHO
        from hashlib import sha256
        for row in app.fixture_repo.list(WHO):
            key = row.get("public_id")
            if not key or key in catalog or row["status"] != "approved":
                continue
            p = row["payload"]
            offset = int(sha256(key.encode()).hexdigest()[:8], 16) % 16
            catalog[key] = dict(
                synthetic=True, name="[가상 등록] 테스트 공간",
                description="사용자가 격리 Preview에서 등록·검토한 가상 공간. 실제 주소·권한·영업 확인 아님.",
                disclaimer="테스트용 가상 등록 · 실제 매물 아님",
                photos=["/__development__/seongsu/assets/interior-1.jpg"],
                category=p["stay_kind"], neighborhood="성수동 테스트 구역",
                area_m2=float(p["area_m2"]), rooms=p["rooms"], guests=p["guests"],
                amenities=p["options"], nightly_krw=p.get("nightly"),
                weekly_krw=p.get("weekly"), monthly_krw=p.get("monthly"),
                available_from=None, available_until=None, blocked_dates=[],
                booking_supported=True, calendar_setup_required=True,
                point=dict(lat=37.541 + (offset % 4) * .0008,
                           lng=127.045 + (offset // 4) * .001),
                application_id=row["id"],
            )

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
            return jsonify(ok=True, items=items, query=values, count=result["counts"].get("stay", 0),
                period_hidden_count=result["period_hidden_count"],
                unquoted_count=sum(not row.get("quote") for row in items),
                price_basis="selected_stay_total",
                map_config=dict(sdk_url="/hs2/consumer-fixture-sdk.js"))
        except ContractError as exc:
            return jsonify(ok=False, code=str(exc), message="테스트 검색 조건을 확인하세요."), 400

    app.view_functions["hs2_private_consumer.results"] = consumer_results

    @app.get("/__development__/seongsu/")
    def guide():
        return send_from_directory(ROOT / "scripts/hs2_demo_assets", "guide.html")

    @app.get("/__development__/seongsu/comparison")
    def comparison():
        return send_from_directory(ROOT / "generated-artifacts/seongsu-preview", "preservation-review.html")

    @app.get("/__development__/seongsu/catalog")
    def demo_catalog():
        return jsonify(ok=True, synthetic=True, items=[dict(v, public_id=k) for k, v in catalog.items()],
            initial_stay_count=14,
            stay_count=sum(v.get("category") in {"lodging", "non_lodging"} for v in catalog.values()),
            native_counts=dict(sale=3, business=3, auction=3),
            default_check_in=min(m["available_from"] for m in catalog.values() if m["available_from"]),
            actual_toss=False, payment_provider="OwnedSandbox_mock",
            account_mode="shared_auto_fixture_101")

    @app.get("/__development__/seongsu/assets/<name>")
    def asset(name):
        if name not in {f"interior-{n}.jpg" for n in range(1, 5)}:
            return jsonify(ok=False, code="NOT_FOUND"), 404
        return send_from_directory(ROOT / "scripts/hs2_demo_assets", name)

    @app.get("/__development__/seongsu/admin-role")
    def mock_admin_role():
        require_owned(app)
        return Response("""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>가상 관리자 체험</title>
<script defer src="/__development__/seongsu/map-assets/demo-role.js"></script></head>
<body><main style="max-width:700px;margin:32px auto;padding:24px;font:16px/1.7 sans-serif">
<h1>가상 관리자 700 체험</h1><p>격리 임시 원장의 등록을 검토하는 역할입니다.
실제 운영 로그인·관리자 권한을 얻거나 운영 신청을 승인하지 않습니다.</p>
<label><input type="checkbox" id="demo-role-ack"> 실제 운영 권한이 아닌 가상 역할임을 확인했습니다.</label>
<p><button id="demo-role-start" type="button" disabled>가상 관리자 역할 시작</button></p>
<p id="demo-role-status" role="status"></p>
<a href="/__development__/legacy-capabilities/">기능 연결표로 돌아가기</a></main></body></html>""",
                        mimetype="text/html")

    @app.post("/__development__/seongsu/admin-role")
    def start_mock_admin_role():
        require_owned(app)
        expected = "isolated-consumer-csrf-not-real-session"
        provided = request.headers.get("X-CSRF-Token", "")
        if not provided.isascii() or not hmac.compare_digest(expected, provided):
            return jsonify(ok=False, code="CSRF_REQUIRED"), 403
        if (request.mimetype != "application/json" or request.content_length is None
                or request.content_length > 1024
                or request.get_json(silent=True) != {"acknowledged_mock_admin": True}):
            return jsonify(ok=False, code="EXPLICIT_MOCK_ROLE_ACK_REQUIRED"), 400
        session["fixture_admin"] = True
        return jsonify(ok=True, synthetic=True, actual_auth=False, role="mock_admin_700")

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
            text = text.replace("</head>", '<link rel="stylesheet" href="/__development__/seongsu/map-assets/preview-readability.css"></head>')
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
                    if key in catalog and not ("total_krw" in value and "check_in" in value):
                        meta = dict(catalog[key])
                        meta["blocked_dates"] = sorted(
                            set(meta["blocked_dates"]) | occupied.get(key, set()))
                        if request.path.startswith(("/hs2/api/consumer/", "/hs2/search/api/")):
                            # Search display data is fictional, but still never
                            # promotes calendar internals/protected identifiers.
                            allowed = {"synthetic", "name", "description", "disclaimer",
                                "photos", "category", "neighborhood", "area_m2", "rooms",
                                "guests", "amenities", "point", "booking_supported",
                                "calendar_setup_required"}
                            if value.get("layer") not in {"stay", None}:
                                allowed.add("test_asking_krw")
                            meta = {k: v for k, v in meta.items() if k in allowed}
                            if value.get("layer") == "stay":
                                summary = value.get("summary") or {}
                                for field in ("area_m2", "rooms", "guests"):
                                    meta[field] = summary.get(field)
                                meta["amenities"] = summary.get("options", [])
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
