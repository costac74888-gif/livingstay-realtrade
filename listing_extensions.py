"""Additive listing contracts: channels are independent of transaction targets."""
import math

from flask import jsonify, request, session
from db import get_conn

SCHEMA_VERSION = "2026-10-10-listing-extension-1"


def ensure_listing_extensions(cur):
    # No master-building DDL, legacy row rewrites, or destructive operations.
    cur.execute("ALTER TABLE listing_requests ADD COLUMN IF NOT EXISTS business_rights_info JSONB DEFAULT '{}'::jsonb")
    cur.execute("ALTER TABLE listing_requests ADD COLUMN IF NOT EXISTS broker_agent_id INTEGER REFERENCES agents(id)")
    cur.execute("ALTER TABLE listing_requests ADD COLUMN IF NOT EXISTS publication_status TEXT")
    cur.execute("ALTER TABLE listing_requests ADD COLUMN IF NOT EXISTS publication_reason TEXT")
    cur.execute("ALTER TABLE listing_requests ADD COLUMN IF NOT EXISTS publication_verified_at TIMESTAMP")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_listing_broker_publication ON listing_requests(broker_agent_id, publication_status)")


TEXT_LIMITS = {
    "facility_name": 100, "lease_term": 150, "furniture_details": 500,
    "takeover_conditions": 500, "permit_status": 100, "permit_industry": 100,
    "permit_notes": 500,
}
BOOL_FIELDS = {
    "lease_transfer_possible", "furniture_included", "staff_transfer",
    "ota_transfer", "permit_certificate",
}
NUM_LIMITS = {
    "maintenance_fee_krw": 1_000_000, "adr_krw": 1_000_000,
    "revpar_krw": 1_000_000, "occ": 100, "rating": 5,
    "review_count": 100_000_000,
}


