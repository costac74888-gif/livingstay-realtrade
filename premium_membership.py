"""Paid access is backed by an administrator-verified bank payment, never a role."""
from flask import has_request_context, session
from membership_common import active_period, membership_connection, reply


def membership_access(feature, cur=None):
    access = {"required": True, "available": False, "status": "inactive",
              "feature": feature, "info_url": "/membership"}
    user_id = session.get("user_id") if has_request_context() else None
    if not user_id:
        return access
    if cur is not None:
        period = active_period(cur, user_id)
    else:
        with membership_connection() as conn:
            with conn.cursor() as cursor:
                period = active_period(cursor, user_id)
    if period:
        access.update(required=False, available=True, status="active", period_id=period["id"],
                      expires_at=period["ends_at"].isoformat())
    return access


def locked_response(feature):
    return reply(403, ok=False, code="MEMBERSHIP_REQUIRED",
                 message="입금 확인 후 활성화된 멤버십이 필요합니다.",
                 membership_access=membership_access(feature))