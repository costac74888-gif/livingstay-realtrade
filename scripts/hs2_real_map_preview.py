"""Owned Preview composition of the existing Kakao map tools, not production."""
import html
import os
from pathlib import Path
from urllib.parse import urlencode
from flask import Response, jsonify, send_from_directory
from scripts.hs2_seongsu_seed import require_owned

ROOT = Path(__file__).resolve().parents[1]


def section(text, start, end):
    """Fail closed if the original source composition contract changes."""
    if text.count(start) != 1 or text.count(end) != 1:
        raise RuntimeError("Legacy map source boundary changed")
    return text.split(start, 1)[1].split(end, 1)[0]


def install(app):
    require_owned(app)
    legacy_html = (ROOT / "static/index.html").read_text()
    toolbar = '<div class="map-toolbar"' + section(
        legacy_html, '<div class="map-toolbar"',
        '<!-- 지도 위 상단 검색바 (기본 접힘) -->')
    legacy_js = (ROOT / "static/js/main.js").read_text()
    tools = 'const MAP_TYPE_STEPS = [' + section(
        legacy_js, 'const MAP_TYPE_STEPS = [',
        '// 새 레이어가 준비될 때까지 기존 CustomOverlay를')
    icons = 'function initMapToolIcons(){' + section(
        legacy_js, 'function initMapToolIcons(){', 'async function initMap(){')
    # The original tool handlers/overlays/state/roadview mini-map remain intact.
    # Only their host map and notifications are supplied by the owned shell.
    wrapper = """
let kakaoMap = null;
function escapeHtml(value){return String(value??"").replace(/[&<>"']/g,
  c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));}
function showFallbackToast(message){
 const el=document.getElementById("statusMessage");el.textContent=message;
}
"""
    bridge = """
window.HS2LegacyMapTools={
 mount(map){kakaoMap=map;initMapToolIcons();_initMapToolControls();
 _bindMapToolMapEvents();kakao.maps.event.addListener(map,"idle",_schedulePoiRefresh);},
 state(){return {active:_activeMapTool,mapType:MAP_TYPE_STEPS[_mapTypeIndex].key,
 measurePoints:_measurePoints.length,poiCount:_mapToolOverlays.length,
 roadviewOpen:!!document.getElementById("roadviewPanel")?.classList.contains("open")};}
};
"""

    def page():
        key = os.environ.get("HS2_PREVIEW_MAP_JS_KEY", "")
        text = (ROOT / "scripts/hs2_demo_assets/map.html").read_text()
        sdk = ""
        if key:
            # Standard original client SDK; no key persistence or fake SDK.
            url = "https://dapi.kakao.com/v2/maps/sdk.js?" + urlencode({
                "appkey": key, "autoload": "false", "libraries": "services"})
            sdk = '<script defer src="' + html.escape(url, quote=True) + '"></script>'
        return Response(text.replace("<!--LEGACY_MAP_TOOLS-->", toolbar)
                        .replace("<!--REAL_MAP_SDK-->", sdk), mimetype="text/html")

    # Development-only override: production/shared consumer template untouched.
    app.view_functions["hs2_private_consumer.page"] = page
    # Resolve blueprint endpoint names explicitly instead of assuming aliases.
    for rule in app.url_map.iter_rules():
        if rule.rule in {"/hs2/consumer", "/hs2/search/", "/hs2/search/mobile/"}:
            app.view_functions[rule.endpoint] = page

    @app.get("/__development__/seongsu/map-assets/<name>")
    def real_map_asset(name):
        if name == "legacy-tools.js":
            return Response(wrapper + tools + icons + bridge,
                            mimetype="application/javascript")
        targets = {
            "brand-logo.png": ("attached_assets", "HOME_STAY_logo_3_BlackWhite_OnBlack_1791718519754.png"),
            "brand-icon.png": ("attached_assets", "앱로고home_stay_share_1791718522426.png"),
            "icons.js": ("static/js", "icons.js"),
            "legacy.css": ("static/css", "main.css"),
            "map.css": ("scripts/hs2_demo_assets", "map.css"),
            "reference.css": ("scripts/hs2_demo_assets", "reference.css"),
            "preview-presentation.js": ("scripts/hs2_demo_assets", "preview-presentation.js"),
            "preview-rate-date.js": ("scripts/hs2_demo_assets", "preview-rate-date.js"),
            "rate-preview.css": ("scripts/hs2_demo_assets", "rate-preview.css"),
            "detail-map.js": ("scripts", "hs2_detail_real_map.js"),
            "demo-role.js": ("scripts/hs2_demo_assets", "demo-role.js"),
            "map.js": ("scripts", "hs2_real_map.js"),
        }
        if name not in targets:
            return jsonify(ok=False, code="NOT_FOUND"), 404
        directory, filename = targets[name]
        return send_from_directory(ROOT / directory, filename)

    @app.get("/__development__/seongsu/map-status")
    def map_status():
        return jsonify(ok=True, provider="existing_kakao_maps", schematic=False,
            key_configured=bool(os.environ.get("HS2_PREVIEW_MAP_JS_KEY")),
            tools_source="original_static_main", data_source="owned_synthetic",
            official_school_assignment=False)

    @app.after_request
    def reference_theme(response):
        if response.mimetype == "text/html":
            response.direct_passthrough = False
            text = response.get_data(as_text=True)
            import re
            # Override only the owned Preview's brand metadata, rather than
            # leaving an older native icon/share image first in the document.
            text = re.sub(
                r"""<link\b(?=[^>]*\brel\s*=\s*["'](?:icon|shortcut icon|apple-touch-icon)["'])[^>]*>""",
                "", text, flags=re.IGNORECASE)
            text = re.sub(
                r"""<meta\b(?=[^>]*\bproperty\s*=\s*["']og:image["'])[^>]*>""",
                "", text, flags=re.IGNORECASE)
            domain = os.environ.get("REPLIT_DEV_DOMAIN", "")
            icon_path = "/__development__/seongsu/map-assets/brand-icon.png"
            share_icon = ("https://" + domain + icon_path
                          if re.fullmatch(r"[A-Za-z0-9.-]+\.replit\.dev", domain)
                          else icon_path)
            assets = '<link rel="icon" type="image/png" href="/__development__/seongsu/map-assets/brand-icon.png">'
            assets += '<link rel="apple-touch-icon" href="/__development__/seongsu/map-assets/brand-icon.png">'
            assets += '<meta property="og:image" content="' + html.escape(share_icon, quote=True) + '">'
            assets += '<link rel="stylesheet" href="/__development__/seongsu/map-assets/reference.css">'
            if "map-assets/preview-rate-date.js" not in text:
                text = text.replace("<head>", '<head><script defer src="/__development__/seongsu/map-assets/preview-rate-date.js"></script>', 1)
                assets += '<link rel="stylesheet" href="/__development__/seongsu/map-assets/rate-preview.css">'
            assets += '<script defer src="/__development__/seongsu/map-assets/preview-presentation.js"></script>'
            if 'id="detail-content"' in text:
                key = os.environ.get("HS2_PREVIEW_MAP_JS_KEY", "")
                if key:
                    url = "https://dapi.kakao.com/v2/maps/sdk.js?" + urlencode({
                        "appkey": key, "autoload": "false", "libraries": "services"})
                    assets += '<script defer src="' + html.escape(url, quote=True) + '"></script>'
                assets += '<script defer src="/__development__/seongsu/map-assets/detail-map.js"></script>'
            text = text.replace("</head>", assets + "</head>", 1)
            response.set_data(text)
            # Original policy predates Kakao's current CDN. Limit this exception
            # to the owned Preview; keep production/auth/payment egress isolated.
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self' https://dapi.kakao.com "
                "https://t1.kakaocdn.net https://t1.daumcdn.net https://map.kakao.com https://rv.map.kakao.com; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                "font-src 'self' https://fonts.gstatic.com; "
                "img-src 'self' https://*.daumcdn.net https://*.kakaocdn.net data: blob:; "
                "connect-src 'self' https://dapi.kakao.com https://*.daumcdn.net "
                "https://*.kakaocdn.net https://map.kakao.com https://rv.map.kakao.com; "
                "frame-src 'self' https://map.kakao.com https://rv.map.kakao.com https://*.daum.net; "
                "frame-ancestors 'self'; object-src 'none'; base-uri 'self'; form-action 'self'"
            )
        return response