def validate_business_info(raw):
    """Allowlisted optional data; preserve real zero and reject malformed input."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("영업권 양도 정보는 항목별 입력값이어야 합니다.")
    result = {}
    for key, limit in TEXT_LIMITS.items():
        value = raw.get(key)
        if value is not None and value != "":
            if not isinstance(value, str) or len(value.strip()) > limit:
                raise ValueError(f"{key} 입력 형식 또는 길이를 확인해주세요.")
            if value.strip():
                result[key] = value.strip()
    for key in BOOL_FIELDS:
        value = raw.get(key)
        if value is not None and value != "":
            if not isinstance(value, bool):
                raise ValueError(f"{key}는 선택값이어야 합니다.")
            result[key] = value
    for key, maximum in NUM_LIMITS.items():
        value = raw.get(key)
        if value is None or value == "":
            continue
        if isinstance(value, bool):
            raise ValueError(f"{key}는 숫자로 입력해주세요.")
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"{key}는 숫자로 입력해주세요.") from None
        if not math.isfinite(number) or not 0 <= number <= maximum:
            raise ValueError(f"{key}의 입력 범위를 확인해주세요.")
        if key == "review_count" and number != int(number):
            raise ValueError("리뷰 수는 정수로 입력해주세요.")
        result[key] = int(number) if key == "review_count" else round(number, 2)
    return result


def broker_context(cur, user):
    """Never identify a business by shared email or trust an arbitrary agent ID."""
    if not user or session.get("active_role") != "agent" or session.get("active_business_table") != "agents":
        return None
    aid = session.get("active_business_id")
    if not aid:
        return None
    cur.execute("""
        SELECT a.id, a.office_name, a.owner_name, a.reg_number,
               a.office_address, a.phone, a.office_phone
          FROM agents a
          JOIN account_business_memberships m
            ON m.business_table='agents' AND m.business_id=a.id
         WHERE a.id=%s AND m.user_id=%s AND m.status='active'
           AND a.status='approved'
    """, [aid, user["id"]])
    row = cur.fetchone()
    return dict(row) if row else None


def public_channel_sql(alias="lr"):
    if alias not in ("lr", "listing_requests"):
        raise ValueError("Unsupported listing alias")
    return f"""(
        COALESCE({alias}.deal_mode,'direct')='direct' OR (
            {alias}.deal_mode='broker' AND {alias}.publication_status='approved'
            AND EXISTS(SELECT 1 FROM agents ba
                       JOIN account_business_memberships bm ON bm.business_table='agents'
                         AND bm.business_id=ba.id AND bm.status='active'
                       JOIN users bu ON bu.id=bm.user_id AND bu.status<>'withdrawn'
                       WHERE ba.id={alias}.broker_agent_id AND ba.status='approved'
                         AND bm.user_id={alias}.user_id)
        ))"""


def business_context_allowed(cur, listing, user_id):
    aid = listing.get("broker_agent_id")
    if not aid:
        return True
    context = broker_context(cur, {"id": user_id})
    return bool(context and context["id"] == aid)


def invalidate_publication(cur, listing_id):
    cur.execute("""
        UPDATE listing_requests SET publication_status='pending',
               publication_verified_at=NULL, publication_reason=NULL, updated_at=NOW()
         WHERE id=%s AND broker_agent_id IS NOT NULL
    """, [listing_id])


def register_listing_extension_routes(app, require_admin, current_user, serve_html):
    @app.get("/api/listings/registration-context")
    def listing_registration_context():
        user = current_user()
        if not user:
            return jsonify(ok=False, message="로그인이 필요합니다."), 401
        conn = get_conn()
        cur = conn.cursor()
        try:
            broker = broker_context(cur, user)
            return jsonify(ok=True, can_publish_broker=bool(broker), broker=broker)
        finally:
            cur.close()
            conn.close()

    @app.get("/admin/broker-listings")
    @require_admin
    def broker_listing_review_page():
        return serve_html("broker_listing_review.html")

    @app.get("/api/admin/broker-listings")
    @require_admin
    def broker_listing_review_queue():
        conn = get_conn()
        cur = conn.cursor()
        try:
            cur.execute("""
                SELECT lr.id, lr.deal_type, lr.transaction_target, lr.price_krw,
                       lr.key_money_krw, lr.monthly_rent_krw, lr.description,
                       lr.room_count, lr.monthly_revenue_krw, lr.annual_revenue_krw,
                       lr.short_stay_ratio, lr.ota_revenue_ratio, lr.operation_status,
                       lr.business_rights_info, lr.publication_status,
                       lr.publication_reason, lr.created_at,
                       COALESCE(lr.updated_at,lr.created_at)::text AS review_version,
                       mb.building_name, mb.road_address,
                       a.office_name, a.owner_name, a.reg_number,
                       a.office_address, a.phone, a.office_phone,
                        u.name AS registered_by,
                        COALESCE((
                            SELECT jsonb_agg('/api/listing-photos/img/' || p.image_key
                                             ORDER BY p.sort_order,p.id)
                              FROM listing_photos p WHERE p.listing_request_id=lr.id
                        ),'[]'::jsonb) AS photos
                  FROM listing_requests lr
                  JOIN agents a ON a.id=lr.broker_agent_id
                  JOIN master_buildings mb ON mb.id=lr.master_building_id
                  JOIN users u ON u.id=lr.user_id
                 WHERE lr.broker_agent_id IS NOT NULL
                   AND COALESCE(lr.status,'') NOT IN ('withdrawn','철회됨')
                 ORDER BY (lr.publication_status='pending') DESC, lr.id DESC
                 LIMIT 200
            """)
            items = []
            for row in cur.fetchall():
                item = dict(row)
                item["broker"] = {
                    key: item.get(key) for key in (
                        "office_name", "owner_name", "reg_number", "office_address",
                        "phone", "office_phone", "registered_by", "created_at",
                    )
                }
                items.append(item)
            return jsonify(ok=True, items=items)
        finally:
            cur.close()
            conn.close()

    @app.post("/api/admin/broker-listings/<int:listing_id>/review")
    @require_admin
    def review_broker_listing(listing_id):
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            return jsonify(ok=False, message="검토 요청 형식이 올바르지 않습니다."), 400
        decision = data.get("decision")
        reason = str(data.get("reason") or "").strip()[:500]
        if decision not in ("approved", "rejected"):
            return jsonify(ok=False, message="승인 또는 반려를 선택해주세요."), 400
        if decision == "rejected" and not reason:
            return jsonify(ok=False, message="반려 사유를 입력해주세요."), 400
        if not isinstance(data.get("review_version"), str):
            return jsonify(ok=False, message="검토 목록을 새로 불러온 후 처리해주세요."), 409
        conn = get_conn()
        cur = conn.cursor()
        try:
            cur.execute("""
                SELECT lr.*, COALESCE(lr.updated_at,lr.created_at)::text AS review_version,
                       a.status AS agent_status, a.office_name, a.owner_name,
                       a.reg_number, a.office_address,
                       COALESCE(NULLIF(a.office_phone,''),a.phone) AS broker_phone,
                       EXISTS(SELECT 1 FROM account_business_memberships m
                              JOIN users u ON u.id=m.user_id AND u.status<>'withdrawn'
                              WHERE m.business_table='agents' AND m.business_id=a.id
                                AND m.user_id=lr.user_id AND m.status='active') AS active_member
                  FROM listing_requests lr JOIN agents a ON a.id=lr.broker_agent_id
                 WHERE lr.id=%s FOR UPDATE OF lr
            """, [listing_id])
            row = cur.fetchone()
            if not row:
                return jsonify(ok=False, message="중개 매물을 찾을 수 없습니다."), 404
            if data["review_version"] != row["review_version"]:
                return jsonify(ok=False, message="매물이 수정되었습니다. 최신 내용을 다시 검토해주세요."), 409
            if row["status"] in ("withdrawn", "철회됨", "보류"):
                return jsonify(ok=False, message="철회·보류 매물은 승인할 수 없습니다."), 409
            if decision == "approved" and (
                row["agent_status"] != "approved" or not row["active_member"]
                or any(not row.get(k) for k in
                       ("office_name", "owner_name", "reg_number", "office_address", "broker_phone"))
            ):
                return jsonify(ok=False, message="중개사 승인·소속·표시광고 필수정보를 먼저 확인해주세요."), 400
            cur.execute("""
                UPDATE listing_requests SET publication_status=%s,
                       publication_reason=%s, publication_verified_at=NOW()
                 WHERE id=%s
            """, [decision, reason or None, listing_id])
            cur.execute("""
                INSERT INTO listing_request_history(listing_request_id, action, after_data)
                VALUES(%s,'publication_review',jsonb_build_object(
                    'decision',%s::text,'reason',%s::text,'admin_id',%s::integer))
            """, [listing_id, decision, reason, session.get("admin_user_id")])
            conn.commit()
            return jsonify(ok=True, publication_status=decision)
        finally:
            cur.close()
            conn.close()
