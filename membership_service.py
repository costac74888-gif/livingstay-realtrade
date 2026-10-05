"""Manual membership payments, immutable bank receipts and audited approvals."""
import uuid

from flask import session, request
from psycopg2.extras import Json
from membership_common import (PLAN, membership_connection, active_period, bank_snapshot,
                               reply, fail, mutation_payload, text, token, lock_user, audit)

PAYMENT_FIELDS = """id,request_no,status,amount,depositor_name,bank,created_at,updated_at,admin_note"""
CHECK_FIELDS = """id,request_no,title,address,building_id,auction_id,status,business_report,
                  operation_succession,fee_arrears,report,memo,created_at,updated_at"""


def register_membership_routes(app, limiter, require_admin, current_user):
    from membership_checks import register_check_routes
    register_check_routes(app, limiter, require_admin, current_user)

    @app.after_request
    def protect_membership_cache(response):
        # The very same building URL returns different records for paid users.
        path = request.path
        if path.startswith("/api/membership/") or path.startswith("/api/admin/membership/") or (
            path.startswith("/api/building/") and path.rsplit("/", 1)[-1].isdigit()
        ):
            response.headers["Cache-Control"] = "private, no-store"
            response.vary.add("Cookie")
        return response

    @app.get("/api/membership/me")
    @limiter.limit("60 per minute")
    def member_me():
        user = current_user()
        if not user:
            return reply(ok=True, logged_in=False, plan=PLAN, bank=None, status="inactive",
                         period=None, paid_through=None, remaining=0, payments=[], checks=[])
        with membership_connection() as conn:
            with conn.cursor() as cur:
                period = active_period(cur, user["id"])
                cur.execute(f"SELECT {PAYMENT_FIELDS} FROM membership_payments WHERE user_id=%s ORDER BY id DESC LIMIT 30",
                            [user["id"]])
                payments = cur.fetchall()
                cur.execute(f"SELECT {CHECK_FIELDS} FROM membership_checks WHERE user_id=%s ORDER BY id DESC LIMIT 30",
                            [user["id"]])
                checks = cur.fetchall()
                cur.execute("SELECT MAX(ends_at) AS until FROM membership_periods WHERE user_id=%s AND revoked_at IS NULL",
                            [user["id"]])
                until = cur.fetchone()["until"]
                remaining = 0
                if period:
                    cur.execute("SELECT id FROM membership_checks WHERE period_id=%s", [period["id"]])
                    remaining = int(cur.fetchone() is None)
                try:
                    bank = bank_snapshot(cur)
                    bank_error = None
                except ValueError as exc:
                    bank, bank_error = None, str(exc)
        return reply(ok=True, logged_in=True, plan=PLAN, bank=bank, bank_error=bank_error,
                     status="active" if period else "inactive", period=period,
                     paid_through=until, remaining=remaining, payments=payments, checks=checks)

    @app.post("/api/membership/payments")
    @limiter.limit("8 per hour")
    def apply_payment():
        user = current_user()
        if not user:
            return fail("로그인 후 신청해 주세요.", 401)
        try:
            data = mutation_payload()
            name, request_token = text(data, "depositor_name", 100, True), token(data)
            if data.get("agree_terms") is not True:
                raise ValueError("이용 조건을 확인하고 동의해 주세요.")
            with membership_connection() as conn:
                with conn.cursor() as cur:
                    lock_user(cur, user["id"])
                    cur.execute(f"SELECT {PAYMENT_FIELDS} FROM membership_payments WHERE user_id=%s AND request_token=%s",
                                [user["id"], request_token])
                    existing = cur.fetchone()
                    if existing:
                        if existing["depositor_name"] != name:
                            return fail("같은 식별값으로 다른 신청을 제출할 수 없습니다.", 409)
                        return reply(ok=True, payment=existing)
                    cur.execute(f"SELECT {PAYMENT_FIELDS} FROM membership_payments WHERE user_id=%s AND status='pending'",
                                [user["id"]])
                    pending = cur.fetchone()
                    if pending:
                        return reply(ok=True, payment=pending)
                    bank = bank_snapshot(cur)
                    cur.execute(f"""INSERT INTO membership_payments(user_id,request_no,request_token,depositor_name,bank)
                      VALUES(%s,%s,%s,%s,%s) RETURNING {PAYMENT_FIELDS}""",
                                [user["id"], "MB-" + uuid.uuid4().hex[:16].upper(), request_token, name, Json(bank)])
                    payment = cur.fetchone()
                    audit(cur, "pending", "회원 #" + str(user["id"]), payment_id=payment["id"],
                          note="월 29,000원 계좌입금·월 1개 물건·자료/전화 확인·미사용 이월 없음 동의")
            return reply(201, ok=True, payment=payment)
        except PermissionError as exc:
            return fail(str(exc), 403)
        except ValueError as exc:
            return fail(str(exc))

    @app.post("/api/membership/payments/<int:payment_id>/cancel")
    @limiter.limit("20 per hour")
    def cancel_payment(payment_id):
        user = current_user()
        if not user:
            return fail("로그인 후 이용해 주세요.", 401)
        try:
            mutation_payload()
        except (PermissionError, ValueError) as exc:
            return fail(str(exc), 403 if isinstance(exc, PermissionError) else 400)
        with membership_connection() as conn:
            with conn.cursor() as cur:
                lock_user(cur, user["id"])
                cur.execute("SELECT * FROM membership_payments WHERE id=%s AND user_id=%s FOR UPDATE",
                            [payment_id, user["id"]])
                payment = cur.fetchone()
                if not payment:
                    return fail("신청을 찾을 수 없습니다.", 404)
                if payment["status"] == "canceled":
                    return reply(ok=True)
                if payment["status"] != "pending":
                    return fail("입금 확인된 신청은 직접 취소할 수 없습니다. 관리자에게 문의해 주세요.", 409)
                cur.execute("UPDATE membership_payments SET status='canceled',updated_at=NOW() WHERE id=%s", [payment_id])
                audit(cur, "canceled", "회원 #" + str(user["id"]), payment_id=payment_id)
        return reply(ok=True)

    @app.get("/api/admin/membership/requests")
    @require_admin
    def admin_requests():
        status = request.args.get("status", "")
        check_status = request.args.get("check_status", "")
        if status and status not in ("pending", "approved", "rejected", "canceled", "revoked"):
            return fail("상태를 확인해 주세요.")
        if check_status and check_status not in ("received", "investigating", "reported"):
            return fail("확인 진행 상태를 확인해 주세요.")
        try:
            page = max(1, min(10000, int(request.args.get("page", "1"))))
            check_page = max(1, min(10000, int(request.args.get("check_page", "1"))))
        except ValueError:
            return fail("페이지를 확인해 주세요.")
        condition, args = ("WHERE p.status=%s", [status]) if status else ("", [])
        with membership_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS n FROM membership_payments p " + condition, args)
                total = cur.fetchone()["n"]
                cur.execute("""SELECT p.*,u.name AS member_name,u.email FROM membership_payments p
                  JOIN users u ON u.id=p.user_id """ + condition + " ORDER BY p.id DESC LIMIT 30 OFFSET %s",
                            args + [(page - 1) * 30])
                payments = cur.fetchall()
                check_condition = " WHERE c.status=%s" if check_status else ""
                check_args = [check_status] if check_status else []
                cur.execute("SELECT COUNT(*) AS n FROM membership_checks c" + check_condition, check_args)
                checks_total = cur.fetchone()["n"]
                cur.execute("""SELECT c.*,u.name AS member_name,u.email FROM membership_checks c
                  JOIN users u ON u.id=c.user_id""" + check_condition +
                            " ORDER BY c.id DESC LIMIT 30 OFFSET %s", check_args + [(check_page - 1) * 30])
                checks = cur.fetchall()
        return reply(ok=True, payments=payments, total=total, page=page, page_size=30, checks=checks,
                     checks_total=checks_total, checks_page=check_page, checks_page_size=30)

    @app.post("/api/admin/membership/payments/<int:payment_id>/status")
    @require_admin
    def approve_payment(payment_id):
        try:
            data = mutation_payload()
            status, note = data.get("status"), text(data, "note", 2000)
            if status not in ("approved", "rejected", "revoked"):
                raise ValueError("처리 상태를 확인해 주세요.")
            if status in ("rejected", "revoked") and not note:
                raise ValueError("처리 사유를 입력해 주세요.")
        except (PermissionError, ValueError) as exc:
            return fail(str(exc), 403 if isinstance(exc, PermissionError) else 400)
        with membership_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT user_id FROM membership_payments WHERE id=%s", [payment_id])
                owner = cur.fetchone()
                if not owner:
                    return fail("신청을 찾을 수 없습니다.", 404)
                lock_user(cur, owner["user_id"])
                cur.execute("""SELECT p.*,u.status AS user_status FROM membership_payments p
                  JOIN users u ON u.id=p.user_id WHERE p.id=%s FOR UPDATE OF p""", [payment_id])
                payment = cur.fetchone()
                if payment["status"] == status:
                    return reply(ok=True)
                allowed = {"pending": ("approved", "rejected"), "approved": ("revoked",)}
                if status not in allowed.get(payment["status"], ()):
                    return fail("이미 처리되었거나 취소된 신청입니다.", 409)
                if status == "approved":
                    if payment["user_status"] == "withdrawn":
                        return fail("탈퇴한 계정은 활성화할 수 없습니다.", 409)
                    cur.execute("""INSERT INTO membership_periods(user_id,payment_id,starts_at,ends_at)
                      SELECT %s,%s,s,
                        ((s AT TIME ZONE 'Asia/Seoul')+INTERVAL '1 month') AT TIME ZONE 'Asia/Seoul'
                      FROM (
                        SELECT GREATEST(NOW(),COALESCE(MAX(ends_at),NOW())) AS s
                        FROM membership_periods WHERE user_id=%s AND revoked_at IS NULL
                      ) x""", [payment["user_id"], payment_id, payment["user_id"]])
                elif status == "revoked":
                    cur.execute("UPDATE membership_periods SET revoked_at=NOW() WHERE payment_id=%s", [payment_id])
                cur.execute("""UPDATE membership_payments SET status=%s,admin_note=%s,
                  approved_by=%s,updated_at=NOW() WHERE id=%s""",
                            [status, note, session.get("admin_user_id"), payment_id])
                audit(cur, status, "관리자 #" + str(session.get("admin_user_id") or "인증"),
                      payment_id=payment_id, note=note)
        return reply(ok=True)