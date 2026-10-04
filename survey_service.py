"""DB-backed survey pricing, immutable receipts, administrator-only PII and expiry."""
import hashlib
import json
import re
import threading
import time
import uuid
from copy import deepcopy
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from flask import jsonify, request, session
from psycopg2.extras import Json
from db import get_conn
from survey_defaults import DEFAULT_SETTINGS

KST = ZoneInfo("Asia/Seoul")
SETTINGS_LOCK = 72941682
TRANSITIONS = {
    "received": ["paid", "canceled"], "paid": ["investigating", "refunded"],
    "investigating": ["reported", "refunded"], "reported": ["refunded"],
    "canceled": ["refunded"], "refunded": [],
}
CHECKS = (
    ("business_report", "영업신고 현황"),
    ("operation_succession", "위탁운영 승계"),
    ("fee_arrears", "관리비 체납"),
)


@contextmanager
def survey_connection():
    """Commit/rollback the transaction and explicitly return the pooled lease."""
    conn = get_conn()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def utcnow():
    return datetime.now(timezone.utc)


def serial(value):
    if isinstance(value, dict):
        return {k: serial(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [serial(v) for v in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def digest(value):
    return hashlib.sha256(json.dumps(serial(value), sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def load_settings(cur):
    cur.execute("SELECT value FROM app_meta WHERE key='survey_settings'")
    row = cur.fetchone()
    stored = json.loads(row["value"]) if row else {}
    result = deepcopy(DEFAULT_SETTINGS)
    result.update(stored)
    return result


def public_config(settings, now=None):
    today = (now or utcnow()).astimezone(KST).date()
    expiry = settings.get("promo_end_date")
    active = bool(settings["promo_enabled"] and settings.get("promo_base_fee") is not None
                  and expiry and date.fromisoformat(expiry) >= today)
    effective = settings["promo_base_fee"] if active else settings["base_fee"]
    return {**settings, "promo_active": active, "effective_base_fee": effective,
            "version": digest({"settings": settings, "effective_base_fee": effective})}


def load_quote(cur, settings):
    """An expired promotion or edited terms invalidates the displayed quote."""
    config = public_config(settings)
    cur.execute("SELECT content FROM legal_documents WHERE doc_type='survey_terms'")
    terms = cur.fetchone()
    config["terms_version"] = digest(terms["content"]) if terms else None
    config["version"] = digest({"pricing_version": config["version"],
                              "terms_version": config["terms_version"]})
    return config, terms


def validate_settings(data):
    if not isinstance(data, dict):
        raise ValueError("설정 형식을 확인해 주세요.")
    result = {}
    for key in ("base_fee", "visit_fee", "report_business_days", "cutoff_days", "payment_hours"):
        value = data.get(key)
        minimum = 0 if key in ("base_fee", "visit_fee", "cutoff_days") else 1
        maximum = 10**9 if key in ("base_fee", "visit_fee") else 3650
        if type(value) is not int or not minimum <= value <= maximum:
            raise ValueError(f"{key}: 비어 있지 않은 {minimum} 이상 정수를 입력해 주세요.")
        result[key] = value
    promo = data.get("promo_base_fee")
    if promo is not None and (type(promo) is not int or not 0 <= promo <= 10**9):
        raise ValueError("프로모션 요금은 0 이상 정수여야 합니다.")
    if type(data.get("promo_enabled")) is not bool:
        raise ValueError("프로모션 사용 여부를 확인해 주세요.")
    expiry = data.get("promo_end_date") or None
    if expiry:
        if not isinstance(expiry, str):
            raise ValueError("프로모션 종료일을 확인해 주세요.")
        try:
            date.fromisoformat(expiry)
        except ValueError:
            raise ValueError("프로모션 종료일을 확인해 주세요.") from None
    if data["promo_enabled"] and (promo is None or not expiry):
        raise ValueError("프로모션 사용 시 요금과 종료일이 필요합니다.")
    result.update(promo_base_fee=promo, promo_enabled=data["promo_enabled"], promo_end_date=expiry)
    for key in ("bank_name", "bank_account", "bank_holder", "provider_name", "business_registration",
                "provider_notice", "service_description", "report_description",
                "refund_policy", "privacy_policy", "vat_label"):
        value = data.get(key)
        if not isinstance(value, str) or not value.strip() or len(value) > 6000 or "\0" in value:
            raise ValueError(f"{key}: 비어 있지 않은 값을 입력해 주세요.")
        result[key] = value.strip()
    descriptions = data.get("checklist_descriptions")
    if not isinstance(descriptions, dict):
        raise ValueError("체크리스트 안내를 입력해 주세요.")
    result["checklist_descriptions"] = {}
    for key, _ in CHECKS:
        value = descriptions.get(key)
        if not isinstance(value, str) or not value.strip() or len(value) > 2000 or "\0" in value:
            raise ValueError("체크리스트 설명은 비워 둘 수 없습니다.")
        result["checklist_descriptions"][key] = value.strip()
    return result


def availability(item, settings, now=None):
    end = item.get("bid_end_at")
    if not end:
        return {"can_apply": False, "reason": "입찰마감일 확인필요", "cutoff_at": None}
    cutoff = end - timedelta(days=settings["cutoff_days"])
    allowed = item["status"] in ("scheduled", "bidding") and (now or utcnow()) < cutoff
    return {"can_apply": allowed, "reason": "" if allowed else "신청 마감",
            "cutoff_at": cutoff.isoformat()}


def analysis_links(item):
    if not item.get("master_building_id"):
        return []
    area, price = item.get("area_m2"), item.get("min_bid_price")
    area_ok = area is not None and 0 < area <= 10000
    # Existing property URL restoration only accepts integer 만원 <=500,000.
    # Never round an auction bid amount to manufacture an accepted value.
    amount = price / 10000 if price is not None and price > 0 else None
    price_ok = amount is not None and amount.is_integer() and 0 < amount <= 500000
    links = []
    for mode, label in (("property", "부동산투자분석"), ("rental", "임대수익분석"), ("operation", "숙박운영분석")):
        params = {"building_id": item["master_building_id"], "mode": mode}
        if area_ok:
            params.update(p_area=area, r_unit_area=area)
        if price_ok and area_ok:
            params["p_purchase"] = int(amount)
            if mode == "rental":
                params["r_purchase"] = int(amount)
            if mode == "operation" and amount >= 100:
                params["buy"] = int(amount)
        links.append({"label": label, "url": "/analysis?" + urlencode(params)})
    return links


def load_item(cur, item_id):
    cur.execute("""SELECT a.id,COALESCE(NULLIF(b.building_name,''),a.title,a.usage_name,'공매 물건') AS title,
      COALESCE(NULLIF(a.address_road,''),a.address_jibun,'') AS address,
      a.min_bid_price,a.area_m2,a.unit_label,a.bid_end_at,a.status,a.master_building_id
      FROM auction_items a LEFT JOIN master_buildings b ON b.id=a.master_building_id WHERE a.id=%s""", [item_id])
    return cur.fetchone()


def validate_applicant(data):
    if not isinstance(data, dict):
        raise ValueError("신청 내용을 확인해 주세요.")
    if any(data.get(key) is not True for key in ("agree_terms", "agree_refund", "agree_privacy")):
        raise ValueError("필수 동의 항목에 모두 동의해 주세요.")
    if data.get("survey_type") not in ("basic", "visit"):
        raise ValueError("조사 유형을 선택해 주세요.")
    cleaned = {"survey_type": data["survey_type"]}
    for key, maximum, required in (("applicant_name", 100, True), ("phone", 40, True),
                                  ("depositor_name", 100, True), ("email", 254, False),
                                  ("memo", 4000, False)):
        value = data.get(key, "")
        if not isinstance(value, str) or len(value) > maximum or "\0" in value or (required and not value.strip()):
            raise ValueError(f"{key}: 입력 내용을 확인해 주세요.")
        cleaned[key] = value.strip()
    cleaned["phone"] = re.sub(r"\D", "", cleaned["phone"])
    if not 8 <= len(cleaned["phone"]) <= 15:
        raise ValueError("연락처를 확인해 주세요.")
    if cleaned["email"] and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", cleaned["email"]):
        raise ValueError("이메일 형식을 확인해 주세요.")
    return cleaned


def receipt(row):
    snapshot = row["settings_snapshot"]
    return serial({**{k: row[k] for k in ("request_no", "base_fee", "visit_fee", "total_fee", "payment_deadline")},
                   **{k: snapshot[k] for k in ("bank_name", "bank_account", "bank_holder")}})


def notify_admin(cur, request_id, request_no):
    """Same transaction as source; existing subscription/outbox respects email opt-in."""
    cur.execute("SELECT current_setting('app.disable_admin_notifications',TRUE) AS disabled")
    if (cur.fetchone() or {}).get("disabled") == "on":
        return
    cur.execute("""INSERT INTO admin_notifications
      (admin_user_id,event_type,source_table,source_id,title,body,deep_link,in_app_enabled)
      SELECT s.admin_user_id,'survey_request','survey_requests',%s,'현황조사 신규 신청',%s,
        '/admin#admin-survey',s.in_app_enabled FROM admin_event_subscriptions s
      WHERE s.event_type='survey_request' AND (s.in_app_enabled OR s.email_enabled)
      ON CONFLICT(admin_user_id,event_type,source_table,source_id) DO NOTHING RETURNING id,admin_user_id""",
                [request_id, request_no])
    for row in cur.fetchall():
        cur.execute("""INSERT INTO admin_notification_email_attempts(notification_id,recipient_email,idempotency_key)
          SELECT %s,a.email,%s FROM admin_users a JOIN admin_event_subscriptions s ON s.admin_user_id=a.id
          WHERE a.id=%s AND s.event_type='survey_request' AND s.email_enabled AND NULLIF(a.email,'') IS NOT NULL
          ON CONFLICT(idempotency_key) DO NOTHING""",
                    [row["id"], "admin-notification-" + str(row["id"]), row["admin_user_id"]])


def cancel_expired(cur, limit=500):
    cur.execute("""WITH due AS (
      SELECT id FROM survey_requests WHERE status='received' AND payment_deadline<=NOW()
      ORDER BY payment_deadline LIMIT %s FOR UPDATE SKIP LOCKED)
      UPDATE survey_requests r SET status='canceled',status_updated_at=NOW()
      FROM due WHERE r.id=due.id RETURNING r.id""", [limit])
    rows = cur.fetchall()
    for row in rows:
        cur.execute("""INSERT INTO survey_request_history(request_id,from_status,to_status,note,changed_by)
          VALUES(%s,'received','canceled','자동취소: 입금 기한 경과','자동취소')""", [row["id"]])
    return len(rows)


_scheduler_started = False


def start_survey_scheduler(logger):
    global _scheduler_started
    if _scheduler_started:
        return
    _scheduler_started = True

    def loop():
        while True:
            try:
                with survey_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SET LOCAL statement_timeout='8s'")
                        cancel_expired(cur)
            except Exception as exc:
                logger.warning("현황조사 자동취소 점검 실패: %s", type(exc).__name__)
            time.sleep(60)
    threading.Thread(target=loop, daemon=True, name="survey-expiry").start()


def register_survey_routes(app, limiter, serve_html, require_admin):
    def actor():
        return "관리자 #" + str(session.get("admin_user_id") or "인증")

    def reject_cross_site():
        return request.headers.get("Sec-Fetch-Site") == "cross-site"

    @app.get("/auctions/<int:item_id>/survey")
    def survey_page(item_id):
        from auction_service import redirect_auction_to_map
        return redirect_auction_to_map(item_id)

    @app.get("/terms/survey")
    def survey_terms_page():
        return serve_html("survey_terms.html")

    @app.get("/api/survey/config")
    @limiter.limit("60 per minute")
    def survey_config():
        with survey_connection() as conn:
            with conn.cursor() as cur:
                config, _ = load_quote(cur, load_settings(cur))
        response = jsonify(ok=True, config=config)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/auctions/<int:item_id>/survey-info")
    @limiter.limit("60 per minute")
    def survey_info(item_id):
        with survey_connection() as conn:
            with conn.cursor() as cur:
                settings = load_settings(cur)
                config, _ = load_quote(cur, settings)
                item = load_item(cur, item_id)
        if not item:
            return jsonify(ok=False, message="공매 물건을 찾을 수 없습니다."), 404
        response = jsonify(ok=True, item=serial(item), config=config,
                           availability=availability(item, settings), analysis_links=analysis_links(item),
                           analysis_notice="확인된 전용면적과 최저입찰가만 전달합니다. 기존 분석 화면의 입력 범위를 벗어나거나 만원 단위로 정확히 표현할 수 없는 금액은 자동 입력하지 않습니다.",
                           comparison=None, checklist=[
                               {"key": key, "label": label, "check_status": "need_check",
                                "description": settings["checklist_descriptions"][key]} for key, label in CHECKS])
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.post("/api/auctions/<int:item_id>/survey-requests")
    @limiter.limit("5 per hour")
    def survey_create(item_id):
        if reject_cross_site():
            return jsonify(ok=False, message="허용되지 않은 요청입니다."), 403
        data = request.get_json(silent=True)
        try:
            cleaned = validate_applicant(data)
            token = data.get("request_token") or uuid.uuid4().hex
            if not isinstance(token, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{16,100}", token):
                raise ValueError("신청 식별값을 확인해 주세요.")
        except ValueError as exc:
            return jsonify(ok=False, message=str(exc)), 400
        token_hash, submission_hash = digest(token), digest({"item_id": item_id, **cleaned})
        with survey_connection() as conn:
            with conn.cursor() as cur:
                # Serialises settings saves, quoting and identical retried submissions.
                cur.execute("SELECT pg_advisory_xact_lock(%s)", [SETTINGS_LOCK])
                cur.execute("SELECT * FROM survey_requests WHERE request_token_hash=%s", [token_hash])
                old = cur.fetchone()
                if old:
                    if old["submission_hash"] != submission_hash:
                        return jsonify(ok=False, message="다른 신청 내용으로 식별값을 재사용할 수 없습니다."), 409
                    return jsonify(ok=True, receipt=receipt(old)), 200
                settings = load_settings(cur)
                config, terms = load_quote(cur, settings)
                if data.get("config_version") and data["config_version"] != config["version"]:
                    return jsonify(ok=False, message="요금·정책 설정이 변경되었습니다. 안내를 확인하고 다시 신청해 주세요."), 409
                item = load_item(cur, item_id)
                if not item:
                    return jsonify(ok=False, message="공매 물건을 찾을 수 없습니다."), 404
                gate = availability(item, settings)
                if not gate["can_apply"]:
                    return jsonify(ok=False, message=gate["reason"]), 409
                now = utcnow()
                base = config["effective_base_fee"]
                visit = config["visit_fee"] if cleaned["survey_type"] == "visit" else 0
                deadline = now + timedelta(hours=config["payment_hours"])
                number = "SV-" + now.astimezone(KST).strftime("%Y%m%d") + "-" + uuid.uuid4().hex[:12].upper()
                if not terms:
                    return jsonify(ok=False, message="서비스 약관을 확인할 수 없습니다. 잠시 후 다시 시도해 주세요."), 503
                cur.execute("""INSERT INTO survey_requests(
                  request_no,auction_item_id,building_id,survey_type,base_fee,visit_fee,total_fee,
                  applicant_name,phone,email,memo,depositor_name,agreed_terms_at,agreed_refund_at,
                  agreed_privacy_at,payment_deadline,settings_snapshot,terms_snapshot,
                  auction_title,auction_address,request_token_hash,submission_hash)
                  VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                  RETURNING *""",
                            [number, item_id, item["master_building_id"], cleaned["survey_type"], base, visit, base + visit,
                             cleaned["applicant_name"], cleaned["phone"], cleaned["email"] or None, cleaned["memo"],
                             cleaned["depositor_name"], now, now, now, deadline, Json(config), terms["content"],
                             item["title"], item["address"], token_hash, submission_hash])
                row = cur.fetchone()
                cur.execute("""INSERT INTO survey_request_history(request_id,to_status,note,changed_by)
                  VALUES(%s,'received','비회원·회원 현황조사 신청 접수','신청자')""", [row["id"]])
                notify_admin(cur, row["id"], number)
        response = jsonify(ok=True, receipt=receipt(row))
        response.headers["Cache-Control"] = "no-store"
        return response, 201

    @app.route("/api/admin/survey/settings", methods=["GET", "PUT"])
    @require_admin
    def survey_settings():
        if request.method == "PUT":
            if reject_cross_site():
                return jsonify(ok=False, message="허용되지 않은 요청입니다."), 403
            try:
                new = validate_settings(request.get_json(silent=True))
            except ValueError as exc:
                return jsonify(ok=False, message=str(exc)), 400
        with survey_connection() as conn:
            with conn.cursor() as cur:
                if request.method == "PUT":
                    cur.execute("SELECT pg_advisory_xact_lock(%s)", [SETTINGS_LOCK])
                    before = load_settings(cur)
                    if before != new:
                        cur.execute("""INSERT INTO survey_settings_history(changed_by,before,after)
                          VALUES(%s,%s,%s)""", [actor(), Json(before), Json(new)])
                        cur.execute("""INSERT INTO app_meta(key,value,updated_at) VALUES('survey_settings',%s,NOW())
                          ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value,updated_at=NOW()""", [Json(new)])
                settings = load_settings(cur)
                cur.execute("SELECT * FROM survey_settings_history ORDER BY id DESC LIMIT 10")
                history = cur.fetchall()
        return jsonify(ok=True, settings=settings, history=serial(history))

    @app.get("/api/admin/survey/requests")
    @require_admin
    def survey_requests():
        status, query = request.args.get("status", ""), request.args.get("q", "").strip()
        if status and status not in TRANSITIONS:
            return jsonify(ok=False, message="신청 상태를 확인해 주세요."), 400
        if len(query) > 200 or "\0" in query:
            return jsonify(ok=False, message="검색어를 확인해 주세요."), 400
        try:
            page = max(1, int(request.args.get("page", "1")))
        except ValueError:
            return jsonify(ok=False, message="페이지를 확인해 주세요."), 400
        conditions, args = [], []
        if status:
            conditions.append("status=%s"); args.append(status)
        if query:
            escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            conditions.append("(request_no ILIKE %s OR applicant_name ILIKE %s OR phone ILIKE %s)")
            args.extend(["%" + escaped + "%"] * 3)
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        with survey_connection() as conn:
            with conn.cursor() as cur:
                cancel_expired(cur)
                cur.execute("SELECT COUNT(*) AS n FROM survey_requests" + where, args)
                total = cur.fetchone()["n"]
                cur.execute("""SELECT id,request_no,created_at,auction_title,applicant_name,phone,email,memo,
                  depositor_name,survey_type,base_fee,visit_fee,total_fee,status,payment_deadline,admin_memo
                  FROM survey_requests""" + where + " ORDER BY created_at DESC,id DESC LIMIT 30 OFFSET %s",
                            args + [(page - 1) * 30])
                items = cur.fetchall()
        response = jsonify(ok=True, items=serial(items), total=total, page=page, page_size=30, transitions=TRANSITIONS)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/admin/survey/requests/<int:request_id>")
    @require_admin
    def survey_request_detail(request_id):
        with survey_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM survey_requests WHERE id=%s", [request_id])
                item = cur.fetchone()
                if not item:
                    return jsonify(ok=False, message="신청을 찾을 수 없습니다."), 404
                cur.execute("SELECT * FROM survey_request_history WHERE request_id=%s ORDER BY id", [request_id])
                history = cur.fetchall()
        response = jsonify(ok=True, item=serial(item), history=serial(history), transitions=TRANSITIONS)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.post("/api/admin/survey/requests/<int:request_id>/status")
    @require_admin
    def survey_status(request_id):
        if reject_cross_site():
            return jsonify(ok=False, message="허용되지 않은 요청입니다."), 403
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            return jsonify(ok=False, message="상태·메모를 확인해 주세요."), 400
        status, note = data.get("status"), data.get("note", "")
        if not isinstance(status, str) or status not in TRANSITIONS or not isinstance(note, str) or len(note) > 4000 or "\0" in note:
            return jsonify(ok=False, message="상태·메모를 확인해 주세요."), 400
        with survey_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM survey_requests WHERE id=%s FOR UPDATE", [request_id])
                row = cur.fetchone()
                if not row:
                    return jsonify(ok=False, message="신청을 찾을 수 없습니다."), 404
                old = row["status"]
                if old == "received" and row["payment_deadline"] <= utcnow():
                    cur.execute("UPDATE survey_requests SET status='canceled',status_updated_at=NOW() WHERE id=%s", [request_id])
                    cur.execute("""INSERT INTO survey_request_history(request_id,from_status,to_status,note,changed_by)
                      VALUES(%s,'received','canceled','자동취소: 입금 기한 경과','자동취소')""", [request_id])
                    return jsonify(ok=False, message="입금 기한이 경과해 자동취소되었습니다."), 409
                if status != old and status not in TRANSITIONS[old]:
                    return jsonify(ok=False, message="허용되지 않은 상태 변경입니다."), 409
                if status == old and not note.strip():
                    return jsonify(ok=False, message="변경 내용 또는 메모를 입력해 주세요."), 400
                cur.execute("""UPDATE survey_requests SET status=%s,status_updated_at=NOW(),admin_memo=%s
                  WHERE id=%s""", [status, note.strip(), request_id])
                cur.execute("""INSERT INTO survey_request_history(request_id,from_status,to_status,note,changed_by)
                  VALUES(%s,%s,%s,%s,%s)""", [request_id, old, status, note.strip(), actor()])
        return jsonify(ok=True)