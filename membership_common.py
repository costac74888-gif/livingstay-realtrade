"""Small, shared transaction and validation helpers for manual membership."""
import json
import re
from contextlib import contextmanager
from datetime import date, datetime
from urllib.parse import urlsplit

from flask import jsonify, request
from db import get_conn

PLAN = {"amount": 29000, "period": 1, "monthly_properties": 1,
        "payment_method": "bank", "onsite": False}
LOCK_NAMESPACE = 290001


@contextmanager
def membership_connection():
    conn = get_conn()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def serial(value):
    if isinstance(value, dict):
        return {key: serial(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [serial(item) for item in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def reply(http_status=200, **payload):
    response = jsonify(serial(payload))
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Vary"] = "Cookie"
    return response, http_status


def fail(message, status=400, code=None):
    return reply(status, ok=False, message=message, **({"code": code} if code else {}))


def mutation_payload():
    origin = request.headers.get("Origin")
    if request.headers.get("Sec-Fetch-Site") == "cross-site" or (
        origin and urlsplit(origin).netloc != request.host
    ):
        raise PermissionError("허용되지 않은 요청입니다.")
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValueError("입력 형식을 확인해 주세요.")
    return data


def text(data, key, maximum, required=False):
    value = data.get(key, "")
    if not isinstance(value, str) or "\0" in value or len(value.strip()) > maximum:
        raise ValueError("입력 내용을 확인해 주세요.")
    value = value.strip()
    if required and not value:
        raise ValueError("필수 항목을 입력해 주세요.")
    return value


def token(data):
    value = data.get("request_token")
    if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{16,100}", value):
        raise ValueError("신청 식별값을 확인해 주세요.")
    return value


def lock_user(cur, user_id):
    cur.execute("SELECT pg_advisory_xact_lock(%s,%s)", [LOCK_NAMESPACE, user_id])


def active_period(cur, user_id):
    cur.execute("""SELECT p.* FROM membership_periods p
      JOIN users u ON u.id=p.user_id AND u.status<>'withdrawn'
      WHERE p.user_id=%s AND p.revoked_at IS NULL AND p.starts_at<=NOW() AND p.ends_at>NOW()
      ORDER BY p.starts_at DESC,p.id DESC LIMIT 1""", [user_id])
    return cur.fetchone()


def bank_snapshot(cur):
    cur.execute("SELECT value FROM app_meta WHERE key='survey_settings'")
    row = cur.fetchone()
    settings = json.loads(row["value"]) if row else {}
    bank = {key: settings.get(key, "") for key in ("bank_name", "bank_account", "bank_holder")}
    if any(not isinstance(value, str) or not value.strip() for value in bank.values()):
        raise ValueError("입금 계좌가 설정되지 않았습니다. 관리자에게 문의해 주세요.")
    return {key: value.strip() for key, value in bank.items()}


def audit(cur, event, actor, payment_id=None, check_id=None, note=""):
    cur.execute("""INSERT INTO membership_history(payment_id,check_id,actor,event,note)
      VALUES(%s,%s,%s,%s,%s)""", [payment_id, check_id, actor, event, note])