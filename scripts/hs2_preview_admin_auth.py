"""Administrator-only access for the owned development Preview, not host auth.

No public role selection. No default credentials, production account lookup,
provider keys, DB changes or real operational authority.
"""
import os
import secrets
import time
from collections import defaultdict
from flask import Response, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash
from scripts.hs2_seongsu_seed import require_owned


def install(app):
    require_owned(app)
    app.secret_key = secrets.token_urlsafe(48)
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")
    password = os.environ.get("HS2_PREVIEW_ADMIN_PASSWORD", "")
    password_hash = generate_password_hash(password) if len(password) >= 12 else None
    del password
    app.config["HS2_PREVIEW_ADMIN_HASH"] = password_hash
    attempts = defaultdict(list)

    def authorized():
        return (session.get("hs2_verified_admin") is True
                and session.get("fixture_admin") is True
                and type(session.get("hs2_admin_login_at")) in {int, float}
                and 0 <= time.time() - session["hs2_admin_login_at"] < 8 * 3600)

    app.preview_admin_authorized = authorized

    @app.before_request
    def enforce():
        path = request.path
        # This old fixture endpoint can otherwise manufacture an admin session.
        if path in {"/hs2/listings-fixture/identity",
                    "/__development__/seongsu/admin-role"}:
            return jsonify(ok=False, code="PUBLIC_ROLE_SWITCH_DISABLED"), 403
        if path.startswith(("/hs2/admin", "/hs2/listings/admin")):
            if path in {"/hs2/admin/login", "/hs2/admin/logout"}:
                return None
            if not authorized():
                return jsonify(ok=False, code="ADMIN_REQUIRED"), 403
        if not authorized():
            session.pop("fixture_admin", None)

    @app.get("/hs2/admin/login")
    def login_page():
        if "hs2_admin_login_csrf" not in session:
            session["hs2_admin_login_csrf"] = secrets.token_urlsafe(32)
        # Token is consumed only by the server-owned same-origin login script.
        html = """<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>관리자 로그인 · HOME &amp; STAY</title>
<script defer src="/__development__/seongsu/map-assets/admin-login.js"></script>
</head><body><header class="site-nav"><a class="brand" href="/hs2/consumer">
<img class="preview-brand-logo" src="/__development__/seongsu/map-assets/brand-logo.png" alt="HOME &amp; STAY"></a>
<a href="/hs2/consumer">숙소 찾기</a></header>
<main class="shell" style="max-width:560px;margin:48px auto;padding:24px">
<h1>관리자 로그인</h1><p>관리자 계정으로 로그인한 경우에만 신청 검토와 관리 화면에 접근할 수 있습니다.</p>
<form id="admin-login-form"><label>관리자 계정<input name="username" autocomplete="username" required></label>
<label>비밀번호<input name="password" type="password" autocomplete="current-password" required></label>
<input name="csrf" type="hidden" value="__TOKEN__">
<button class="primary" type="submit">관리자 로그인</button></form>
<p id="admin-login-feedback" role="status"></p>
<p>이 환경은 개발용 가상 원장입니다. 운영 관리자 계정과 실제 결제 권한을 부여하지 않습니다.</p>
</main></body></html>"""
        return Response(html.replace("__TOKEN__", session["hs2_admin_login_csrf"]),
                        mimetype="text/html")

    @app.post("/hs2/admin/login")
    def login():
        raw = request.get_json(silent=True)
        if (type(raw) is not dict or set(raw) != {"username", "password", "csrf"}
                or not all(type(v) is str for v in raw.values())
                or max(map(len, raw.values())) > 1024):
            return jsonify(ok=False, code="INVALID_LOGIN"), 400
        csrf = session.get("hs2_admin_login_csrf")
        if not csrf or not raw["csrf"].isascii() or not secrets.compare_digest(csrf, raw["csrf"]):
            return jsonify(ok=False, code="CSRF_REQUIRED"), 403
        digest = app.config.get("HS2_PREVIEW_ADMIN_HASH")
        if not digest:
            return jsonify(ok=False, code="ADMIN_ACCOUNT_NOT_CONFIGURED"), 503
        peer = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
        now = time.monotonic()
        attempts[peer] = [t for t in attempts[peer] if now - t < 900]
        if len(attempts[peer]) >= 5:
            return jsonify(ok=False, code="LOGIN_RATE_LIMIT"), 429
        attempts[peer].append(now)
        valid_password = check_password_hash(digest, raw["password"])
        if raw["username"] != "preview-admin" or not valid_password:
            return jsonify(ok=False, code="INVALID_LOGIN"), 401
        session.clear()
        session.update(fixture_admin=True, hs2_verified_admin=True,
                       hs2_admin_login_at=time.time(), fixture_csrf=secrets.token_urlsafe(32))
        return jsonify(ok=True, management_scope="owned_preview_only")

    @app.post("/hs2/admin/logout")
    def logout():
        if not authorized():
            return jsonify(ok=False, code="ADMIN_REQUIRED"), 403
        expected = session.get("fixture_csrf", "")
        provided = request.headers.get("X-HS2-CSRF", "")
        if not expected or not provided.isascii() or not secrets.compare_digest(expected, provided):
            return jsonify(ok=False, code="CSRF_REQUIRED"), 403
        session.pop("fixture_admin", None)
        session.pop("hs2_verified_admin", None)
        session.pop("hs2_admin_login_at", None)
        return jsonify(ok=True)
