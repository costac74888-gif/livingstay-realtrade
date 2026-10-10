"""Reuse trusted existing authentication callbacks, not a second user store."""
import secrets
import time
from pathlib import Path

from flask import Blueprint, jsonify, request, send_from_directory, session

WEB = Path(__file__).parent / "web"
OPERATOR_ROLES = {"agent", "operator", "lodging_operator"}
PREFIX = "hs2_mode_"
EMAIL_ENTRY_SECONDS = 600


def create_blueprint(*, current_user, get_contexts, email_login, member_logout,
                     limit, clock=time.time):
    """Host supplies its existing account/membership functions and rate limiter.

    No DB/credential/provider defaults; not mounted by importing this module.
    Operator mode is presentation context, not a new registration/booking grant.
    Membership and email proof are revalidated on every protected request.
    """
    bp = Blueprint("hs2_account_modes", __name__)

    def reset():
        for key in list(session):
            if key.startswith(PREFIX):
                session.pop(key, None)

    def rotate():
        session[PREFIX + "csrf"] = secrets.token_urlsafe(32)

    def state():
        user = current_user()
        uid = user["id"] if user else None
        if session.get(PREFIX + "actor") != uid:
            reset()
        session[PREFIX + "actor"] = uid
        if PREFIX + "csrf" not in session:
            rotate()
        contexts = []
        if user:
            contexts = [c for c in get_contexts(uid)
                        if c.get("role") in OPERATOR_ROLES
                        and c.get("business_id") is not None
                        and c.get("business_table") in {"agents", "operators", "operator_lodging"}]
        proof = session.get(PREFIX + "email_actor") == uid and uid is not None
        try:
            age = clock() - float(session.get(PREFIX + "email_at", 0))
            proof = proof and 0 <= age < EMAIL_ENTRY_SECONDS
        except (ValueError, TypeError):
            proof = False
        selected = session.get(PREFIX + "context")
        if not proof or not any(c["id"] == selected for c in contexts):
            session[PREFIX + "mode"] = "consumer"
            session.pop(PREFIX + "context", None)
        return user, contexts, bool(proof)

    def csrf():
        token = request.headers.get("X-HS2-CSRF", "")
        expected = session.get(PREFIX + "csrf", "")
        # Do not initialize/rotate first: an account change invalidates old tokens.
        bound = session.get(PREFIX + "actor")
        user = current_user()
        uid = user["id"] if user else None
        return (bound == uid and bool(expected) and isinstance(token, str)
                and len(token) <= 128 and secrets.compare_digest(expected, token))

    def fail(code, message, status):
        return jsonify(ok=False, code=code, message=message), status

    def body(fields):
        value = request.get_json(silent=True)
        if not isinstance(value, dict) or set(value) - fields:
            return None
        return value

    @bp.after_request
    def private_response(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        return response

    @bp.get("/hs2/mode")
    def mode_page():
        return send_from_directory(WEB, "mode.html")

    @bp.get("/hs2/mode-assets/<path:name>")
    def mode_assets(name):
        if name not in {"mode.css", "mode.js"}:
            return fail("NOT_FOUND", "파일이 없습니다.", 404)
        return send_from_directory(WEB, name)

    @bp.get("/hs2/api/mode")
    def mode_status():
        try:
            user, contexts, proof = state()
        except Exception:
            return fail("ACCOUNT_UNAVAILABLE", "계정 상태를 확인하지 못했습니다.", 503)
        return jsonify(ok=True, logged_in=bool(user), name=user.get("name") if user else None,
                       mode=session.get(PREFIX + "mode", "consumer"),
                       context_id=session.get(PREFIX + "context"),
                       contexts=[{k: c.get(k) for k in ("id", "role", "business_name")}
                                 for c in contexts],
                       csrf_token=session[PREFIX + "csrf"], email_entry=True,
                       email_authenticated=proof)

    @bp.post("/hs2/api/email-login")
    @limit("5 per minute; 20 per hour")
    def mode_email_login():
        if not csrf():
            return fail("CSRF_REQUIRED", "화면을 새로 열고 다시 시도해주세요.", 403)
        data = body({"email", "password"})
        if (data is None or not isinstance(data.get("email"), str)
                or not 1 <= len(data["email"]) <= 254
                or not isinstance(data.get("password"), str)
                or not 1 <= len(data["password"]) <= 1024):
            return fail("INVALID_CREDENTIALS", "이메일 또는 비밀번호가 올바르지 않습니다.", 400)
        # Reauthentication attempts must not retain earlier operator proof.
        session.pop(PREFIX + "email_actor", None)
        session.pop(PREFIX + "email_at", None)
        session.pop(PREFIX + "context", None)
        session[PREFIX + "mode"] = "consumer"
        try:
            response, status = email_login(data)
            if status != 200 or not response.get_json().get("ok"):
                return fail("LOGIN_FAILED", "로그인 정보 또는 승인된 사업장을 확인해주세요.",
                            401 if status == 401 else 403 if status == 403 else 503)
            user = current_user()
            if not user:
                reset()
                return fail("LOGIN_FAILED", "로그인 상태를 확인하지 못했습니다.", 503)
            reset()
            session[PREFIX + "actor"] = user["id"]
            session[PREFIX + "email_actor"] = user["id"]
            session[PREFIX + "email_at"] = clock()
            rotate()
            _, contexts, _ = state()
            if not contexts:
                reset()
                return fail("APPROVED_BUSINESS_REQUIRED", "승인된 사업장 권한이 필요합니다.", 403)
        except Exception:
            reset()
            return fail("LOGIN_UNAVAILABLE", "로그인을 처리하지 못했습니다. 다시 시도해주세요.", 503)
        return jsonify(ok=True)

    @bp.post("/hs2/api/mode")
    @limit("20 per minute")
    def mode_switch():
        if not csrf():
            return fail("CSRF_REQUIRED", "화면을 새로 열고 다시 시도해주세요.", 403)
        data = body({"mode", "context_id"})
        if data is None or data.get("mode") not in {"consumer", "operator"}:
            return fail("INVALID_MODE", "이용 모드를 확인해주세요.", 400)
        try:
            user, contexts, proof = state()
        except Exception:
            return fail("ACCOUNT_UNAVAILABLE", "계정 상태를 확인하지 못했습니다.", 503)
        if data["mode"] == "operator":
            if not user:
                return fail("LOGIN_REQUIRED", "로그인이 필요합니다.", 401)
            if not proof:
                return fail("EMAIL_LOGIN_REQUIRED", "사업자 이메일 로그인이 필요합니다.", 403)
            cid = data.get("context_id")
            if not isinstance(cid, str) or not any(c["id"] == cid for c in contexts):
                return fail("APPROVED_BUSINESS_REQUIRED", "본인의 승인된 사업장을 선택해주세요.", 403)
            session[PREFIX + "context"] = cid
        else:
            if data.get("context_id") is not None:
                return fail("INVALID_CONTEXT", "이용자 모드에는 사업장을 지정할 수 없습니다.", 400)
            session.pop(PREFIX + "context", None)
        session[PREFIX + "mode"] = data["mode"]
        rotate()
        return jsonify(ok=True)

    @bp.post("/hs2/api/logout")
    @limit("20 per minute")
    def mode_logout():
        if not csrf():
            return fail("CSRF_REQUIRED", "화면을 새로 열고 다시 시도해주세요.", 403)
        member_logout()
        reset()
        rotate()
        return jsonify(ok=True)

    @bp.get("/hs2/api/operator-context")
    def operator_context():
        try:
            user, contexts, proof = state()
        except Exception:
            return fail("ACCOUNT_UNAVAILABLE", "사업장 권한을 확인하지 못했습니다.", 503)
        if not user:
            return fail("LOGIN_REQUIRED", "로그인이 필요합니다.", 401)
        if not proof or session.get(PREFIX + "mode") != "operator":
            return fail("OPERATOR_MODE_REQUIRED", "사업자 로그인이 필요합니다.", 403)
        selected = session.get(PREFIX + "context")
        context = next((c for c in contexts if c["id"] == selected), None)
        if context is None:
            return fail("APPROVED_BUSINESS_REQUIRED", "승인된 사업장이 필요합니다.", 403)
        return jsonify(ok=True, context={k: context.get(k)
                                       for k in ("id", "role", "business_name")})

    return bp
