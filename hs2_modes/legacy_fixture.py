"""Run selected ORIGINAL auth functions against an owned fixture PostgreSQL.

This is test infrastructure, not an application adapter or an alternative login.
Never imports app.py, boots its jobs, uses a DSN, or reads live credentials.
"""
import ast
import hashlib
import secrets
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode

from flask import jsonify, redirect, request, session
from psycopg2.extras import RealDictCursor
from werkzeug.security import check_password_hash, generate_password_hash
from hs2_data.repository import require_fixture

NAMES = {"current_user", "_account_context_id", "_get_account_contexts",
         "_begin_account_login", "_unified_role_login", "auth_logout",
         "_record_login_history", "_kakao_redirect_uri", "kakao_start", "kakao_callback"}
CONSTANTS = {"_ACCOUNT_CONTEXT_REDIRECTS", "_ACCOUNT_PARTNER_TABLES"}


def seed_accounts(conn):
    require_fixture(conn)
    password_hash = generate_password_hash("Synthetic-only-123!", method="pbkdf2:sha256:1000")
    with conn.cursor() as c:
        c.execute("""CREATE SCHEMA hs2_fixture_auth;
          SET search_path TO hs2_fixture_auth;
          CREATE TABLE users(id bigserial PRIMARY KEY,email text UNIQUE,password_hash text,
            name text,provider text,kakao_id text UNIQUE,status text NOT NULL DEFAULT 'active',
            last_login_at timestamptz,phone text,phone_verified boolean DEFAULT false,
            email_alert_enabled boolean DEFAULT false,weekly_email_enabled boolean DEFAULT false);
          CREATE TABLE account_role_memberships(user_id bigint,role text,status text,legacy_account_id bigint);
          CREATE TABLE account_business_memberships(user_id bigint,role text,business_table text,
            business_id bigint,status text);
          CREATE TABLE agents(id bigint PRIMARY KEY,email text,password_hash text,status text,
            office_name text,owner_name text,phone text,weekly_email_enabled boolean DEFAULT false);
          CREATE TABLE operators(id bigint PRIMARY KEY,email text,password_hash text,status text,
            company_name text,owner_name text,phone text,weekly_email_enabled boolean DEFAULT false);
          CREATE TABLE loan_consultants(id bigint PRIMARY KEY,email text,password_hash text,status text,
            office_name text,name text,phone text,weekly_email_enabled boolean DEFAULT false);
          CREATE TABLE operator_lodging(id bigint PRIMARY KEY,email text,status text,biz_name text);
          CREATE TABLE login_history(id bigserial PRIMARY KEY,user_id bigint,ip_hash text,user_agent text);
          INSERT INTO users(id,email,name,provider) VALUES
            (101,'business@example.test','원래 이메일 회원','email'),
            (102,NULL,'원래 카카오 회원','kakao');
          UPDATE users SET kakao_id='fixture-kakao-id' WHERE id=102;
          INSERT INTO users(id,email,name,provider,kakao_id,status)
            VALUES(103,NULL,'탈퇴 회원','kakao','fixture-withdrawn','withdrawn');
          SELECT setval('users_id_seq',1000,true);
          INSERT INTO operators VALUES(21,'legacy@example.test',NULL,'approved','원래 사업장 A','검증',NULL,false),
            (22,'legacy@example.test',NULL,'approved','원래 사업장 B','검증',NULL,false),
            (23,'pending@example.test',NULL,'pending','미승인 사업장','검증',NULL,false);
          INSERT INTO account_role_memberships VALUES(101,'general','active',NULL),(101,'operator','active',21);
          INSERT INTO account_business_memberships VALUES
            (101,'operator','operators',21,'active'),(101,'operator','operators',22,'active');
        """)
        c.execute("UPDATE users SET password_hash=%s WHERE id=101", (password_hash,))
    conn.commit()


class SyntheticKakao:
    """Only fixed fake provider responses; no HTTP client or credentials."""
    subject = "fixture-kakao-id"
    email = "business@example.test"
    broken = False

    def post(self, url, **kwargs):
        if self.broken or url != "fixture:token":
            raise RuntimeError("synthetic provider failure")
        return SimpleNamespace(raise_for_status=lambda: None,
                               json=lambda: {"access_token": "synthetic-only"})

    def get(self, url, **kwargs):
        if self.broken or url != "fixture:profile":
            raise RuntimeError("synthetic provider failure")
        return SimpleNamespace(raise_for_status=lambda: None,
            json=lambda: {"id": self.subject, "kakao_account": {
                "email": self.email, "profile": {"nickname": "검증 카카오"}}})


def source_auth(conn):
    require_fixture(conn)

    class Lease:
        def cursor(self):
            return conn.cursor(cursor_factory=RealDictCursor)
        def close(self):
            pass  # fixture parent, not an application pool, owns this connection
        def commit(self):
            conn.commit()
        def rollback(self):
            conn.rollback()

    provider = SyntheticKakao()
    scope = dict(session=session, request=request, jsonify=jsonify, redirect=redirect,
                 check_password_hash=check_password_hash, get_conn=lambda: Lease(),
                 hashlib=hashlib, get_client_ip=lambda: "synthetic-fixture",
                 _PAGE_VIEW_SALT="synthetic-only", _secrets=secrets, urlencode=urlencode,
                 os=SimpleNamespace(environ={"KAKAO_REST_API_KEY": "synthetic-only"}),
                 requests=provider, _KAKAO_AUTHORIZE_URL="/fixture-kakao",
                 _KAKAO_TOKEN_URL="fixture:token", _KAKAO_USERME_URL="fixture:profile")
    tree = ast.parse((Path(__file__).resolve().parents[1] / "app.py").read_text())
    nodes = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in NAMES:
            node.decorator_list = []
            nodes.append(node)
        elif isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id in CONSTANTS for t in node.targets):
            nodes.append(node)
    if {n.name for n in nodes if isinstance(n, ast.FunctionDef)} != NAMES:
        raise RuntimeError("Required original auth functions missing")
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "original-app-auth", "exec"), scope)
    return scope, provider
