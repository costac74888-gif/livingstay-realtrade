"""One immutable property selection per paid month, with a three-part report."""
import uuid
from flask import session
from membership_common import (membership_connection, active_period, reply, fail,
                               mutation_payload, token, text, lock_user, audit)


def submit_check(data, user_id, forced_auction_id=None):
    if data.get("agree_terms") is not True:
        raise ValueError("자료·전화 확인 범위와 결과의 한계를 확인하고 동의해 주세요.")
    request_token, memo = token(data), text(data, "memo", 2000)
    auction_id = forced_auction_id or data.get("auction_id")
    building_id = data.get("building_id")
    # Never permit a visit flag or an alternate priced service to slip through.
    if data.get("survey_type") not in (None, "basic") or data.get("onsite") is True:
        raise ValueError("현장확인은 제공하지 않습니다.")
    if forced_auction_id:
        building_id = None
    if (auction_id is None) == (building_id is None):
        raise ValueError("건물 또는 공매 물건 1건을 선택해 주세요.")
    target_id = auction_id if auction_id is not None else building_id
    if isinstance(target_id, bool) or not isinstance(target_id, int) or target_id <= 0 or target_id > 2147483647:
        raise ValueError("물건 식별값을 확인해 주세요.")
    with membership_connection() as conn:
        with conn.cursor() as cur:
            lock_user(cur, user_id)
            period = active_period(cur, user_id)
            if not period:
                return fail("입금 확인된 유효 멤버십이 필요합니다.", 403, "MEMBERSHIP_REQUIRED")
            cur.execute("SELECT * FROM membership_checks WHERE user_id=%s AND request_token=%s",
                        [user_id, request_token])
            old = cur.fetchone()
            if old:
                if old["memo"] != memo or (auction_id is not None and old["auction_id"] != auction_id) or (
                    auction_id is None and (old["auction_id"] is not None or old["building_id"] != building_id)
                ):
                    return fail("같은 식별값으로 다른 물건·내용을 신청할 수 없습니다.", 409)
                return reply(ok=True, check=old)
            cur.execute("SELECT id FROM membership_checks WHERE period_id=%s", [period["id"]])
            if cur.fetchone():
                return fail("이번 이용기간의 물건 1건을 이미 신청했습니다.", 409, "MONTHLY_LIMIT")
            if auction_id is not None:
                from auction_domain import ELIGIBLE_SQL
                cur.execute(f"""SELECT a.title,COALESCE(NULLIF(a.address_road,''),a.address_jibun,'') AS address,
                  a.master_building_id AS building_id
                  FROM auction_items a WHERE a.id=%s AND {ELIGIBLE_SQL}""", [auction_id])
            else:
                cur.execute("""SELECT COALESCE(building_name,'건물') AS title,
                  COALESCE(road_address,jibun_address,'') AS address,id AS building_id
                  FROM master_buildings WHERE id=%s""", [building_id])
            target = cur.fetchone()
            if not target:
                return fail("선택한 물건을 찾을 수 없습니다.", 404)
            cur.execute("""INSERT INTO membership_checks(
              period_id,user_id,request_no,request_token,building_id,auction_id,title,address,memo)
              VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                        [period["id"], user_id, "MC-" + uuid.uuid4().hex[:16].upper(),
                         request_token, target["building_id"], auction_id, target["title"] or "공매 물건",
                         target["address"] or "", memo])
            check = cur.fetchone()
            audit(cur, "received", "회원 #" + str(user_id), check_id=check["id"],
                  note="동일 물건 영업신고·위탁운영·관리비 각 1회; 자료/전화 확인에 동의")
    return reply(201, ok=True, check=check)


def register_check_routes(app, limiter, require_admin, current_user):
    @app.post("/api/membership/checks")
    @limiter.limit("20 per hour")
    def apply_check():
        user = current_user()
        if not user:
            return fail("로그인 후 신청해 주세요.", 401)
        try:
            return submit_check(mutation_payload(), user["id"])
        except (PermissionError, ValueError) as exc:
            return fail(str(exc), 403 if isinstance(exc, PermissionError) else 400)

    @app.post("/api/admin/membership/checks/<int:check_id>/status")
    @require_admin
    def update_check(check_id):
        try:
            data = mutation_payload()
            status = data.get("status")
            if status not in ("received", "investigating", "reported"):
                raise ValueError("확인 진행 상태를 확인해 주세요.")
            report = text(data, "report", 10000)
            values = [data.get(key, "need_check") for key in
                      ("business_report", "operation_succession", "fee_arrears")]
            if any(value not in ("need_check", "ok", "issue") for value in values):
                raise ValueError("항목별 결과를 확인해 주세요.")
            if status == "reported" and not report:
                raise ValueError("확인 결과 또는 미확인 사유를 입력해 주세요.")
        except (PermissionError, ValueError) as exc:
            return fail(str(exc), 403 if isinstance(exc, PermissionError) else 400)
        with membership_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM membership_checks WHERE id=%s FOR UPDATE", [check_id])
                old = cur.fetchone()
                if not old:
                    return fail("신청을 찾을 수 없습니다.", 404)
                order = {"received": 0, "investigating": 1, "reported": 2}
                if order[status] < order[old["status"]]:
                    return fail("완료된 진행 상태를 이전으로 되돌릴 수 없습니다.", 409)
                cur.execute("""UPDATE membership_checks SET status=%s,business_report=%s,
                  operation_succession=%s,fee_arrears=%s,report=%s,updated_at=NOW() WHERE id=%s""",
                            [status, *values, report, check_id])
                audit(cur, status, "관리자 #" + str(session.get("admin_user_id") or "인증"),
                      check_id=check_id, note=report)
        return reply(ok=True)