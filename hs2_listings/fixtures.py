"""Owned PostgreSQL browser data; no credential/env-DSN/live account fallback."""
import base64
import hmac
from flask import Flask, jsonify, request, session
from hs2_data.repository import connect_fixture, migrate as migrate_base
from .repository import Repository, migrate
from .api import create_blueprint
from .review import public_rows
from .references import ReferenceAdapter

CANDIDATE = "00000000-0000-4000-8000-000000006001"
WORKFLOW = "00000000-0000-4000-8000-000000006002"
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII=")


def seed():
    with connect_fixture() as conn, conn.cursor() as c:
        c.execute("""CREATE SCHEMA hs2_fixture_legacy;
            CREATE TABLE hs2_fixture_legacy.master_buildings(id bigint PRIMARY KEY,identity_key text);
            CREATE TABLE hs2_fixture_legacy.users(id bigint PRIMARY KEY,active boolean);
            INSERT INTO hs2_fixture_legacy.users VALUES(101,true),(102,true);
            CREATE ROLE hs2_fixture_writer NOLOGIN;
            CREATE ROLE hs2_fixture_public NOLOGIN;""")
        migrate_base(conn)
        migrate(conn)
        c.execute("""INSERT INTO hs2_dev.candidates
            (id,identity_key,identity_confirmed,building_use,road_address,evidence_version)
            VALUES(%s,'fixture:phase6:warehouse',true,'창고','PRIVATE_FIXTURE_ADDRESS','fixture-confirmed:v1')""", (CANDIDATE,))


def create_fixture_app(initialize=True):
    if initialize:
        seed()
    app = Flask("hs2_listing_owned_pg")
    app.secret_key = "synthetic-fixture-only-session"
    app.config.update(MAX_CONTENT_LENGTH=600000, SESSION_COOKIE_HTTPONLY=True,
                      SESSION_COOKIE_SAMESITE="Lax")
    approved = {(101, "operator:fixture:101"), (102, "operator:fixture:102"),
                (101, "operator:fixture:other")}
    repo = Repository(connect_fixture, lambda uid, ctx: (uid, ctx) in approved)
    from hs2_registration.fixtures import fixture_service
    from hs2_registration.providers import ReadPorts
    from hs2_registration.service import RegistrationService
    from hs2_registration.store import PostgresReferenceStore
    from hs2_registration.api import create_blueprint as reference_blueprint

    class OwnedReferenceStore:
        def save(self, building, coordinates, master):
            with connect_fixture() as conn:
                return PostgresReferenceStore(conn).save(building, coordinates, master)

        def legacy(self, identity):
            with connect_fixture() as conn:
                return PostgresReferenceStore(conn).legacy(identity)

    ports = fixture_service().ports
    store = OwnedReferenceStore()
    reference_service = RegistrationService(ReadPorts(ports.addresses, ports.buildings, ports.coordinates, store.legacy), store)
    reference_adapter = ReferenceAdapter(reference_service)

    @app.before_request
    def synthetic_session():
        session.setdefault("fixture_user", 101)
        session.setdefault("fixture_context", "operator:fixture:101")
        session.setdefault("fixture_csrf", "synthetic-csrf-only")

    def context():
        return dict(user_id=session["fixture_user"], context_id=session["fixture_context"],
                    role="operator", business_name="격리 검증 사업장")

    def verify(who, workflow):
        if who["user_id"] == 101 and workflow == WORKFLOW:
            return dict(status="REFERENCE_CONFIRMED", reference_id=CANDIDATE)
        return reference_adapter.verify(who, workflow)

    csrf = lambda: hmac.compare_digest(request.headers.get("X-HS2-CSRF", ""), session["fixture_csrf"])
    app.register_blueprint(create_blueprint(repo, resolve_context=context,
        resolve_admin=lambda: 700 if session.get("fixture_admin") else None,
        csrf_token=lambda: session["fixture_csrf"],
        check_csrf=csrf,
        references=lambda who: ([dict(workflow_id=WORKFLOW, label="확인된 검증 건물", building_use="창고")] if who["user_id"] == 101 else []) + reference_adapter.list(who),
        verify_reference=verify))
    # Phase 3's actual UI reads its existing dev-only CSRF cookie.
    app.register_blueprint(reference_blueprint(reference_service,
        resolve_actor=lambda: context()["user_id"],
        check_csrf=lambda: request.headers.get("X-HS2-CSRF") == session["fixture_csrf"] or
                              request.headers.get("X-HS2-CSRF") == "synthetic-csrf"))

    @app.after_request
    def reference_cookie(response):
        response.set_cookie("hs2_fixture_csrf", "synthetic-csrf", samesite="Lax")
        return response

    @app.post("/hs2/listings-fixture/identity")
    def identity():
        body = request.get_json()
        if not isinstance(body, dict) or set(body) - {"user", "admin", "context"}:
            return jsonify(ok=False), 400
        if body.get("user", 101) not in {101, 102}:
            return jsonify(ok=False), 400
        session["fixture_user"] = body.get("user", 101)
        session["fixture_context"] = body.get("context", f"operator:fixture:{session['fixture_user']}")
        session["fixture_admin"] = body.get("admin") is True
        return jsonify(ok=True)

    @app.get("/hs2/listings-fixture/public")
    def public():
        return jsonify(ok=True, items=public_rows(repo))

    app.fixture_repo = repo
    app.fixture_approved = approved
    app.fixture_reference_service = reference_service
    return app
