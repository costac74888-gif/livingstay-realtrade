"""Design composition ONLY for the owned development app.

No application database, provider or production app imports. Native functional
routes keep their handlers. Additional UI routes are distinctly mapped.
"""
import html
import json
import re
from pathlib import Path
from urllib.parse import urlencode
from flask import Response, request, redirect, send_from_directory
from scripts.hs2_seongsu_seed import require_owned

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "scripts/hs2_design_assets"
REGISTRY = ROOT / "scripts/hs2_design_registry.json"


def install(app):
    require_owned(app)
    registry = json.loads(REGISTRY.read_text())
    screens = registry["screens"]
    by_id = {s["id"]: s for s in screens}
    by_path = {s["preview_path"]: s for s in screens if not s.get("native") and not s.get("alias_of")}

    @app.get("/hs2/design-assets/<path:name>")
    def design_asset(name):
        if "/" in name or name.startswith("."):
            return Response(status=404)
        return send_from_directory(ASSETS, name)

    @app.get("/hs2/design-images/<group>/<name>")
    def approved_image(group, name):
        if group not in {"hs2-unified", "hs2-complete"} or "/" in name:
            return Response(status=404)
        return send_from_directory(
            ROOT / "artifacts/mockup-sandbox/public/images" / group, name)

    @app.get("/hs2/admin/preview-exports/<name>")
    def preview_export(name):
        if not app.preview_admin_authorized():
            return Response("관리자 로그인 필요", status=403)
        if name not in {"homenstay-running-preview-comparison.xlsx",
                        "homenstay-running-preview-captures.zip"}:
            return Response(status=404)
        return send_from_directory(ROOT/"generated-artifacts/hs2-integrated-preview",
                                   name, as_attachment=True)

    def page():
        screen = by_path[request.path]
        # Existing before_request protects /hs2/admin; this second check fences
        # any future registry mistake that puts an admin elsewhere.
        if screen["role"] == "관리자" and not app.preview_admin_authorized():
            return Response("관리자 로그인 필요", status=403)
        selected = request.args.get("public_id")
        places = []
        for key, item in app.fixture_demo_catalog.items():
            if item.get("category") not in {"lodging", "non_lodging"}:
                continue
            lodging = item["category"] == "lodging"
            week, month = item.get("weekly_krw"), item.get("monthly_krw")
            photo = (item.get("photos") or ["interior-1.jpg"])[0]
            number = re.search(r"interior-(\d)", photo)
            point = item.get("point") or {}
            places.append(dict(id=key,title=item["name"],neighborhood=item["neighborhood"],
                walk="성수동 인근",guests=item["guests"],rooms=item["rooms"],area=item["area_m2"],
                image=int(number[1]) if number else 1,kind="lodging" if lodging else "home",
                price=(item.get("nightly_krw") if lodging else week or month) or 0,
                basis="day" if lodging else "week" if week else "month",
                description=item["description"],amenities=item["amenities"],
                lat=point.get("lat"),lng=point.get("lng")))
        if selected:
            places.sort(key=lambda p:p["id"] != selected)
        if screen["view"] == "detail-month" and len(places) > 6:
            monthly = next(((key,item) for key,item in app.fixture_demo_catalog.items()
                if item.get("category") == "non_lodging" and item.get("monthly_krw")), None)
            if monthly:
                key,item = monthly
                actual = next(p for p in places if p["id"] == key).copy()
                actual.update(price=item["monthly_krw"],basis="month")
                places[6] = actual
        data = json.dumps({"screen": screen["id"], "screens": screens,"places":places},
                          ensure_ascii=False).replace("<", "\\u003c")
        return Response(
            '<!doctype html><html lang="ko"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{html.escape(screen["title"])} · HOME &amp; STAY</title>'
            '<link rel="stylesheet" href="/hs2/design-assets/app.css">'
            '<script defer src="/hs2/design-assets/app.js"></script>'
            '</head><body><div id="hs-design-page"></div>'
            f'<script type="application/json" id="hs-design-bootstrap">{data}</script>'
            '</body></html>', mimetype="text/html")

    for index, path in enumerate(by_path):
        app.add_url_rule(path, f"hs2_design_page_{index}", page, methods=["GET"])

    @app.before_request
    def semantic_navigation():
        # Original components' internal navigation resolves to normal semantic
        # URLs; arbitrary IDs never grant access or select an admin session.
        selected = request.args.get("screen")
        if request.method == "GET" and selected in by_id and request.path.startswith("/hs2/"):
            target = by_id[selected]["preview_path"]
            carry = {k:request.args[k] for k in
                ("public_id","booking_id","receipt_id","check_in","check_out","guests") if k in request.args}
            if carry:
                base, sep, fragment = target.partition("#")
                target = base + ("&" if "?" in base else "?") + urlencode(carry) + (sep+fragment if sep else "")
            return redirect(target)
        if request.method == "GET" and request.path == "/hs2/details/" and not request.args.get("public_id"):
            # A default owned demo item for the normal detail entry; never
            # overwrite the actual item selected by search or a saved link.
            catalog = app.fixture_demo_catalog
            key = next((key for key, value in catalog.items()
                        if value.get("category") in {"lodging", "non_lodging"}), None)
            if key:
                return redirect("/hs2/details/?public_id=" + key)

    def navigation(role, authorized):
        groups = {
            "사용자": [("숙소 찾기", "/hs2/consumer"), ("관심·대화", "/hs2/workspace/?view=consumer"),
                        ("내 예약", "/hs2/bookings/"), ("내 계정", by_id["C023"]["preview_path"]),
                        ("이용 안내", "/hs2/help/")],
            "임대인": [("시설 지도", "/hs2/owner-map/"), ("매물 관리", "/hs2/listings/"),
                        ("공간 등록", "/hs2/registration/"), ("요금·달력", "/hs2/calendar/"),
                        ("예약 관리", "/hs2/bookings/"), ("운영 현황", "/hs2/dashboard/"),
                        ("대화·알림", "/hs2/workspace/?view=owner")],
            "관리자": [("운영 관리", "/hs2/admin/"), ("등록 심사", "/hs2/listings/admin"),
                        ("예약·금융", "/hs2/finance/")],
        }
        links = "".join(f'<a href="{html.escape(url, quote=True)}">{label}</a>'
                        for label, url in groups[role])
        extra = [s for s in screens if s["role"] == role and s["kind"] == "page"
                 and not s.get("alias_of")]
        seen = set()
        more = []
        for s in extra:
            if s["preview_path"] in seen:
                continue
            seen.add(s["preview_path"])
            more.append(f'<a href="{html.escape(s["preview_path"], quote=True)}">'
                        f'{html.escape(s["title"])}</a>')
        admin = '<a href="/hs2/admin/">관리자</a>' if authorized else ''
        return (
            '<header class="hs-live-header"><a class="hs-live-brand" href="/hs2/consumer">'
            '<img src="/__development__/seongsu/map-assets/brand-logo.png" alt="HOME &amp; STAY"></a>'
            '<button class="hs-live-menu-toggle" id="hs-mobile-menu-toggle" type="button" aria-expanded="false" '
            'aria-controls="hs-main-menu" aria-label="메뉴 열기"><span></span><span></span><span></span></button>'
            '<div class="hs-live-nav-panel" id="hs-main-menu">'
            '<nav aria-label="모드"><a href="/hs2/consumer">머물 곳 찾기</a>'
            f'<a href="/hs2/owner-map/">공간 운영</a>{admin}</nav>'
            '<nav class="hs-live-section-nav" aria-label="주요 메뉴">' + links +
            '<details class="hs-live-more"><summary>전체 메뉴</summary><div>' +
            "".join(more) + '</div></details></nav></div></header>'
        )

    @app.after_request
    def design_shell(response):
        if response.mimetype != "text/html" or not request.path.startswith("/hs2/"):
            return response
        response.direct_passthrough = False
        text = response.get_data(as_text=True)
        authorized = app.preview_admin_authorized()
        screen = by_path.get(request.path)
        role = screen["role"] if screen else (
            "관리자" if request.path.startswith("/hs2/admin") or "/listings/admin" in request.path
            else "임대인" if request.path.startswith(("/hs2/owner", "/hs2/calendar", "/hs2/listings",
                                                       "/hs2/registration", "/hs2/dashboard"))
            or request.args.get("view") == "owner" else "사용자")
        context_query = {k:request.args[k] for k in
            ("public_id","booking_id","receipt_id","check_in","check_out","guests") if k in request.args}
        def contextual(path):
            if not context_query:
                return path
            base, sep, fragment = path.partition("#")
            return base + ("&" if "?" in base else "?") + urlencode(context_query) + (sep+fragment if sep else "")
        route_map = {s["id"]: contextual(s["preview_path"]) for s in screens}
        safe_map = json.dumps(route_map, ensure_ascii=False).replace("<", "\\u003c")
        # Supplemental contextual states never appear as an inspection gallery.
        current = screen or next((s for s in screens if s["preview_path"].split("?")[0] == request.path), None)
        related = [] if not current else [
            s for s in screens if s.get("flow_parent") == current["id"]
            and s["id"] != current["id"] and s["kind"] in {"tab", "popup"}]
        context = '<nav class="hs-live-context" aria-label="세부 항목">' + "".join(
            f'<a href="{html.escape(contextual(s["preview_path"]), quote=True)}">{html.escape(s["title"])}</a>'
            for s in related) + '</nav>' if related else ''
        boot = (f'<script type="application/json" id="hs-live-routes">{safe_map}</script>'
                '<script defer src="/hs2/design-assets/shell.js"></script>'
                '<script defer src="/hs2/design-assets/responsive.js"></script>')
        styles = ('<link rel="stylesheet" href="/hs2/design-assets/shell.css">'
                  '<link rel="stylesheet" href="/hs2/design-assets/responsive.css">'
                  '<meta http-equiv="Content-Security-Policy" content="upgrade-insecure-requests">')
        text = text.replace("</head>", styles + "</head>", 1)
        text = re.sub(r'(<body\b[^>]*>)', lambda m: m[1] + navigation(role, authorized) + context,
                      text, count=1, flags=re.I)
        text = text.replace("</body>", boot + "</body>", 1)
        response.set_data(text)
        response.headers["Cache-Control"] = "no-store, private"
        csp = response.headers.get("Content-Security-Policy", "")
        if csp and "upgrade-insecure-requests" not in csp:
            response.headers["Content-Security-Policy"] = csp + "; upgrade-insecure-requests"
        return response
