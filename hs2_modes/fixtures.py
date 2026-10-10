"""Synthetic account callbacks for browser/unit checks only; never live users."""
from flask import Flask, jsonify, session, request
from flask_limiter import Limiter
from werkzeug.security import check_password_hash, generate_password_hash
from .api import create_blueprint

FIXTURE_EMAIL = "business@example.test"
FIXTURE_PASSWORD = "Synthetic-only-123!"


def create_fixture_app():
    app = Flask("hs2_mode_private_fixture")
    app.secret_key = "hs2-synthetic-browser-only"
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                      MAX_CONTENT_LENGTH=8192)
    limiter = Limiter(key_func=lambda: request.remote_addr or "fixture",
                      app=app, storage_uri="memory://")
    accounts = {101: {"id": 101, "name": "검증 회원", "status": "active"},
                102: {"id": 102, "name": "다른 회원", "status": "active"}}
    contexts = {
        101: [{"id": "operator:operators:21", "role": "operator",
               "business_id": 21, "business_table": "operators", "business_name": "검증 사업장 A"},
              {"id": "lodging_operator:operator_lodging:22", "role": "lodging_operator",
               "business_id": 22, "business_table": "operator_lodging", "business_name": "검증 사업장 B"}],
        102: []
    }
    password_hash = generate_password_hash(FIXTURE_PASSWORD, method="pbkdf2:sha256:1000")

    def user():
        value = accounts.get(session.get("user_id"))
        return value if value and value["status"] == "active" else None

    def email_login(data):
        if data["email"].strip().lower() != FIXTURE_EMAIL or not check_password_hash(password_hash, data["password"]):
            return jsonify(ok=False), 401
        session["user_id"] = 101
        return jsonify(ok=True), 200

    def logout():
        for key in ("user_id", "active_role", "active_business_id", "active_business_table",
                    "agent_id", "operator_id", "loan_consultant_id", "kakao_oauth_state"):
            session.pop(key, None)

    app.register_blueprint(create_blueprint(current_user=user,
        get_contexts=lambda uid: contexts[uid], email_login=email_login,
        member_logout=logout, limit=limiter.limit))
    app.fixture_accounts, app.fixture_contexts = accounts, contexts
    app.fixture_limiter = limiter
    return app
