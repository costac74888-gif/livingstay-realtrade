 listing_requests SET updated_at=NOW() WHERE id=%s", [lr_id])
        conn.commit()
    finally:
        cur.close(); conn.close()
    try:
        storage_util.delete_object(key)
    except Exception:
        app.logger.warning("매물 사진 객체 삭제 실패: %s", key, exc_info=True)
    return jsonify({"ok": True, "id": photo_id})


@app.route("/api/listing-photos/img/<path:key>")
def listing_photo_proxy(key):
    """직거래 매물 사진 프록시 — 공개 상태가 바뀔 수 있어 공유 캐시를 금지한다."""
    if not storage_util.is_valid_listing_photo_ref(key):
        return jsonify({"ok": False, "message": "잘못된 경로입니다."}), 404
    conn = get_conn(); cur = conn.cursor()
    try:
        cur.execute("""
            SELECT COALESCE(lp.is_public, TRUE) AS is_public
            FROM listing_photos lp
            JOIN listing_requests lr ON lr.id = lp.listing_request_id
            WHERE lp.image_key = %s
              AND lr.deal_mode = 'direct'
              AND COALESCE(lr.status, '') NOT IN ('withdrawn', '철회됨', '보류')
              AND (
                    lr.user_id = %s
                    OR (
                        COALESCE(lp.is_public, TRUE)
                        AND NOT (
                            lr.transaction_target = 'whole'
                            AND COALESCE(lr.disclosure_scope, 'limited') = 'limited'
                        )
                    )
              )
        """, [key, (current_user() or {}).get("id", -1)])
        photo = cur.fetchone()
        if not photo:
            return jsonify({"ok": False, "message": "파일을 찾을 수 없습니다."}), 404
        file_data = storage_util.download_bytes(key)
    except Exception:
        return jsonify({"ok": False, "message": "파일을 찾을 수 없습니다."}), 404
    finally:
        cur.close(); conn.close()
    ext = key.rsplit(".", 1)[-1].lower() if "." in key else ""
    ct = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}.get(ext, "image/jpeg")
    from flask import Response as _Response
    resp = _Response(file_data, mimetype=ct)
    # 같은 이미지 URL이 공개에서 비공개로 전환될 수 있다. 공개 응답을 CDN에
    # 보관하면 이후 DB 권한 확인을 우회할 수 있으므로 모든 사진을 공유 캐시하지 않는다.
    resp.headers["Cache-Control"] = "private, no-store"
    return resp


@app.route("/api/listing-requests/<int:lr_id>/like", methods=["POST"])
@limiter.limit("60 per minute")
def toggle_listing_like(lr_id):
    """직거래 매물 찜 토글 — 로그인 필수. liked:true/false + like_count 반환."""
    user = current_user()
    if not user:
        return jsonify({"ok": False, "message": "로그인이 필요합니다."}), 401
    conn = get_conn(); cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id FROM listing_requests WHERE id=%s AND deal_mode='direct' "
            "AND COALESCE(status, '') NOT IN ('withdrawn', '철회됨', '보류')",
            [lr_id]
        )
        if not cur.fetchone():
            return jsonify({"ok": False, "message": "매물을 찾을 수 없습니다."}), 404
        cur.execute(
            "SELECT id FROM listing_likes WHERE listing_request_id=%s AND user_id=%s",
            [lr_id, user["id"]]
        )
        if cur.fetchone():
            cur.execute(
                "DELETE FROM listing_likes WHERE listing_request_id=%s AND user_id=%s",
                [lr_id, user["id"]]
            )
            liked = False
        else:
            cur.execute(
                "INSERT INTO listing_likes (listing_request_id, user_id) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                [lr_id, user["id"]]
            )
            liked = True
        cur.execute("SELECT COUNT(*) AS cnt FROM listing_likes WHERE listing_request_id=%s", [lr_id])
        like_count = int(cur.fetchone()["cnt"])
        conn.commit()
    finally:
        cur.close(); conn.close()
    return jsonify({"ok": True, "liked": liked, "like_count": like_count})


# ── 인앱 채팅 (직거래 매물 문의) ─────────────────────────────────────────

@app.route("/api/chat/rooms", methods=["POST"])
@limiter.limit("20 per hour")
def create_chat_room():
    """직거래 매물 채팅방 생성 또는 기존 방 반환 — 로그인·휴대폰 인증 필요."""
    user = current_user()
    if not user:
        return jsonify({"ok": False, "message": "로그인이 필요합니다."}), 401
    data = request.get_json(force=True, silent=True) or {}
    try:
        lr_id = int(data.get("listing_request_id") or 0)
    except (TypeError, ValueError):
        lr_id = 0
    if not lr_id:
        return jsonify({"ok": False, "message": "매물 ID가 필요합니다."}), 400
    conn = get_conn(); cur = conn.cursor()
    try:
        # 세션에 든 정보가 아니라 현재 DB 인증 상태를 기준으로 확인한다.
        # 이 생성/재개 진입점은 기존 방을 반환하는 경우에도 인증을 요구한다.
        # 방 목록에서 이미 참여 중인 방을 읽고 보내는 API의 정책은 별개다.
        cur.execute("""
            SELECT phone, COALESCE(phone_verified, FALSE) AS phone_verified
              FROM users WHERE id = %s
        """, [user["id"]])
        requester = cur.fetchone()
        if not requester or not requester["phone_verified"] or not requester["phone"]:
            return jsonify({
                "ok": False,
                "code": "PHONE_VERIFICATION_REQUIRED",
                "message": "안전한 직거래를 위해 휴대폰 인증 후 채팅을 시작해주세요.",
            }), 403
        # 매물 존재 확인 + 판매자 ID
        cur.execute("""
            SELECT lr.id, lr.user_id AS seller_user_id
            FROM listing_requests lr
            WHERE lr.id = %s AND lr.deal_mode = 'direct'
              AND COALESCE(lr.status, '') NOT IN ('withdrawn', '철회됨', '보류')
        """, [lr_id])
        lr = cur.fetchone()
        if not lr:
            return jsonify({"ok": False, "message": "공개 직거래 매물을 찾을 수 없습니다."}), 404
        seller_id = lr["seller_user_id"]
        buyer_id = user["id"]
        if seller_id == buyer_id:
            return jsonify({"ok": False, "message": "본인 매물에는 문의할 수 없습니다."}), 400
        # UPSERT — 기존 방 있으면 반환
        cur.execute("""
            INSERT INTO chat_rooms (listing_request_id, buyer_user_id, seller_user_id)
            VALUES (%s, %s, %s)
            ON CONFLICT (listing_request_id, buyer_user_id) DO UPDATE SET listing_request_id = EXCLUDED.listing_request_id
            RETURNING id, created_at
        """, [lr_id, buyer_id, seller_id])
        room = cur.fetchone()
        conn.commit()
        return jsonify({"ok": True, "room_id": room["id"]})
    finally:
        cur.close(); conn.close()


@app.route("/api/chat/rooms/<int:room_id>/messages")
@limiter.limit("120 per minute")
def get_chat_messages(room_id):
    """채팅 메시지 조회 — 채팅방 참여자(buyer/seller)만 접근 가능."""
    user = current_user()
    if not user:
        return jsonify({"ok": False, "message": "로그인이 필요합니다."}), 401
    conn = get_conn(); cur = conn.cursor()
    try:
        cur.execute("""
            SELECT cr.buyer_user_id, cr.seller_user_id,
                   bu.name AS buyer_name, su.name AS seller_name
              FROM chat_rooms cr
              JOIN users bu ON bu.id = cr.buyer_user_id
              JOIN users su ON su.id = cr.seller_user_id
             WHERE cr.id = %s
        """, [room_id])
        room = cur.fetchone()
        if not room:
            return jsonify({"ok": False, "message": "채팅방을 찾을 수 없습니다."}), 404
        if user["id"] not in (room["buyer_user_id"], room["seller_user_id"]):
            return jsonify({"ok": False, "message": "접근 권한이 없습니다."}), 403
        cur.execute("""
            SELECT cm.id, cm.sender_user_id, cm.body,
                   cm.attachment_key, cm.attachment_name,
                   TO_CHAR(cm.created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS sent_at,
                   u.name AS sender_name
            FROM chat_messages cm
            JOIN users u ON u.id = cm.sender_user_id
            WHERE cm.room_id = %s
            ORDER BY cm.created_at ASC
            LIMIT 200
        """, [room_id])
        messages = [dict(r) for r in cur.fetchall()]
        # 상대방이 보낸 안 읽은 메시지를 읽음으로 표시
        cur.execute("""
            UPDATE chat_messages
               SET is_read = TRUE
             WHERE room_id = %s
               AND sender_user_id != %s
               AND is_read = FALSE
        """, [room_id, user["id"]])
        conn.commit()
    finally:
        cur.close(); conn.close()
    opponent_name = (
        room["seller_name"] if user["id"] == room["buyer_user_id"]
        else room["buyer_name"]
    ) or "상대방"
    return jsonify({
        "ok": True,
        "messages": messages,
        "my_user_id": user["id"],
        "my_role": "buyer" if user["id"] == room["buyer_user_id"] else "seller",
        "opponent_name": opponent_name,
    })


@app.route("/api/chat/unread-count")
def chat_unread_count():
    """헤더 벨 배지용 — 현재 사용자에게 온 안 읽은 채팅 메시지 수."""
    u = current_user()
    if not u:
        return jsonify({"ok": False, "message": "로그인이 필요합니다."}), 401
    conn = get_conn(); cur = conn.cursor()
    try:
        cur.execute("""
            SELECT COUNT(*) AS c
              FROM chat_messages cm
              JOIN chat_rooms cr ON cr.id = cm.room_id
             WHERE cm.sender_user_id != %s
               AND cm.is_read = FALSE
               AND (cr.buyer_user_id = %s OR cr.seller_user_id = %s)
        """, [u["id"], u["id"], u["id"]])
        c = cur.fetchone()["c"]
    finally:
        cur.close(); conn.close()
    return jsonify({"ok": True, "count": c})


@app.route("/api/chat/recent-unread")
def chat_recent_unread():
    """헤더 알림 드롭다운용 — 안 읽은 채팅을 채팅방별 최신 1건씩 최대 10개 반환."""
    u = current_user()
    if not u:
        return jsonify({"ok": False, "message": "로그인이 필요합니다."}), 401
    conn = get_conn(); cur = conn.cursor()
    try:
        cur.execute("""
            SELECT cr.id AS room_id,
                   mb.building_name,
                   (SELECT COUNT(*) FROM chat_messages
                    WHERE room_id = cr.id AND sender_user_id != %(uid)s AND is_read = FALSE
                   ) AS unread_count,
                   (SELECT u2.name
                    FROM chat_messages cm2
                    JOIN users u2 ON u2.id = cm2.sender_user_id
                    WHERE cm2.room_id = cr.id AND cm2.sender_user_id != %(uid)s AND cm2.is_read = FALSE
                    ORDER BY cm2.created_at DESC LIMIT 1
                   ) AS sender_name,
                   (SELECT COALESCE(NULLIF(TRIM(cm2.body),''), '(첨부파일)')
                    FROM chat_messages cm2
                    WHERE cm2.room_id = cr.id AND cm2.sender_user_id != %(uid)s AND cm2.is_read = FALSE
                    ORDER BY cm2.created_at DESC LIMIT 1
                   ) AS body,
                   (SELECT TO_CHAR(cm2.created_at, 'YYYY-MM-DD HH24:MI')
                    FROM chat_messages cm2
                    WHERE cm2.room_id = cr.id AND cm2.sender_user_id != %(uid)s AND cm2.is_read = FALSE
                    ORDER BY cm2.created_at DESC LIMIT 1
                   ) AS sent_at,
                   (SELECT cm2.created_at
                    FROM chat_messages cm2
                    WHERE cm2.room_id = cr.id AND cm2.sender_user_id != %(uid)s AND cm2.is_read = FALSE
                    ORDER BY cm2.created_at DESC LIMIT 1
                   ) AS latest_at
            FROM chat_rooms cr
            JOIN listing_requests lr ON lr.id = cr.listing_request_id
            JOIN master_buildings mb ON mb.id = lr.master_building_id
            WHERE (cr.buyer_user_id = %(uid)s OR cr.seller_user_id = %(uid)s)
              AND EXISTS (
                SELECT 1 FROM chat_messages
                WHERE room_id = cr.id AND sender_user_id != %(uid)s AND is_read = FALSE
              )
            ORDER BY latest_at DESC
            LIMIT 10
        """, {"uid": u["id"]})
        items = [dict(r) for r in cur.fetchall()]
        for it in items:
            it.pop("latest_at", None)
            it["unread_count"] = int(it["unread_count"])
    finally:
        cur.close(); conn.close()
    return jsonify({"ok": True, "items": items})


@app.route("/api/chat/rooms", methods=["GET"])
@limiter.limit("60 per minute")
def list_chat_rooms():
    """채팅목록 모달용 — 내가 참여한 모든 채팅방을 최신 메시지순으로 반환.

    미읽음 여부와 무관하게 전체 방을 포함한다(/api/chat/recent-unread와 구별).
    limit/offset 페이징 — limit+1개를 조회해 has_more를 계산한다.
    """
    u = current_user()
    if not u:
        return jsonify({"ok": False, "message": "로그인이 필요합니다."}), 401
    try:
        limit = min(max(int(request.args.get("limit", 20)), 1), 50)
    except (TypeError, ValueError):
        limit = 20
    try:
        offset = max(int(request.args.get("offset", 0)), 0)
    except (TypeError, ValueError):
        offset = 0
    conn = get_conn(); cur = conn.cursor()
    try:
        cur.execute("""
            SELECT cr.id AS room_id,
                   cr.listing_request_id,
                   mb.building_name,
                   CASE WHEN cr.buyer_user_id = %(uid)s THEN su.name ELSE bu.name END
                       AS opponent_name,
                   lm.body            AS last_body,
                   lm.attachment_key  AS last_attachment_key,
                   TO_CHAR(COALESCE(lm.created_at, cr.created_at),
                           'YYYY-MM-DD HH24:MI') AS last_at,
                   lr.deal_type, lr.price_krw, lr.price_krw_max, lr.monthly_rent_krw,
                   lr.area_sqm, lr.yield_rate,
                    TO_CHAR(COALESCE(lr.updated_at, lr.created_at), 'YYYY-MM-DD') AS listing_date,
                   (SELECT COUNT(*) FROM chat_messages
                     WHERE room_id = cr.id
                       AND sender_user_id != %(uid)s
                       AND is_read = FALSE) AS unread_count,
                   ph.thumb_url
              FROM chat_rooms cr
              JOIN listing_requests lr ON lr.id = cr.listing_request_id
              LEFT JOIN master_buildings mb ON mb.id = lr.master_building_id
              JOIN users bu ON bu.id = cr.buyer_user_id
              JOIN users su ON su.id = cr.seller_user_id
              LEFT JOIN LATERAL (
                    SELECT body, attachment_key, created_at
                      FROM chat_messages
                     WHERE room_id = cr.id
                     ORDER BY created_at DESC
                     LIMIT 1
                   ) lm ON TRUE
              LEFT JOIN LATERAL (
                    SELECT '/api/listing-photos/img/' || image_key AS thumb_url
                      FROM listing_photos
                     WHERE listing_request_id = lr.id
                     ORDER BY sort_order ASC, id ASC
                     LIMIT 1
                   ) ph ON TRUE
             WHERE cr.buyer_user_id = %(uid)s OR cr.seller_user_id = %(uid)s
             ORDER BY COALESCE(lm.created_at, cr.created_at) DESC, cr.id DESC
             LIMIT %(limit_plus)s OFFSET %(offset)s
        """, {"uid": u["id"], "limit_plus": limit + 1, "offset": offset})
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        cur.close(); conn.close()
    has_more = len(rows) > limit
    items = []
    for r in rows[:limit]:
        body = (r.get("last_body") or "").strip()
        if not body:
            body = "(첨부파일)" if r.get("last_attachment_key") else "아직 메시지가 없습니다"
        items.append({
            "room_id": r["room_id"],
            "listing_request_id": r["listing_request_id"],
            "building_name": r.get("building_name") or "",
            "opponent_name": r.get("opponent_name") or "상대방",
            "preview": body,
            "last_at": r.get("last_at"),
            "unread_count": int(r["unread_count"]),
            "thumb_url": r.get("thumb_url"),
            "listing_summary": format_lr_summary(
                r.get("deal_type"), r.get("price_krw"), r.get("monthly_rent_krw"),
                r.get("area_sqm"), r.get("yield_rate"), r.get("price_krw_max")),
            "listing_date": r.get("listing_date"),
        })
    return jsonify({"ok": True, "items": items, "limit": limit,
                    "offset": offset, "has_more": has_more})


@app.route("/api/chat/rooms/<int:room_id>/attachments", methods=["POST"])
@limiter.limit("20 per minute")
def upload_chat_attachment(room_id):
    """채팅 첨부파일 업로드 — 채팅방 참여자만, jpg/jpeg/png/pdf 5MB 이하."""
    user = current_user()
    if not user:
        return jsonify({"ok": False, "message": "로그인이 필요합니다."}), 401
    if "file" not in request.files:
        return jsonify({"ok": False, "message": "파일이 없습니다."}), 400
    f = request.files["file"]
    original_name = (f.filename or "").strip()
    if not original_name:
        return jsonify({"ok": False, "message": "파일명이 없습니다."}), 400
    ext = original_name.rsplit(".", 1)[-1].lower() if "." in original_name else ""
    if ext not in storage_util.CHAT_ATTACHMENT_EXTENSIONS:
        return jsonify({"ok": False, "message": "jpg, jpeg, png, pdf만 첨부 가능합니다."}), 400
    data = f.read(storage_util.MAX_FILE_BYTES + 1)
    if len(data) > storage_util.MAX_FILE_BYTES:
        return jsonify({"ok": False, "message": "파일 크기는 5MB 이하여야 합니다."}), 400
    if not storage_util.check_magic_bytes(data, ext):
        return jsonify({"ok": False, "message": "파일 형식이 올바르지 않습니다."}), 400
    conn = get_conn(); cur = conn.cursor()
    try:
        cur.execute("SELECT buyer_user_id, seller_user_id FROM chat_rooms WHERE id = %s", [room_id])
        room = cur.fetchone()
        if not room:
            return jsonify({"ok": False, "message": "채팅방을 찾을 수 없습니다."}), 404
        if user["id"] not in (room["buyer_user_id"], room["seller_user_id"]):
            return jsonify({"ok": False, "message": "접근 권한이 없습니다."}), 403
    finally:
        cur.close(); conn.close()
    key = storage_util.build_chat_attachment_key(ext)
    storage_util.upload_doc(key, data)
    return jsonify({"ok": True, "key": key, "name": original_name})


@app.route("/api/chat/attachments/<path:key>")
def chat_attachment_proxy(key):
    """채팅 첨부파일 다운로드 프록시 — 로그인한 사용자만."""
    user = current_user()
    if not user:
        return jsonify({"ok": False, "message": "로그인이 필요합니다."}), 401
    if not storage_util.is_valid_chat_attachment_ref(key):
        return jsonify({"ok": False, "message": "잘못된 파일 경로입니다."}), 400
    data = storage_util.download_bytes(key)
    ext = key.rsplit(".", 1)[-1].lower()
    ct = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
          "pdf": "application/pdf"}.get(ext, "application/octet-stream")
    return Response(data, mimetype=ct)


@app.route("/api/chat/rooms/<int:room_id>/messages", methods=["POST"])
@limiter.limit("60 per minute")
def send_chat_message(room_id):
    """메시지 전송 — 채팅방 참여자만."""
    user = current_user()
    if not user:
        return jsonify({"ok": False, "message": "로그인이 필요합니다."}), 401
    data = request.get_json(force=True, silent=True) or {}
    body = (data.get("body") or "").strip()[:1000]
    attachment_key  = (data.get("attachment_key")  or "").strip() or None
    attachment_name = (data.get("attachment_name") or "").strip()[:200] or None
    if not body and not attachment_key:
        return jsonify({"ok": False, "message": "메시지 또는 첨부파일을 입력해주세요."}), 400
    if attachment_key and not storage_util.is_valid_chat_attachment_ref(attachment_key):
        return jsonify({"ok": False, "message": "잘못된 첨부파일 참조입니다."}), 400
    conn = get_conn(); cur = conn.cursor()
    try:
        cur.execute("""
            SELECT buyer_user_id, seller_user_id FROM chat_rooms WHERE id = %s
        """, [room_id])
        room = cur.fetchone()
        if not room:
            return jsonify({"ok": False, "message": "채팅방을 찾을 수 없습니다."}), 404
        if user["id"] not in (room["buyer_user_id"], room["seller_user_id"]):
            return jsonify({"ok": False, "message": "접근 권한이 없습니다."}), 403
        cur.execute("""
            INSERT INTO chat_messages (room_id, sender_user_id, body, attachment_key, attachment_name)
            VALUES (%s, %s, %s, %s, %s) RETURNING id, TO_CHAR(created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS sent_at
        """, [room_id, user["id"], body, attachment_key, attachment_name])
        msg = cur.fetchone()
        conn.commit()
        return jsonify({"ok": True, "id": msg["id"], "sent_at": msg["sent_at"]})
    finally:
        cur.close(); conn.close()


@app.route("/api/listing-requests/<int:req_id>", methods=["PUT"])
def update_listing_request(req_id):
    """매물의뢰 수정 — 접수됨 또는 보류 상태인 본인 의뢰만 수정 가능."""
    user = current_user()
    if not user:
        return jsonify({"ok": False, "message": "로그인이 필요합니다."}), 401
    data = request.get_json(force=True, silent=True) or {}
    deal_type = (data.get("deal_type") or "").strip()
    desired_price = (data.get("desired_price") or "").strip()[:100]
    transaction_target = (data.get("transaction_target") or data.get("listing_target") or "unit").strip()
    if transaction_target not in _LISTING_TARGETS:
        return jsonify({"ok": False, "message": "거래대상은 개별호실 또는 건물전체 중 하나여야 합니다."}), 400
    listing_values, listing_error = _whole_listing_values(data)
    if listing_error:
        return jsonify({"ok": False, "message": listing_error}), 400
    deal_type = listing_values["deal_type"]
    whole_values = listing_values if transaction_target == "whole" else None
    is_urgent = listing_values["is_urgent"]

    if transaction_target == "unit" and deal_type not in _LISTING_DEAL_TYPES:
        return jsonify({"ok": False, "message": "거래유형이 올바르지 않습니다."}), 400

    def _parse_krw(field, allowed):
        v = data.get(field)
        if v is None or v == "":
            return None, None
        if not allowed:
            return None, f"{field}는 이 거래유형에서 사용할 수 없습니다."
        try:
            n = int(v)
        except (TypeError, ValueError):
            return None, "희망가는 만원 단위 숫자로 입력해주세요."
        if not (0 < n <= 1_000_000):
            return None, "입력 가능한 최대 금액을 초과했습니다 (최대 100억 만원)."
        return n, None

    try:
        area_sqm = float(data.get("area_sqm") or 0)
        area_sqm = round(area_sqm, 2) if 0 < area_sqm < 100000 else None
    except (TypeError, ValueError):
        area_sqm = None
    dong = (str(data.get("dong") or "").strip()[:20]) or None
    ho = (str(data.get("ho") or "").strip()[:20]) or None
    registrant_type_raw = (data.get("registrant_type") or "owner").strip()
    registrant_type = registrant_type_raw if registrant_type_raw in (
        "owner", "building_owner", "business", "agent", "other"
    ) else "owner"
    if transaction_target == "whole":
        price_krw = whole_values["price_krw"]
        price_krw_max = None
        monthly_rent_krw = whole_values["monthly_rent_krw"]
        deposit_krw = None
        yield_rent_krw = None
        err1 = err2 = err3 = err4 = err5 = None
    else:
        price_krw, err1 = _parse_krw(
            "price_krw",
            deal_type in ("매매", "전세", "월세")
            or (registrant_type == "business" and deal_type == "단기임대"),
        )
        price_krw_max, err2 = _parse_krw(
            "price_krw_max", registrant_type == "business" and deal_type in ("월세", "단기임대")
        )
        monthly_rent_krw, err3 = _parse_krw("monthly_rent_krw", deal_type in ("월세", "매매"))
        deposit_krw, err4 = _parse_krw("deposit_krw", True)
        yield_rent_krw, err5 = _parse_krw("yield_rent_krw", True)
    try:
        room_count_value = data.get("room_count")
        room_count = int(room_count_value) if room_count_value not in (None, "") else None
        if room_count is not None and not (0 < room_count <= 100_000):
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"ok": False, "message": "총 호실수는 1~100,000 사이의 숫자로 입력해주세요."}), 400
    if registrant_type != "business" and transaction_target != "whole":
        room_count = None
    if err1 or err2 or err3 or err4 or err5:
        return jsonify({"ok": False, "message": err1 or err2 or err3 or err4 or err5}), 400
    if price_krw_max is not None and price_krw is None:
        return jsonify({"ok": False, "message": "가격범위의 최저가를 먼저 입력해주세요."}), 400
    if price_krw_max is not None and price_krw_max < price_krw:
        return jsonify({"ok": False, "message": "최고가는 최저가 이상으로 입력해주세요."}), 400
    description = (str(data.get("description") or "").strip()[:500]) or None
    yield_base_rent = yield_rent_krw if yield_rent_krw is not None else monthly_rent_krw
    yield_rate = (
        round((yield_base_rent * 12) / max(price_krw - (deposit_krw or 0), 1) * 100, 1)
        if deal_type == "매매" and price_krw and yield_base_rent else None
    )
    if transaction_target == "whole":
        desired_price = ((str(data.get("desired_price") or "").strip()[:100] or
                          (f"{deal_type} {price_krw:,}만원" if price_krw else deal_type)))
        area_sqm = None
        dong = ho = None
        yield_rate = None
    urgent_email_jobs = []
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """SELECT id, user_id, master_building_id, deal_mode, status, deal_type, desired_price, price_krw, price_krw_max,
                       monthly_rent_krw, room_count, area_sqm, dong, ho, registrant_type, description, deposit_krw,
                       yield_rent_krw, yield_rate, contact_phone, transaction_target,
                       succession_loan_krw, key_money_krw, monthly_revenue_krw, annual_revenue_krw,
                        short_stay_ratio, ota_revenue_ratio, matched_permit_number,
                        operation_status, closed_at, remodeling_info, is_urgent, disclosure_scope,
                       building_info_overrides
               FROM listing_requests WHERE id = %s""", [req_id]
        )
        row = cur.fetchone()
        if not row:
            return jsonify({"ok": False, "message": "의뢰를 찾을 수 없습니다."}), 404
        if row["user_id"] != user["id"]:
            return jsonify({"ok": False, "message": "권한이 없습니다."}), 403
        if row["status"] not in ("submitted", "보류"):
            return jsonify({"ok": False, "message": "접수됨 또는 보류 상태에서만 수정할 수 있습니다."}), 400
        matched_permit_number = None if registrant_type != "business" else row["matched_permit_number"]
        if registrant_type == "business":
            verification = _business_verification_context(cur, row["master_building_id"], user["id"])
            if verification["representative"]:
                current_permit = verification["representative_permit"]
                cached = verification["cached"]
                if not current_permit:
                    return jsonify({
                        "ok": False,
                        "message": "이 건물의 영업신고번호를 확인할 수 없습니다. 관리자에게 문의해주세요.",
                    }), 503
                if not cached or cached.get("permit_number") != current_permit:
                    return jsonify({
                        "ok": False,
                        "message": "사업주 영업신고번호 인증이 필요합니다. 인증 후 다시 시도해주세요.",
                        "requires_business_verification": True,
                    }), 403
                matched_permit_number = current_permit
        before = {
            "deal_type": row["deal_type"], "desired_price": row["desired_price"],
            "price_krw": row["price_krw"], "price_krw_max": row["price_krw_max"],
            "monthly_rent_krw": row["monthly_rent_krw"], "room_count": row["room_count"],
            "area_sqm": row["area_sqm"], "dong": row["dong"], "ho": row["ho"],
            "registrant_type": row["registrant_type"], "description": row["description"],
            "deposit_krw": row["deposit_krw"], "yield_rent_krw": row["yield_rent_krw"],
            "yield_rate": row["yield_rate"], "contact_phone": row["contact_phone"],
            "transaction_target": row["transaction_target"] or "unit",
            "succession_loan_krw": row["succession_loan_krw"], "key_money_krw": row["key_money_krw"],
            "monthly_revenue_krw": row["monthly_revenue_krw"], "annual_revenue_krw": row["annual_revenue_krw"],
            "short_stay_ratio": row["short_stay_ratio"], "ota_revenue_ratio": row["ota_revenue_ratio"],
            "matched_permit_number": row["matched_permit_number"],
            "operation_status": row["operation_status"], "closed_at": row["closed_at"],
            "remodeling_info": row["remodeling_info"], "is_urgent": row["is_urgent"],
            "disclosure_scope": row["disclosure_scope"], "building_info_overrides": row["building_info_overrides"],
        }
        after = {
            "deal_type": deal_type,
            "desired_price": desired_price,
            "price_krw": price_krw, "price_krw_max": price_krw_max,
            "monthly_rent_krw": monthly_rent_krw, "room_count": room_count,
            "area_sqm": area_sqm, "dong": dong, "ho": ho,
            "registrant_type": registrant_type, "description": description,
            "deposit_krw": deposit_krw, "yield_rent_krw": yield_rent_krw,
            "yield_rate": yield_rate, "contact_phone": row["contact_phone"],
            "transaction_target": transaction_target,
            "succession_loan_krw": whole_values["succession_loan_krw"] if whole_values else None,
            "key_money_krw": whole_values["key_money_krw"] if whole_values else None,
            "monthly_revenue_krw": whole_values["monthly_revenue_krw"] if whole_values else None,
            "annual_revenue_krw": whole_values["annual_revenue_krw"] if whole_values else None,
            "short_stay_ratio": whole_values["short_stay_ratio"] if whole_values else None,
            "ota_revenue_ratio": whole_values["ota_revenue_ratio"] if whole_values else None,
            "matched_permit_number": matched_permit_number,
            "operation_status": whole_values["operation_status"] if whole_values else None,
            "closed_at": whole_values["closed_at"] if whole_values else None,
            "remodeling_info": whole_values["remodeling_info"] if whole_values else None,
            "is_urgent": is_urgent,
            "disclosure_scope": whole_values["disclosure_scope"] if whole_values else None,
            "building_info_overrides": whole_values["building_info_overrides"] if whole_values else {},
        }
        before_urgent_tier = _urgent_tier_for_listing(cur, {
            "deal_mode": row.get("deal_mode") or "direct",
            "transaction_target": before["transaction_target"],
            "disclosure_scope": before["disclosure_scope"],
            "status": row["status"], "master_building_id": row["master_building_id"],
            "deal_type": before["deal_type"], "is_urgent": before["is_urgent"],
            "price_krw": before["price_krw"],
        })
        cur.execute(
            """UPDATE listing_requests SET status='submitted', deal_type=%s, desired_price=%s,
                price_krw=%s, price_krw_max=%s, monthly_rent_krw=%s, room_count=%s,
                area_sqm=%s, dong=%s, ho=%s,
               registrant_type=%s, description=%s, deposit_krw=%s,
                yield_rent_krw=%s, yield_rate=%s, transaction_target=%s,
                succession_loan_krw=%s, key_money_krw=%s, monthly_revenue_krw=%s,
                annual_revenue_krw=%s, short_stay_ratio=%s, ota_revenue_ratio=%s,
                matched_permit_number=%s, operation_status=%s, closed_at=%s,
                remodeling_info=%s, is_urgent=%s, disclosure_scope=%s,
                building_info_overrides=%s, updated_at=NOW() WHERE id=%s""",
            [after["deal_type"], after["desired_price"] or None, after["price_krw"],
              after["price_krw_max"], after["monthly_rent_krw"], after["room_count"],
              after["area_sqm"], after["dong"], after["ho"],
             after["registrant_type"], after["description"], after["deposit_krw"],
              after["yield_rent_krw"], after["yield_rate"], after["transaction_target"],
              after["succession_loan_krw"], after["key_money_krw"], after["monthly_revenue_krw"],
               after["annual_revenue_krw"], after["short_stay_ratio"], after["ota_revenue_ratio"],
               after["matched_permit_number"], after["operation_status"], after["closed_at"],
              after["remodeling_info"], after["is_urgent"], after["disclosure_scope"],
              json.dumps(after["building_info_overrides"] or {}), req_id]
        )
        if (
            after["transaction_target"] == "whole"
            and (after["disclosure_scope"] or "limited") == "limited"
        ):
            cur.execute(
                "UPDATE listing_photos SET is_public=FALSE WHERE listing_request_id=%s",
                [req_id],
            )
            cur.execute("""
                DELETE FROM building_photos
                 WHERE source='upload'
                   AND listing_photo_id IN (
                       SELECT id FROM listing_photos WHERE listing_request_id=%s
                   )
            """, [req_id])
            _refresh_building_photo_primary(cur, row["master_building_id"])
        cur.execute(
            "INSERT INTO listing_request_history (listing_request_id, action, before_data, after_data) "
            "VALUES (%s, 'edited', %s, %s)",
            # PostgreSQL NUMERIC는 Decimal로 반환될 수 있으므로 이력 저장 시
            # JSON 직렬화 실패로 본문 수정 전체가 500이 되지 않게 한다.
            [req_id, json.dumps(before, default=str), json.dumps(after, default=str)]
        )
        after_urgent_tier = _urgent_tier_for_listing(cur, {
            "deal_mode": row["deal_mode"], "transaction_target": after["transaction_target"],
            "disclosure_scope": after["disclosure_scope"], "status": "submitted",
            "master_building_id": row["master_building_id"], "deal_type": after["deal_type"],
            "is_urgent": after["is_urgent"], "price_krw": after["price_krw"],
        })
        if after_urgent_tier and not before_urgent_tier:
            cur.execute("SAVEPOINT urgent_listing_alerts")
            try:
                cur.execute(
                    "SELECT building_name, road_address, jibun_address FROM master_buildings WHERE id=%s",
                    [row["master_building_id"]],
                )
                building = cur.fetchone() or {}
                urgent_email_jobs = _queue_urgent_listing_alerts(
                    cur, req_id, row["master_building_id"], building.get("building_name"),
                    building.get("road_address") or building.get("jibun_address"),
                    after["price_krw"], after_urgent_tier, after["deal_type"],
                )
                cur.execute("RELEASE SAVEPOINT urgent_listing_alerts")
            except Exception:
                cur.execute("ROLLBACK TO SAVEPOINT urgent_listing_alerts")
                cur.execute("RELEASE SAVEPOINT urgent_listing_alerts")
                urgent_email_jobs = []
                app.logger.exception("수정 매물의 급매 알림 예약 실패(listing_id=%s)", req_id)
        conn.commit()
    finally:
        cur.close()
        conn.close()
    for urgent_email_job in urgent_email_jobs:
        _send_urgent_listing_email(urgent_email_job)
    return jsonify({"ok": True})


@app.route("/api/listing-requests/<int:req_id>/withdraw", methods=["POST"])
def withdraw_listing_request(req_id):
    """매물의뢰 철회 — 접수됨 또는 보류 상태인 본인 의뢰만 철회 가능."""
    user = current_user()
    if not user:
        return jsonify({"ok": False, "message": "로그인이 필요합니다."}), 401
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id, user_id, status FROM listing_requests WHERE id = %s", [req_id])
        row = cur.fetchone()
        if not row:
            return jsonify({"ok": False, "message": "의뢰를 찾을 수 없습니다."}), 404
        if row["user_id"] != user["id"]:
            return jsonify({"ok": False, "message": "권한이 없습니다."}), 403
        if row["status"] not in ("submitted", "보류"):
            return jsonify({"ok": False, "message": "접수됨 또는 보류 상태에서만 철회할 수 있습니다."}), 400
        # 연관 데이터 순서대로 삭제 (FK NO ACTION이므로 수동 처리)
        cur.execute("""
            DELETE FROM chat_messages
            WHERE room_id IN (SELECT id FROM chat_rooms WHERE listing_request_id = %s)
        """, [req_id])
        cur.execute("DELETE FROM chat_rooms WHERE listing_request_id = %s", [req_id])
        cur.execute("DELETE FROM listing_request_history WHERE listing_request_id = %s", [req_id])
        cur.execute("DELETE FROM listing_requests WHERE id = %s", [req_id])
        conn.commit()
    finally:
        cur.close()
        conn.close()
    return jsonify({"ok": True})


def _set_listing_hold_state(req_id, *, held):
    """본인 매물의뢰를 보류하거나 보류해제한다."""
    user = current_user()
    if not user:
        return jsonify({"ok": False, "message": "로그인이 필요합니다."}), 401
    expected_status = "submitted" if held else "보류"
    next_status = "보류" if held else "submitted"
    action = "held" if held else "resumed"
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id, user_id, status FROM listing_requests WHERE id = %s",
            [req_id],
        )
        row = cur.fetchone()
        if not row:
            return jsonify({"ok": False, "message": "의뢰를 찾을 수 없습니다."}), 404
        if row["user_id"] != user["id"]:
            return jsonify({"ok": False, "message": "권한이 없습니다."}), 403
        if row["status"] != expected_status:
            label = "접수됨" if held else "보류중"
            return jsonify({"ok": False, "message": f"{label} 상태에서만 변경할 수 있습니다."}), 400
        cur.execute(
            "UPDATE listing_requests SET status=%s, updated_at=NOW() "
            "WHERE id=%s RETURNING id, status",
            [next_status, req_id],
        )
        item = dict(cur.fetchone())
        cur.execute(
            "INSERT INTO listing_request_history (listing_request_id, action, after_data) "
            "VALUES (%s, %s, %s)",
            [req_id, action, json.dumps({"status": next_status})],
        )
        conn.commit()
        return jsonify({"ok": True, "item": item})
    finally:
        cur.close()
        conn.close()


@app.route("/api/listing-requests/<int:req_id>/hold", methods=["POST"])
def hold_listing_request(req_id):
    return _set_listing_hold_state(req_id, held=True)


@app.route("/api/listing-requests/<int:req_id>/resume", methods=["POST"])
@app.route("/api/listing-requests/<int:req_id>/unhold", methods=["POST"])
def resume_listing_request(req_id):
    return _set_listing_hold_state(req_id, held=False)


@app.route("/api/listing-requests/<int:req_id>/disclosure-scope", methods=["PATCH", "PUT"])
def update_listing_disclosure_scope(req_id):
    """본인 매물의 공개범위만 즉시 변경한다."""
    user = current_user()
    if not user:
        return jsonify({"ok": False, "message": "로그인이 필요합니다."}), 401
    data = request.get_json(force=True, silent=True) or {}
    scope = data.get("disclosure_scope", data.get("scope"))
    if scope not in ("public", "limited"):
        return jsonify({"ok": False, "message": "공개범위는 전체공개 또는 제한공개만 선택할 수 있습니다."}), 400
    urgent_email_jobs = []
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """SELECT id, user_id, transaction_target, master_building_id, deal_mode, status,
                      deal_type, price_krw, is_urgent, disclosure_scope
                 FROM listing_requests WHERE id=%s""",
            [req_id],
        )
        row = cur.fetchone()
        if not row:
            return jsonify({"ok": False, "message": "의뢰를 찾을 수 없습니다."}), 404
        if row["user_id"] != user["id"]:
            return jsonify({"ok": False, "message": "권한이 없습니다."}), 403
        if row["transaction_target"] != "whole":
            return jsonify({"ok": False, "message": "공개범위는 건물전체 매물에서만 변경할 수 있습니다."}), 400
        before_urgent_tier = _urgent_tier_for_listing(cur, row)
        cur.execute(
            "UPDATE listing_requests SET disclosure_scope=%s, updated_at=NOW() "
            "WHERE id=%s RETURNING id, disclosure_scope",
            [scope, req_id],
        )
        item = dict(cur.fetchone())
        if scope == "limited":
            cur.execute(
                "UPDATE listing_photos SET is_public=FALSE WHERE listing_request_id=%s",
                [req_id],
            )
            cur.execute("""
                DELETE FROM building_photos
                 WHERE source='upload'
                   AND listing_photo_id IN (
                       SELECT id FROM listing_photos WHERE listing_request_id=%s
                   )
            """, [req_id])
            _refresh_building_photo_primary(cur, row["master_building_id"])
        cur.execute(
            "INSERT INTO listing_request_history (listing_request_id, action, after_data) "
            "VALUES (%s, 'scope_changed', %s)",
            [req_id, json.dumps({"disclosure_scope": scope})],
        )
        after_urgent_tier = _urgent_tier_for_listing(cur, {
            **dict(row), "disclosure_scope": scope,
        })
        if after_urgent_tier and not before_urgent_tier:
            cur.execute("SAVEPOINT urgent_listing_alerts")
            try:
                cur.execute(
                    "SELECT building_name, road_address, jibun_address FROM master_buildings WHERE id=%s",
                    [row["master_building_id"]],
                )
                building = cur.fetchone() or {}
                urgent_email_jobs = _queue_urgent_listing_alerts(
                    cur, req_id, row["master_building_id"], building.get("building_name"),
                    building.get("road_address") or building.get("jibun_address"),
                    row["price_krw"], after_urgent_tier, row["deal_type"],
                )
                cur.execute("RELEASE SAVEPOINT urgent_listing_alerts")
            except Exception:
                cur.execute("ROLLBACK TO SAVEPOINT urgent_listing_alerts")
                cur.execute("RELEASE SAVEPOINT urgent_listing_alerts")
                urgent_email_jobs = []
                app.logger.exception("공개전환 급매 알림 예약 실패(listing_id=%s)", req_id)
        conn.commit()
    finally:
        cur.close()
        conn.close()
    for urgent_email_job in urgent_email_jobs:
        _send_urgent_listing_email(urgent_email_job)
    return jsonify({"ok": True, "item": item})


@app.route("/api/listing-requests/<int:req_id>/history")
def listing_request_history_api(req_id):
    """매물의뢰 이력 조회 — 본인 것만."""
    user = current_user()
    if not user:
        return jsonify({"ok": False, "message": "로그인이 필요합니다."}), 401
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT user_id FROM listing_requests WHERE id = %s", [req_id])
        row = cur.fetchone()
        if not row:
            return jsonify({"ok": False, "message": "의뢰를 찾을 수 없습니다."}), 404
        if row["user_id"] != user["id"]:
            return jsonify({"ok": False, "message": "권한이 없습니다."}), 403
        cur.execute(
            "SELECT id, action, before_data, after_data, "
            "to_char(created_at, 'YYYY-MM-DD HH24:MI') AS created_at "
            "FROM listing_request_history WHERE listing_request_id = %s "
            "ORDER BY created_at ASC",
            [req_id]
        )
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        cur.close()
        conn.close()
    return jsonify({"ok": True, "history": rows})


# ============================================================
# 운영업체(operators) 로그인 — 승인된 운영업체만. agent 로그인과 같은 패턴.
# 세션에 operator_id 저장. require_operator 로 보호.
# ============================================================

def require_operator(f):
    """세션에 operator_id가 없으면 차단한다.
    /api/* 요청은 401 JSON, 그 외는 /operator/login으로 리다이렉트."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("operator_id"):
            if request.path.startswith("/api/"):
                return jsonify({"ok": False, "message": "로그인이 필요합니다."}), 401
            return redirect("/operator/login")
        return f(*args, **kwargs)
    return wrapper


@app.route("/operator/login")
def operator_login_page():
    return _serve_static_html("operator_login.html")


@app.route("/api/operator/login", methods=["POST"])
@limiter.limit("5 per minute; 20 per hour")
def operator_login():
    """operators 테이블 기반 이메일/비밀번호 로그인. status='approved'만 허용.
    실패 시 이메일 존재 여부를 드러내지 않도록 통일된 메시지로 401을 반환한다."""
    data = request.get_json(force=True, silent=True) or {}
    email = (data.get("email") or "").strip()
    password = data.get("password") or ""
    fail = jsonify({"ok": False, "message": "이메일 또는 비밀번호가 올바르지 않습니다."}), 401
    if not email or not password:
        return fail

    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id, password_hash, status FROM operators WHERE LOWER(email) = LOWER(%s)",
            (email,),
        )
        row = cur.fetchone()
        if not row or not row["password_hash"] or not check_password_hash(row["password_hash"], password):
            return fail
        if row["status"] != "approved":
            return jsonify({"ok": False, "message": "승인된 운영지원업체 계정이 아닙니다."}), 403
    finally:
        cur.close()
        conn.close()

    session["operator_id"] = row["id"]
    session.permanent = True
    return jsonify({"ok": True})


@app.route("/api/operator/logout", methods=["POST"])
def operator_logout():
    session.pop("operator_id", None)
    return jsonify({"ok": True})


@app.route("/api/operator/password", methods=["PUT"])
@require_operator
@limiter.limit("5 per minute; 20 per hour")
def operator_change_password():
    """운영업체 비밀번호 변경 — 현재 비밀번호 확인 후 교체 (agent와 같은 패턴)."""
    operator_id = session.get("operator_id")
    data = request.get_json(force=True, silent=True) or {}
    current_pw = data.get("current_password") or ""
    new_pw = data.get("new_password") or ""
    if len(new_pw) < 8:
        return jsonify({"ok": False, "message": "새 비밀번호는 8자 이상이어야 합니다."}), 400

    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT password_hash FROM operators WHERE id = %s", (operator_id,))
        row = cur.fetchone()
        if not row or not row["password_hash"] or not check_password_hash(row["password_hash"], current_pw):
            return jsonify({"ok": False, "message": "현재 비밀번호가 올바르지 않습니다."}), 401
        cur.execute(
            "UPDATE operators SET password_hash = %s WHERE id = %s",
            (generate_password_hash(new_pw), operator_id),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()
    return jsonify({"ok": True})


# ---- 운영업체 공개 프로필 + 대시보드(본인 데이터 관리) — agent와 동일 패턴 ----
# 차이점: 매물 개수(매매/전세/월세/단기임대) 개념 없음. "담당 단지 + 메모(note)"만 관리.

@app.route("/operator/<slug>")
def operator_profile_page(slug):
    """운영업체 공개 프로필 페이지. Flask는 정적 룰(/operator/login, /operator/dashboard)을 우선 매칭하므로 충돌 없음."""
    return _serve_static_html("operator_profile.html")


def _render_markdown_safe(text: str) -> str:
    """마크다운 원문 → 안전한 HTML 변환.
    1) html.escape로 전체 이스케이프 → <script> 등 완전 무해화
    2) 최소 마크다운만 변환: ![alt](url), [text](url), **굵게**, *기울임*, 줄바꿈
    3) href/src URL: http(s):// 시작만 허용, javascript: 등 차단
    """
    if not text:
        return ""

    def _safe_url(raw: str) -> str:
        u = _html.unescape(raw).strip()
        if u.startswith(("http://", "https://")):
            return _html.escape(u, quote=True)
        # 자체 소개글 이미지 경로 허용 (operator/agent/loan_consultant)
        if re.match(r'^/api/(?:operator|agent|loan_consultant)/intro-image-file/[a-zA-Z0-9/_.-]+$', u):
            return _html.escape(u, quote=True)
        return ""

    s = _html.escape(text)

    # 이미지: ![alt](url) — 링크보다 먼저 처리
    def _img(m):
        su = _safe_url(m.group(2))
        if not su:
            return m.group(0)
        return f'<img src="{su}" alt="{m.group(1)}" style="max-width:100%;height:auto;border-radius:4px;">'
    s = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', _img, s)

    # 링크: [text](url)
    def _link(m):
        su = _safe_url(m.group(2))
        if not su:
            return m.group(1)
        return f'<a href="{su}" target="_blank" rel="noopener noreferrer">{m.group(1)}</a>'
    s = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', _link, s)

    # 굵게: **text**
    s = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', s, flags=re.DOTALL)
    # 기울임: *text* (굵게 처리 후)
    s = re.sub(r'\*([^*\n]+?)\*', r'<i>\1</i>', s)
    # 줄바꿈
    s = s.replace('\n', '<br>\n')
    return s


@app.route("/api/operator/profile/<slug>")
def operator_public_profile(slug):
    """운영업체 공개 프로필 API — 인증 불필요. approved 상태만 노출."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT id, company_name, owner_name, category, phone, photo_url, logo_url, intro_text,
                   office_address, biz_reg_number, website_url
            FROM operators
            WHERE subdomain_slug = %s AND status = 'approved'
        """, [slug])
        op = cur.fetchone()
        if not op:
            return jsonify({"error": "not found"}), 404
        cur.execute("""
            SELECT ob.master_building_id, mb.building_name, mb.lodging_type,
                   mb.lodging_subtype, ob.note
            FROM operator_buildings ob
            JOIN master_buildings mb ON mb.id = ob.master_building_id
            WHERE ob.operator_id = %s
            ORDER BY mb.building_name
        """, [op["id"]])
        buildings = [dict(r) for r in cur.fetchall()]
    finally:
        cur.close()
        conn.close()
    return jsonify({
        "company_name": op["company_name"],
        "owner_name": op["owner_name"],
        "category": op["category"],
        "phone": op["phone"],
        "logo_src": f"/api/partners/operator-logo/{op['id']}" if op["logo_url"] else None,
        "intro_text": _render_markdown_safe(op["intro_text"] or ""),
        "office_address": op["office_address"],
        "biz_reg_number": op["biz_reg_number"],
        "website_url": (op["website_url"] if (op["website_url"] or "").startswith(("http://", "https://")) else None),
        "buildings": buildings,
        "building_count": len(buildings),
    })


@app.route("/operator/dashboard")
@require_operator
def operator_dashboard_page():
    return _serve_static_html("operator_dashboard.html")


@app.route("/api/operator/me")
@require_operator
def operator_me():
    operator_id = session["operator_id"]
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT company_name, owner_name, category, phone, photo_url, logo_url, intro_text, subdomain_slug,
                   email, biz_reg_number, status,
                   COALESCE(is_visible, TRUE) AS is_visible
            FROM operators WHERE id = %s
        """, [operator_id])
        me = cur.fetchone()
        if not me:
            return jsonify({"ok": False, "message": "계정을 찾을 수 없습니다."}), 404
        cur.execute("""
            SELECT ob.master_building_id, mb.building_name, mb.lodging_type,
                   mb.lodging_subtype, ob.note,
                   ob.has_priority_badge,
                   ob.premium_expires_at,
                   ob.premium_granted_at,
                   mb.booking_url,
                   mb.booking_url_source,
                   mb.booking_url_expires_at,
                   bur.id        AS bur_id,
                   bur.booking_url AS bur_url,
                   bur.status    AS bur_status,
                   bur.submitted_at AS bur_submitted_at
            FROM operator_buildings ob
            JOIN master_buildings mb ON mb.id = ob.master_building_id
            LEFT JOIN LATERAL (
                SELECT id, booking_url, status, submitted_at
                FROM booking_url_requests
                WHERE operator_id = %s AND master_building_id = ob.master_building_id
                ORDER BY submitted_at DESC
                LIMIT 1
            ) bur ON TRUE
            WHERE ob.operator_id = %s
            ORDER BY mb.building_name
        """, [operator_id, operator_id])
        import datetime as _dt
        buildings = []
        for r in cur.fetchall():
            b = dict(r)
            # 만료 체크
            exp = b.get("booking_url_expires_at")
            if exp and exp < _dt.datetime.utcnow():
                b["booking_url"] = None  # 만료됨
            if b.get("booking_url_expires_at"):
                b["booking_url_expires_at"] = b["booking_url_expires_at"].isoformat()
            if b.get("premium_expires_at"):
                b["premium_expires_at"] = b["premium_expires_at"].isoformat()
            if b.get("premium_granted_at"):
                b["premium_granted_at"] = b["premium_granted_at"].isoformat()
            if b.get("bur_submitted_at"):
                b["bur_submitted_at"] = b["bur_submitted_at"].isoformat()
            buildings.append(b)
    finally:
        cur.close()
        conn.close()
    out = dict(me)
    out["logo_src"] = f"/api/partners/operator-logo/{operator_id}" if out.get("logo_url") else None
    out["buildings"] = buildings
    out["building_cap"] = MAX_FREE_BUILDINGS
    out["badge_cap"] = OPERATOR_PREMIUM_BADGE_CAP
    return jsonify(out)


@app.route("/api/operator/me", methods=["PUT"])
@require_operator
def operator_me_update():
    """부분 업데이트 — 전달된 키만 수정 (agent와 동일 패턴). 사업자등록번호 변경 시 재승인 대기 전환."""
    operator_id = session["operator_id"]
    data = request.get_json(force=True, silent=True) or {}
    allowed = ["phone", "photo_url", "logo_url", "intro_text", "company_name", "owner_name", "email", "biz_reg_number"]
    sets, params = [], []
    license_changes = {}
    for k in allowed:
        if k in data:
            v = data.get(k)
            if v is not None and not isinstance(v, str):
                return jsonify({"ok": False, "message": f"{k} 값이 올바르지 않습니다."}), 400
            v = (v or "").strip() or None
            if k == "phone":
                # 하이픈 유무와 무관하게 숫자만 저장 + 자릿수 검증 (표시할 때 재포맷)
                v = _digits_only(v) or None
                if v and not _validate_phone_digits(v):
                    return jsonify({"ok": False, "message": "전화번호 형식이 올바르지 않습니다. (숫자 10~11자리)"}), 400
            if k in ("photo_url", "logo_url") and v and not (v.startswith("http://") or v.startswith("https://")):
                return jsonify({"ok": False, "message": ("사진" if k == "photo_url" else "로고") + " URL은 http(s)://로 시작해야 합니다."}), 400
            if k in ("company_name", "owner_name") and not v:
                return jsonify({"ok": False, "message": ("업체명" if k == "company_name" else "대표자명") + "은(는) 비울 수 없습니다."}), 400
            if k == "email":
                if not v or not _EMAIL_RE.match(v):
                    return jsonify({"ok": False, "message": "이메일 형식이 올바르지 않습니다."}), 400
                v = v.lower()
            if k == "intro_text" and v and len(v) > 5000:
                return jsonify({"ok": False, "message": "소개글은 5000자 이내로 입력해주세요."}), 400
            if k == "biz_reg_number":
                v = _digits_only(v) or None
                if not v:
                    return jsonify({"ok": False, "message": "사업자등록번호는 비울 수 없습니다."}), 400
                if len(v) != 10:
                    return jsonify({"ok": False, "message": "사업자등록번호 형식이 올바르지 않습니다. (숫자 10자리)"}), 400
                license_changes[k] = v
            sets.append(f"{k} = %s")
            params.append(v)
    if not sets:
        return jsonify({"ok": False, "message": "수정할 항목이 없습니다."}), 400
    conn = get_conn()
    cur = conn.cursor()
    try:
        extra_sets, extra_params, reapproval = _reapply_if_license_changed(cur, "operators", operator_id, license_changes)
        cur.execute(f"UPDATE operators SET {', '.join(sets + extra_sets)} WHERE id = %s",
                    params + extra_params + [operator_id])
        conn.commit()
    except psycopg2_errors.UniqueViolation:
        conn.rollback()
        return jsonify({"ok": False, "message": "이미 다른 계정에서 사용 중인 이메일 또는 사업자등록번호입니다."}), 400
    finally:
        cur.close()
        conn.close()
    if reapproval:
        _mark_master_stats_invalidated_safely("operator_me_reapproval")
    return jsonify({"ok": True, "reapproval_required": reapproval})


@app.route("/api/operator/visibility", methods=["PUT"])
@require_operator
def operator_visibility_update():
    """노출 여부 토글 — 본인 세션 기준. is_visible만 갱신 (agent와 동일 패턴)."""
    data = request.get_json(force=True, silent=True) or {}
    v = data.get("is_visible")
    if not isinstance(v, bool):
        return jsonify({"ok": False, "message": "is_visible 값은 true/false여야 합니다."}), 400
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE operators SET is_visible = %s WHERE id = %s", (v, session["operator_id"]))
        conn.commit()
    finally:
        cur.close()
        conn.close()
    return jsonify({"ok": True, "is_visible": v})


@app.route("/api/operator/logo", methods=["POST"])
@require_operator
def operator_logo_upload():
    """마이페이지에서 로고 업로드/교체 — 신청서 업로드와 동일한 검증."""
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"ok": False, "message": "파일을 선택해주세요."}), 400
    ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
    if ext not in storage_util.LOGO_EXTENSIONS:
        return jsonify({"ok": False, "message": "JPG 또는 PNG 이미지만 업로드할 수 있습니다."}), 400
    data = f.read(storage_util.MAX_FILE_BYTES + 1)
    if len(data) > storage_util.MAX_FILE_BYTES:
        return jsonify({"ok": False, "message": "파일 크기는 5MB 이하여야 합니다."}), 400
    if len(data) < 16:
        return jsonify({"ok": False, "message": "파일이 비어 있거나 손se _search_ranking_fallback_centroid(row["sido_name"], row["sgg_name"])
            )
            lat, lng = (
                (float(row["lat"]), float(row["lng"]))
                if has_sgg_centroid else (fallback_centroid or (None, None))
            )
            items.append({
                "name": row["attraction_name"],
                "rank": int(row["rank"]),
                "sido": row["sido_name"],
                "sgg": row["sgg_name"],
                "lat": lat,
                "lng": lng,
                "coordinate_scope": (
                    "sgg_centroid" if has_sgg_centroid else "sgg_office_fallback"
                ),
                "source_period": row["source_period"],
            })
        return jsonify({"items": items, "coordinate_scope": "sgg_representative"})
    finally:
        try:
            if cur is not None:
                cur.close()
        finally:
            if conn is not None:
                release_conn(conn)


def _tourism_surge_payload(stat_type, label):
    """최신 방문자 급등동네 TOP 10과 행정동 중심 좌표를 반환한다."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            WITH latest AS (
                SELECT source_file
                FROM tourism_stats
                WHERE stat_type = %s
                ORDER BY COALESCE(split_part(source_period, '-', 2), '') DESC,
                         source_file DESC
                LIMIT 1
            ),
            source_rows AS (
                SELECT
                    t.sido_name,
                    t.sgg_name,
                    t.ref_yearmonth,
                    t.source_period,
                    t.dimensions->>'행정동명' AS dong_name,
                    NULLIF(t.dimensions->>'순위', '')::INTEGER AS rank,
                    t.dimensions->>'조회일자' AS query_period,
                    MAX(t.metric_value) FILTER (WHERE t.metric_name = '관광객수') AS current_visitors,
                    MAX(t.metric_value) FILTER (WHERE t.metric_name = '전년동기관광객수') AS previous_year_visitors,
                    MAX(t.metric_value) FILTER (WHERE t.metric_name = '증감율') AS growth_rate
                FROM tourism_stats t
                JOIN latest l ON l.source_file = t.source_file
                WHERE t.stat_type = %s
                GROUP BY t.sido_name, t.sgg_name, t.ref_yearmonth, t.source_period,
                         t.dimensions->>'행정동명', t.dimensions->>'순위',
                         t.dimensions->>'조회일자'
            )
            SELECT s.*, c.lat, c.lng, c.building_count
            FROM source_rows s
            LEFT JOIN tourism_dong_coords c
              ON c.sido_name = s.sido_name
             AND c.sgg_name = s.sgg_name
             AND c.dong_name = s.dong_name
            ORDER BY s.rank NULLS LAST, s.growth_rate DESC
            LIMIT 10
        """, (stat_type, stat_type))
        items = []
        for row in cur.fetchall():
            items.append({
                "rank": int(row["rank"] or len(items) + 1),
                "sido": row["sido_name"],
                "sgg": row["sgg_name"],
                "dong": row["dong_name"],
                "lat": float(row["lat"]) if row["lat"] is not None else None,
                "lng": float(row["lng"]) if row["lng"] is not None else None,
                "building_count": int(row["building_count"] or 0),
                "current_visitors": float(row["current_visitors"] or 0),
                "previous_year_visitors": float(row["previous_year_visitors"] or 0),
                "growth_rate": float(row["growth_rate"] or 0),
                "ref_yearmonth": row["ref_yearmonth"],
                "query_period": row["query_period"],
                "source_period": row["source_period"],
            })
        mapped_count = sum(
            item["lat"] is not None and item["lng"] is not None for item in items
        )
        return {
            "ok": True,
            "type": stat_type,
            "label": label,
            "items": items,
            "mapped_count": mapped_count,
            "unmapped_count": len(items) - mapped_count,
            "source": "한국관광 데이터랩",
            "note": "전국 전체 동 분포가 아닌 전년 동기 대비 방문자 급등 TOP 10입니다.",
        }
    finally:
        cur.close()
        conn.close()


@app.route("/api/tourism/surge/domestic")
@limiter.limit("30 per minute")
def tourism_surge_domestic():
    return jsonify(_tourism_surge_payload("surge_domestic_dong", "내국인 방문자 급등동네"))


@app.route("/api/tourism/surge/foreign")
@limiter.limit("30 per minute")
def tourism_surge_foreign():
    return jsonify(_tourism_surge_payload("surge_foreign_dong", "외국인 방문자 급등동네"))


@app.route("/api/stats/price-change-top")
@limiter.limit("30 per minute")
def stats_price_change_top(_direction=None, _as_payload=False):
    """최근 30일 안의 동일 건물·주소·전용면적 거래 첫값 대비 최근값 변동 TOP5."""
    direction = (
        _direction
        if _direction is not None
        else (request.args.get("direction") or "up").strip().lower()
    )
    if direction not in ("up", "down"):
        return jsonify({"ok": False, "message": "direction은 up 또는 down이어야 합니다."}), 400

    master_payload = _master_stats_section("transaction_stats")
    if (
        master_payload is not None
        and direction in (master_payload.get("price_change") or {})
    ):
        return jsonify(master_payload["price_change"][direction])

    if _master_stats_cold_starting():
        payload = {"ok": False, "status": "warming", "direction": direction, "items": []}
        return payload if _as_payload else jsonify(payload)

    # [LEGACY] 원본 캐시의 거래 섹션이 없거나 실패했을 때의 기존 직접 집계.
    conn = get_conn()
    cur = conn.cursor()
    try:
        comparison = "change_percent > 0" if direction == "up" else "change_percent < 0"
        ordering = "change_percent DESC" if direction == "up" else "change_percent ASC"
        cur.execute(f"""
            WITH grouped AS (
                SELECT
                    building_name,
                    address,
                    MIN(sgg_nm) AS sgg_nm,
                    sgg_cd,
                    umd_nm,
                    jibun,
                    COUNT(*) AS transaction_count,
                    (array_agg(price ORDER BY deal_date ASC, id ASC))[1] AS first_price,
                    (array_agg(price ORDER BY deal_date DESC, id DESC))[1] AS latest_price,
                    (array_agg(deal_date ORDER BY deal_date ASC, id ASC))[1] AS first_deal_date,
                    (array_agg(deal_date ORDER BY deal_date DESC, id DESC))[1] AS latest_deal_date,
                    area AS area_sqm
                FROM transactions
                WHERE transaction_scope = 'unit'
                  AND deal_date IS NOT NULL
                  AND deal_date >= TO_CHAR(CURRENT_DATE - INTERVAL '30 days', 'YYYY-MM-DD')
                  AND area > 0
                  AND price > 0
                GROUP BY building_name, address, sgg_cd, umd_nm, jibun, area
                HAVING COUNT(*) >= 2
            ),
            changed AS (
                SELECT *,
                       100.0 * (latest_price - first_price) / NULLIF(first_price, 0)
                         AS change_percent
                FROM grouped
            )
            SELECT
                building_name, address, sgg_nm, sgg_cd, umd_nm, jibun, transaction_count,
                first_price, latest_price, first_deal_date, latest_deal_date,
                area_sqm, change_percent,
                (SELECT id FROM master_buildings
                 WHERE building_name = changed.building_name
                    AND sgg_cd = changed.sgg_cd
                    AND umd_nm = changed.umd_nm
                    AND jibun = changed.jibun
                  ORDER BY id LIMIT 1) AS building_id,
                 (SELECT lat FROM master_buildings
                  WHERE building_name = changed.building_name
                    AND sgg_cd = changed.sgg_cd
                    AND umd_nm = changed.umd_nm
                    AND jibun = changed.jibun
                  ORDER BY id LIMIT 1) AS lat,
                 (SELECT lng FROM master_buildings
                  WHERE building_name = changed.building_name
                    AND sgg_cd = changed.sgg_cd
                    AND umd_nm = changed.umd_nm
                    AND jibun = changed.jibun
                  ORDER BY id LIMIT 1) AS lng
            FROM changed
            WHERE {comparison}
            ORDER BY {ordering}, building_name, address, area_sqm
            LIMIT 5
        """)
        items = [
            {
                "building_name": row["building_name"],
                "address": row["address"],
                "sgg_nm": row["sgg_nm"],
                "sgg_cd": row["sgg_cd"],
                "umd_nm": row["umd_nm"],
                "jibun": row["jibun"],
                "building_id": row["building_id"],
                "lat": float(row["lat"]) if row["lat"] is not None else None,
                "lng": float(row["lng"]) if row["lng"] is not None else None,
                "area_sqm": float(row["area_sqm"]),
                "transaction_count": int(row["transaction_count"]),
                "first_price": int(row["first_price"]),
                "latest_price": int(row["latest_price"]),
                "first_deal_date": row["first_deal_date"],
                "latest_deal_date": row["latest_deal_date"],
                "change_percent": round(float(row["change_percent"]), 1),
            }
            for row in cur.fetchall()
        ]
        payload = {"ok": True, "direction": direction, "items": items}
        return payload if _as_payload else jsonify(payload)
    finally:
        cur.close()
        conn.close()


@app.route("/api/stats/highest-price-top")
@limiter.limit("30 per minute")
def stats_highest_price_top(_order=None, _as_payload=False):
    """건물별 역대 최고·최저 거래가 TOP5."""
    order = (
        _order
        if _order is not None
        else (request.args.get("order") or "highest").strip().lower()
    )
    if order not in ("highest", "lowest"):
        return jsonify({"ok": False, "message": "order는 highest 또는 lowest여야 합니다."}), 400
    price_order = "DESC" if order == "highest" else "ASC"

    master_payload = _master_stats_section("transaction_stats")
    if (
        master_payload is not None
        and order in (master_payload.get("highest_price") or {})
    ):
        return jsonify(master_payload["highest_price"][order])

    if _master_stats_cold_starting():
        payload = {"ok": False, "status": "warming", "order": order, "items": []}
        return payload if _as_payload else jsonify(payload)

    # [LEGACY] 원본 캐시의 거래 섹션이 없거나 실패했을 때의 기존 직접 집계.
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(f"""
            WITH extreme_by_building AS (
                SELECT DISTINCT ON (building_name, address)
                    building_name, address, sgg_nm, sgg_cd, umd_nm, jibun, price, deal_date, id
                FROM transactions
                WHERE transaction_scope = 'unit'
                  AND price > 0 AND deal_date IS NOT NULL
                ORDER BY building_name, address, price {price_order}, deal_date DESC, id DESC
            )
            SELECT
                building_name, address, sgg_nm, umd_nm, price, deal_date,
                (SELECT id FROM master_buildings
                 WHERE building_name = extreme_by_building.building_name
                    AND sgg_cd = extreme_by_building.sgg_cd
                    AND umd_nm = extreme_by_building.umd_nm
                    AND jibun = extreme_by_building.jibun
                 ORDER BY id LIMIT 1) AS building_id,
                (SELECT lat FROM master_buildings
                 WHERE building_name = extreme_by_building.building_name
                    AND sgg_cd = extreme_by_building.sgg_cd
                    AND umd_nm = extreme_by_building.umd_nm
                    AND jibun = extreme_by_building.jibun
                 ORDER BY id LIMIT 1) AS lat,
                (SELECT lng FROM master_buildings
                 WHERE building_name = extreme_by_building.building_name
                    AND sgg_cd = extreme_by_building.sgg_cd
                    AND umd_nm = extreme_by_building.umd_nm
                    AND jibun = extreme_by_building.jibun
                 ORDER BY id LIMIT 1) AS lng
            FROM extreme_by_building
            ORDER BY price {price_order}, deal_date DESC, building_name, address
            LIMIT 5
        """)
        items = [
            {
                "building_name": row["building_name"],
                "address": row["address"],
                "sgg_nm": row["sgg_nm"],
                "umd_nm": row["umd_nm"],
                "building_id": row["building_id"],
                "lat": float(row["lat"]) if row["lat"] is not None else None,
                "lng": float(row["lng"]) if row["lng"] is not None else None,
                "price": int(row["price"]),
                "deal_date": row["deal_date"],
            }
            for row in cur.fetchall()
        ]
        payload = {"ok": True, "order": order, "items": items}
        return payload if _as_payload else jsonify(payload)
    finally:
        cur.close()
        conn.close()


_matched_lodging_region_cache: dict = {}
_MATCHED_LODGING_REGION_CACHE_TTL = 300  # seconds; 전국 주소 매칭 재계산 방지


def _matched_lodging_by_region(*, exclude_general=False):
    """관리자 통계와 같은 주소 우선순위로 신고사업장을 지역·전국 집계에 연결한다.

    exclude_general=True는 하위호환 이름이며, 실제로는 객실수 대비 비율이
    유효한 생활숙박 유형만 남긴다.
    """
    if not exclude_general:
        master_payload = _master_stats_section("region_match")
        if master_payload is not None:
            return master_payload

    # [LEGACY] 지역별 주소 매칭 원본. 마스터 캐시 재생성 중에는 이 경로를
    # 강제로 다시 계산해 개별 5분 캐시의 오래된 값을 섞지 않는다.
    cache_key = bool(exclude_general)
    now = time.time()
    cached = _matched_lodging_region_cache.get(cache_key)
    if (
        not _master_stats_is_rebuilding()
        and cached
        and now - cached["ts"] < _MATCHED_LODGING_REGION_CACHE_TTL
    ):
        return cached["data"]

    conn = get_conn()
    cur = conn.cursor()
    try:
        lodging_filter = """
            WHERE lodging_type IS DISTINCT FROM 'mixed_use_excluded'
        """
        if exclude_general:
            lodging_filter += " AND lodging_type = ANY(%s)"
            lodging_params = [list(REPORT_RATE_ROOM_BASED_LODGING_TYPES)]
        else:
            lodging_params = []
        cur.execute(f"""
            SELECT id, sgg_text, road_address, jibun_address, lodging_type, units
            FROM master_buildings
            {lodging_filter}
        """, lodging_params)
        buildings = cur.fetchall()

        building_keys = []
        road_norms = set()
        jibun_norms = set()
        for building in buildings:
            road_key = addr_norm.normalize_road_prefix(building["road_address"])
            jibun_key = addr_norm.normalize_jibun_prefix(
                building["jibun_address"] or building["road_address"]
            )
            building_keys.append((building, road_key, jibun_key))
            if road_key:
                road_norms.add(road_key)
            if jibun_key:
                jibun_norms.add(jibun_key)

        road_matches = {}
        jibun_matches = {}
        if road_norms or jibun_norms:
            cur.execute("""
            SELECT permit_number, biz_name, permit_date, room_count, biz_status_name,
                   hygiene_type, road_norm, jibun_norm
                FROM lodging_registry
                WHERE road_norm = ANY(%s) OR jibun_norm = ANY(%s)
            """, [list(road_norms) or ["__none__"], list(jibun_norms) or ["__none__"]])
            for row in cur.fetchall():
                if row["road_norm"]:
                    road_matches.setdefault(row["road_norm"], {})[row["permit_number"]] = row
                if row["jibun_norm"]:
                    jibun_matches.setdefault(row["jibun_norm"], {})[row["permit_number"]] = row

        region_map = {}
        sido_map = {}
        all_permits = {}
        building_permits = {}
        for building, road_key, jibun_key in building_keys:
            region = (building["sgg_text"] or "").strip()
            matches = road_matches.get(road_key) if road_key else None
            if not matches:
                matches = jibun_matches.get(jibun_key) if jibun_key else None
            if not matches:
                continue
            building_permits[building["id"]] = matches
            for permit, lodging in matches.items():
                all_permits.setdefault(permit, lodging)
                if region:
                    sido = region.split(" ")[0]
                    region_permits = region_map.setdefault(region, {})
                    sido_permits = sido_map.setdefault(sido, {})
                    region_permits.setdefault(permit, lodging)
                    sido_permits.setdefault(permit, lodging)

        capped_report_rooms_by_building = _capped_active_report_rooms_by_building(
            buildings, road_matches, jibun_matches
        ) if exclude_general else {}
        result = (
            buildings, region_map, sido_map, all_permits,
            capped_report_rooms_by_building, building_permits,
        )
        _matched_lodging_region_cache[cache_key] = {"ts": now, "data": result}
        return result
    finally:
        cur.close()
        conn.close()


def _closure_rate_payload(region_match=None):
    """[LEGACY] 시군구별 매칭 숙박업체 폐업률 TOP5(표본 5건 이상)."""
    _, region_map, _, _, _, _ = region_match or _matched_lodging_by_region()
    items = []
    for region, permits in region_map.items():
        total_count = len(permits)
        if total_count < 5:
            continue
        closed_count = sum(
            1 for lodging in permits.values()
            if "폐업" in (lodging["biz_status_name"] or "")
        )
        items.append({
            "region": region,
            "total_count": total_count,
            "closed_count": closed_count,
            "closure_rate": round(closed_count / total_count * 100, 1),
        })
    items.sort(key=lambda item: (-item["closure_rate"], -item["total_count"], item["region"]))
    return {"ok": True, "items": items[:5], "minimum_sample_size": 5}


@app.route("/api/stats/closure-rate-by-region")
@limiter.limit("20 per minute")
def stats_closure_rate_by_region():
    master_payload = _master_stats_section("closure_stats")
    if master_payload is not None:
        return jsonify(master_payload)
    if _master_stats_cold_starting():
        return jsonify({
            "ok": False,
            "status": "warming",
            "items": [],
            "minimum_sample_size": 5,
        })
    return jsonify(_closure_rate_payload())


def _legacy_operator_consign_by_sido_payload(_as_payload=False):
    """[LEGACY-위탁가입업체] 플랫폼 가입 위탁업체 기반 집계 보존본.

    공개 데이터랩은 행안부 영업신고 기준으로 전환됐다. 이 구현은 과거 플랫폼
    가입·담당건물 기준을 비교하거나 필요 시 복구할 수 있도록 남겨 둔다.
    """
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT
                mb.id AS building_id,
                mb.sgg_text,
                COALESCE(mb.units, 0) AS units,
                approved.operator_id
            FROM master_buildings mb
            LEFT JOIN (
                SELECT DISTINCT ob.master_building_id, ob.operator_id
                FROM operator_buildings ob
                JOIN operators o ON o.id = ob.operator_id
                WHERE o.status = 'approved'
                  AND o.category = '위탁'
            ) approved ON approved.master_building_id = mb.id
            WHERE mb.lodging_type = '생활'
            ORDER BY mb.id
        """)
        # 업체가 여러 곳 연결된 건물도 호실수는 한 번만 세고,
        # 업체수만 승인 업체 ID 기준으로 중복 제거한다.
        buildings = {}
        for row in cur.fetchall():
            building_id = row["building_id"]
            building = buildings.setdefault(building_id, {
                "sido": _canonical_sido_name(row["sgg_text"]),
                "units": max(0, int(row["units"] or 0)),
                "operator_ids": set(),
            })
            if row["operator_id"] is not None:
                building["operator_ids"].add(int(row["operator_id"]))

        region_stats = {}
        for building in buildings.values():
            sido = building["sido"]
            if not sido:
                continue
            stats = region_stats.setdefault(sido, {
                "building_count": 0,
                "units": 0,
                "operator_ids": set(),
                "operator_units": 0,
            })
            stats["building_count"] += 1
            stats["units"] += building["units"]
            stats["operator_ids"].update(building["operator_ids"])
            if building["operator_ids"]:
                stats["operator_units"] += building["units"]

        def summary(stats):
            units = stats["units"]
            return {
                "building_count": stats["building_count"],
                "units": units,
                "operator_count": len(stats["operator_ids"]),
                "operator_units": stats["operator_units"],
                "operator_rate": (
                    round(stats["operator_units"] / units * 100, 1)
                    if units else None
                ),
            }

        items = [
            {"sido": sido, **summary(stats)}
            for sido, stats in sorted(region_stats.items())
        ]
        total_stats = {
            "building_count": sum(item["building_count"] for item in items),
            "units": sum(item["units"] for item in items),
            "operator_count": len({
                operator_id
                for stats in region_stats.values()
                for operator_id in stats["operator_ids"]
            }),
            "operator_units": sum(item["operator_units"] for item in items),
        }
        total = summary({
            **total_stats,
            "operator_ids": {
                operator_id
                for stats in region_stats.values()
                for operator_id in stats["operator_ids"]
            },
        })
        payload = {
            "ok": True,
            "items": items,
            "total": total,
            "is_partial": True,
        }
        return payload if _as_payload else jsonify(payload)
    finally:
        cur.close()
        conn.close()


def _report_rate_by_sido_payload():
    """생활숙박시설의 행안부 영업신고 현황을 시도별로 집계한다.

    건물 상세·관리자 통계와 같은 주소 매칭 규칙을 사용한다. 도로명 키에 신고가
    하나라도 있으면 그 결과만 쓰고, 없을 때에만 지번 키를 보조로 사용한다.
    """
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT id, sgg_text, COALESCE(units, 0) AS units,
                   road_address, jibun_address
            FROM master_buildings
            WHERE lodging_type IN ('생활', '생숙')
              AND NOT (
                  building_status IN ('허가', '착공')
                  AND use_apr_day IS NULL
              )
            ORDER BY id
        """)
        buildings = [dict(row) for row in cur.fetchall()]
        if not buildings:
            return {
                "ok": True,
                "items": [],
                "total": {
                    "building_cnt": 0,
                    "total_units": 0,
                    "active_biz_cnt": 0,
                    "active_room_cnt": 0,
                    "report_rate": None,
                },
                "is_partial": True,
            }

        road_keys, jibun_keys = set(), set()
        for building in buildings:
            road_key = addr_norm.normalize_road_prefix(building.get("road_address"))
            jibun_key = addr_norm.get_building_jibun_key(building)
            building["_road_key"] = road_key
            building["_jibun_key"] = jibun_key
            if road_key:
                road_keys.add(road_key)
            if jibun_key:
                jibun_keys.add(jibun_key)

        cur.execute("""
            SELECT permit_number, biz_name, permit_date, room_count, biz_status_name,
                   hygiene_type, road_norm, jibun_norm
            FROM lodging_registry
            WHERE road_norm = ANY(%s) OR jibun_norm = ANY(%s)
            ORDER BY source_updated_at DESC NULLS LAST, id DESC
        """, [list(road_keys) or ["__none__"], list(jibun_keys) or ["__none__"]])
        road_permits, jibun_permits = {}, {}
        for row in cur.fetchall():
            permit = dict(row)
            if permit.get("road_norm"):
                road_permits.setdefault(permit["road_norm"], {})[
                    permit["permit_number"]
                ] = permit
            if permit.get("jibun_norm"):
                jibun_permits.setdefault(permit["jibun_norm"], {})[
                    permit["permit_number"]
                ] = permit

        regions = {}
        # 전국 숙박통계의 생활 행과 동일하게 활성 생활숙박 신고만 집계하고,
        # 원본 간 동일 신고도 한 번만 센다. 주소 우선순위는 상태 적용 전에 정한다.
        assigned_permit_numbers = set()
        assigned_active_rows = []
        for building in buildings:
            sido = _canonical_sido_name(building.get("sgg_text"))
            if not sido:
                continue
            region = regions.setdefault(sido, {
                "building_cnt": 0,
                "total_units": 0,
                "active_permits": {},
                "building_ids": [],
            })
            region["building_cnt"] += 1
            region["total_units"] += max(0, int(building.get("units") or 0))
            region["building_ids"].append(building["id"])

            road_matches = road_permits.get(building.get("_road_key"), {})
            # 기존 건물 목록·상세와 동일하게 도로명 결과가 없을 때만 지번을 쓴다.
            matched_permits = road_matches or jibun_permits.get(
                building.get("_jibun_key"), {}
            )
            for permit_number, permit in matched_permits.items():
                if (
                    not permit_number
                    or not is_active_status(permit.get("biz_status_name"))
                    or lodging_type_for_hygiene(permit.get("hygiene_type")) != "생활"
                    or permit_number in assigned_permit_numbers
                ):
                    continue
                assigned_permit_numbers.add(permit_number)
                assigned = dict(permit)
                assigned["_sido"] = sido
                assigned_active_rows.append(assigned)

        deduplicated_active_rows = deduplicate_cross_source_lodgings(assigned_active_rows)
        for permit in deduplicated_active_rows:
            regions[permit["_sido"]]["active_permits"][permit["permit_number"]] = permit

        # 주소가 여러 건물에 매칭되는 신고는 대표 건물 한 곳에만 귀속하고,
        # 대표 건물 안에서도 마스터 호실수를 넘지 않게 캡처리한다.
        capped_active_rooms_by_building = _capped_active_report_rooms_by_building(
            buildings, road_permits, jibun_permits, expected_type="생활"
        )

        def summary(region):
            total_units = region["total_units"]
            active_permits = region["active_permits"]
            active_room_cnt = sum(
                capped_active_rooms_by_building.get(building_id, 0)
                for building_id in region["building_ids"]
            )
            return {
                "building_cnt": region["building_cnt"],
                "total_units": total_units,
                "active_biz_cnt": len(active_permits),
                "active_room_cnt": active_room_cnt,
                "report_rate": (
                    round(active_room_cnt * 100.0 / total_units, 1)
                    if total_units else None
                ),
            }

        items = [
            {"sido": sido, **summary(region)}
            for sido, region in sorted(regions.items())
        ]
        total_units = sum(item["total_units"] for item in items)
        active_room_cnt = sum(item["active_room_cnt"] for item in items)
        total = {
            "building_cnt": sum(item["building_cnt"] for item in items),
            "total_units": total_units,
            "active_biz_cnt": len(deduplicated_active_rows),
            "active_room_cnt": active_room_cnt,
            "report_rate": (
                round(active_room_cnt * 100.0 / total_units, 1)
                if total_units else None
            ),
        }
        return {"ok": True, "items": items, "total": total, "is_partial": True}
    finally:
        cur.close()
        conn.close()


@app.route("/api/stats/consign-by-sido")
@limiter.limit("20 per minute")
def stats_consign_by_sido(_as_payload=False):
    """생활숙박시설 영업신고 현황을 시도별로 반환한다."""
    master_payload = _master_stats_section("consign_stats")
    if master_payload is not None:
        return master_payload if _as_payload else jsonify(master_payload)

    if _master_stats_cold_starting():
        payload = {"ok": False, "status": "warming", "items": [], "total": {}}
        return payload if _as_payload else jsonify(payload)

    # [LEGACY] 원본 캐시 섹션 장애에도 같은 행안부 영업신고 기준으로 폴백한다.
    payload = _report_rate_by_sido_payload()
    return payload if _as_payload else jsonify(payload)


def _consign_by_sido_payload():
    """마스터 재계산용 생활숙박시설 영업신고 현황 원본 집계."""
    return _report_rate_by_sido_payload()


def _transaction_master_stats_payload():
    """가격변동·최고가·거래량 랭킹을 같은 재계산 시점에 묶는다.

    HTTP API의 rate limit은 외부 요청에만 적용해야 한다. 여기서는 데코레이터를
    우회해 순수 집계 경로의 dict를 얻고, 형식 검증은 공통 섹션 처리에서 한다.
    """
    price_handler = getattr(stats_price_change_top, "__wrapped__", stats_price_change_top)
    highest_handler = getattr(stats_highest_price_top, "__wrapped__", stats_highest_price_top)
    ranking_handler = getattr(get_ranking, "__wrapped__", get_ranking)
    price_change = {
        direction: price_handler(_direction=direction, _as_payload=True)
        for direction in ("up", "down")
    }
    highest_price = {
        order: highest_handler(_order=order, _as_payload=True)
        for order in ("highest", "lowest")
    }
    ranking = ranking_handler(_as_payload=True)
    return {
        "volume_top": ranking.get("most_traded") or [],
        "price_change": price_change,
        "highest_price": highest_price,
        "ranking": ranking,
    }


def _collection_stats_payload():
    """수집 작업의 마지막 갱신 상태를 원본 창고 카드용으로 읽는다."""
    key_map = {
        "lodging": "lodging_last_sync",
        "brhub": "brhub_progress",
    }
    conn = cur = None
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT key, value, updated_at::text AS updated_at FROM app_meta WHERE key = ANY(%s)",
            (list(key_map.values()),),
        )
        rows = {row["key"]: row for row in cur.fetchall()}
        result = {}
        for label, key in key_map.items():
            row = rows.get(key) or {}
            value = row.get("value")
            try:
                payload = json.loads(value) if value else {}
            except (TypeError, ValueError):
                payload = {}
            result[label] = {
                "updated_at": payload.get("finished_at") or payload.get("updated_at") or row.get("updated_at"),
                "completed": payload.get("completed"),
                "total": payload.get("total") or payload.get("found_total"),
            }
        return result
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def _master_stats_admin_snapshot(*, force=False):
    """관리자 원본 창고가 표시할 안전한 요약만 만든다."""
    cache = _rebuild_master_stats(force=force)
    now = time.time()
    refreshed_at = (
        datetime.fromtimestamp(cache["ts"]).strftime("%Y-%m-%d %H:%M:%S")
        if cache["ts"] else None
    )
    expires_in_seconds = max(
        0,
        int(_MASTER_STATS_CACHE_TTL - (now - cache["ts"])),
    ) if cache["ts"] else 0
    data = cache["data"]

    lodging_stats = data.get("lodging_stats", {})
    lodging_total = next(
        (row for row in (lodging_stats.get("rows") or []) if row.get("type") == "전체"),
        {},
    )
    lodging_total_building_cnt = lodging_stats.get("total_building_cnt")
    if lodging_total_building_cnt is None:
        lodging_total_building_cnt = lodging_total.get("building_count") or 0
    region_match = data.get("region_match")
    all_permits = region_match[3] if region_match else {}
    active_permits = [
        permit for permit in all_permits.values()
        if is_active_status(permit.get("biz_status_name"))
    ]
    consign_total = data.get("consign_stats", {}).get("total") or {}
    closure_items = data.get("closure_stats", {}).get("items") or []
    transaction_data = data.get("transaction_stats", {})
    collection_data = data.get("collection_stats", {})

    summaries = {
        "lodging_stats": (
            f"건물 {int(lodging_total_building_cnt):,}건 · "
            f"호실 {int(lodging_total.get('units') or 0):,}실"
        ),
        "region_match": (
            f"매칭 신고 {len(all_permits):,}건 · 영업중 {len(active_permits):,}건"
        ),
        "consign_stats": (
            f"신고업체 {int(consign_total.get('active_biz_cnt') or 0):,}곳 · "
            f"신고호실 {int(consign_total.get('active_room_cnt') or 0):,}실"
        ),
        "closure_stats": f"표본 충족 지역 {len(closure_items):,}곳",
        "transaction_stats": (
            f"거래량 TOP {len(transaction_data.get('volume_top') or []):,}건 · "
            f"가격변동 {len(transaction_data.get('price_change', {}).get('up', {}).get('items') or []):,}건"
        ),
        "collection_stats": (
            "숙박업 "
            f"{collection_data.get('lodging', {}).get('updated_at') or '-'} · "
            "건축HUB "
            f"{collection_data.get('brhub', {}).get('updated_at') or '-'}"
        ),
    }
    labels = {
        "lodging_stats": "숙박 통계",
        "region_match": "주소 매칭",
        "consign_stats": "영업신고 현황",
        "closure_stats": "폐업 현황",
        "transaction_stats": "거래 통계",
        "collection_stats": "수집 현황",
    }
    sections = [
        {
            "key": key,
            "label": labels[key],
            "status": cache["sections"].get(key, {}).get("status", "error"),
            "error": cache["sections"].get(key, {}).get("error"),
            "summary": summaries[key],
        }
        for key in labels
    ]
    return {
        "ok": True,
        "refreshed_at": refreshed_at,
        "expires_in_seconds": expires_in_seconds,
        "sections": sections,
    }


@app.route("/api/admin/stats/master", methods=["GET", "POST"])
@require_admin
@limiter.limit("2 per minute", methods=["POST"])
def admin_master_stats():
    """통계 원본 창고 상태 조회와 관리자 수동 새로고침."""
    return jsonify(_master_stats_admin_snapshot(force=request.method == "POST"))


@app.route("/api/admin/stats/refresh", methods=["POST"])
@require_admin
@limiter.limit("2 per minute")
def admin_stats_refresh():
    """관리자 요청으로 통합 통계 원본 캐시를 즉시 다시 만든다."""
    try:
        cache = _rebuild_master_stats(force=True)
    except Exception as exc:
        app.logger.exception("[master-stats] manual refresh failed")
        return jsonify({"ok": False, "message": f"통계 갱신에 실패했습니다: {exc}"}), 500

    section_keys = (
        "lodging_stats",
        "region_match",
        "consign_stats",
        "closure_stats",
        "transaction_stats",
    )
    sections = {
        key: cache["sections"].get(key, {}).get("status") == "ok"
        for key in section_keys
    }
    if not any(sections.values()):
        return jsonify({"ok": False, "message": "모든 통계 섹션 갱신에 실패했습니다."}), 500

    refreshed_at = (
        datetime.fromtimestamp(cache["ts"]).isoformat(timespec="seconds")
        if cache["ts"] else None
    )
    return jsonify({
        "ok": True,
        "refreshed_at": refreshed_at,
        "sections": sections,
    })


@app.route("/api/stats/registration-rate")
def stats_registration_rate():
    """전국 생활숙박 객실수 대비 신고율 — 다른 숙박 유형은 모두 제외.

    _row() 함수(건물마스터 상단 통계)와 동일한 소스·계산 방식 재사용:
    admin_buildings_full_stats 캐시가 유효하면 그 결과를 직접 사용하고,
    미스(초기 기동 직후)일 때만 road_norm 기준 SQL 폴백으로 근사치 반환.
    응답 필드명은 하위호환을 위해 biz_units로 유지.
    """
    master_payload = _master_stats_section("lodging_stats")
    if master_payload:
        total_row = next(
            (row for row in master_payload.get("rows") or [] if row.get("type") == "전체"),
            {},
        )
        legacy_rooms = int(total_row.get("report_rate_room_count") or 0)
        legacy_units = int(total_row.get("report_rate_units") or 0)
        return jsonify({
            "ok": True,
            "buildings": total_row.get("report_rate_building_count", 0),
            "total_units": legacy_units,
            "biz_units": legacy_rooms,
            "rate": round(legacy_rooms / legacy_units * 100, 1) if legacy_units else None,
            "general_excluded": True,
            "tourism_excluded": True,
            "non_living_excluded": True,
        })

    if _master_stats_cold_starting():
        return jsonify({
            "ok": False,
            "status": "warming",
            "buildings": 0,
            "total_units": 0,
            "biz_units": 0,
            "rate": None,
            "general_excluded": True,
            "tourism_excluded": True,
            "non_living_excluded": True,
        })

    # [LEGACY] 통합 원본의 숙박 섹션 자체가 실패했을 때만 기존 5분 캐시를
    # 사용한다. 통합 원본을 재생성할 때는 이 캐시도 먼저 비우므로, 외부
    # 무효화 표식 이전 값이 재사용되지는 않는다.
    global _bld_full_stats_cache
    cached = _bld_full_stats_cache.get("data")
    if cached and (time.time() - _bld_full_stats_cache["ts"] < _BLD_FULL_STATS_TTL):
        total_row = next((r for r in cached["rows"] if r["type"] == "전체"), {})
        legacy_rooms = int(total_row.get("report_rate_room_count") or 0)
        legacy_units = int(total_row.get("report_rate_units") or 0)
        return jsonify({
            "ok": True,
            "buildings": total_row.get("report_rate_building_count", 0),
            "total_units": legacy_units,
            "biz_units": legacy_rooms,
            "rate": round(legacy_rooms / legacy_units * 100, 1) if legacy_units else None,
            "general_excluded": True,
            "tourism_excluded": True,
            "non_living_excluded": True,
        })
    # 캐시 미스도 데이터랩·관리자 통계와 같은 주소 우선 매칭과 건물별 상한 규칙을
    # 사용한다. exclude_general의 하위호환 이름은 현재 생활 외 유형 전체 제외를 뜻한다.
    report_buildings, _, _, _, capped_rooms_by_building, _ = _matched_lodging_by_region(
        exclude_general=True
    )
    buildings = len(report_buildings)
    total_units = sum(int(building["units"] or 0) for building in report_buildings)
    biz_units = sum(capped_rooms_by_building.values())
    rate = round(biz_units / total_units * 100, 1) if total_units > 0 else None
    return jsonify({
        "ok": True,
        "buildings": buildings,
        "total_units": total_units,
        "biz_units": biz_units,
        "rate": rate,
        "general_excluded": True,
        "tourism_excluded": True,
        "non_living_excluded": True,
    })


@app.route("/api/stats/agent-count")
def stats_agent_count():
    """승인(approved)된 전속중개사 수 — 메인 좌측 패널 카드용 (하우스 계정 제외)."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*) AS c
        FROM agents
        WHERE status = 'approved'
          AND office_name <> '홈스퀘어부동산중개법인'
    """)
    n = cur.fetchone()["c"]
    cur.close()
    conn.close()
    return jsonify({"ok": True, "count": n})


@app.route("/api/stats/operator-counts")
def stats_operator_counts():
    """승인(approved)된 운영업체 수 — 메인 좌측 패널 카드용 그룹 집계.

    - consign(위탁정보): 위탁운영
    - housekeeping(운영지원): 청소 + 세탁 + 용품
    - finance(금융): loan_consultants 테이블(별도 엔티티) 기준
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT category, COUNT(*) AS c
        FROM operators
        WHERE status = 'approved'
        GROUP BY category
    """)
    by_cat = {r["category"]: r["c"] for r in cur.fetchall()}
    cur.execute("SELECT COUNT(*) AS c FROM loan_consultants WHERE status = 'approved'")
    loan_cnt = cur.fetchone()["c"]
    cur.close()
    conn.close()
    return jsonify({
        "ok": True,
        "consign": by_cat.get("위탁운영", 0),
        "housekeeping": by_cat.get("청소", 0) + by_cat.get("세탁", 0) + by_cat.get("용품", 0),
        "finance": loan_cnt,
    })


@app.route("/api/health")
def health():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM sync_log ORDER BY id DESC LIMIT 1")
    last = cur.fetchone()
    cur.execute("SELECT COUNT(*) c FROM transactions")
    total_tx = cur.fetchone()["c"]
    cur.close()
    conn.close()
    if not last:
        return jsonify({"status": "no sync yet", "total_transactions": total_tx})
    data = dict(last)
    # datetime은 그대로 jsonify하면 RFC 형식(Tue, 07 Jul...)이 되어 프론트 파싱과 어긋남 → ISO로 통일
    for k in ("started_at", "finished_at"):
        if data.get(k) is not None:
            data[k] = data[k].isoformat(timespec="minutes")
    data["total_transactions"] = total_tx
    return jsonify(data)


def _resume_interrupted_sync_jobs():
    """서버 재시작(Republish 등) 직후, 재시작 전에 'running' 상태로 남아
    있던 모든 데이터 동기화 작업을 자동으로 재개한다. 관리자가 일일이
    화면을 열어서 다시 누를 필요 없게 하기 위함. 각 스크립트는 자체
    체크포인트/일일캡 로직을 갖고 있어서, 더 할 게 없으면 스스로 조용히
    종료한다 — 여기서는 무조건 재기동만 시도하면 된다.
    gunicorn 멀티 워커 환경에서도 _start_detached_sync의 조건부 UPDATE(락)
    덕분에 한 워커만 실제로 기동하므로 안전하다."""
    jobs = [
        (_GEOCODE_META_KEY,       "geocode_buildings.py",    ["--status-key", _GEOCODE_META_KEY]),
        (_TITLE_INFO_META_KEY,    "backfill_title_info.py",  ["--status-key", _TITLE_INFO_META_KEY, "--sleep", "0.2"]),
        (_GEOCODE_BROKERS_META_KEY, "geocode_brokers.py",    ["--status-key", _GEOCODE_BROKERS_META_KEY]),
        (_SYNC_META_KEY,          "sync_runner.py",          []),
        (_BACKFILL_META_KEY,      "sync_runner.py",          ["--meta-key", _BACKFILL_META_KEY, "--months", "60", "--progress-key", "tx_backfill_progress"]),
        (_BROKER_SYNC_META_KEY,   "sync_brokers.py",         ["--status-key", _BROKER_SYNC_META_KEY]),
        (_LODGING_SYNC_META_KEY,  "sync_lodgings.py",        ["--include-camping", "--status-key", _LODGING_SYNC_META_KEY]),
        (_BRHUB_SYNC_META_KEY,    "sync_brhub.py",           ["--status-key", _BRHUB_SYNC_META_KEY]),
        (_PERMITS_SYNC_META_KEY,  "sync_permits.py",              ["--status-key", _PERMITS_SYNC_META_KEY]),
        (_REALTY_SYNC_META_KEY,   "sync_realty_stores.py",        ["--status-key", _REALTY_SYNC_META_KEY]),
        (_RECLASSIFY_META_KEY,    "reclassify_unclassified.py",   ["--status-key", _RECLASSIFY_META_KEY]),
    ]
    try:
        legacy_sync_control = lodging_promotion.get_legacy_lodging_sync_control()
    except Exception:
        legacy_sync_control = {"enabled": True}
    if legacy_sync_control.get("enabled") is False:
        jobs = [job for job in jobs if job[0] != _LODGING_SYNC_META_KEY]
    conn = get_conn()
    cur = conn.cursor()
    try:
        for meta_key, script_name, script_args in jobs:
            try:
                cur.execute("SELECT value FROM app_meta WHERE key=%s", (meta_key,))
                row = cur.fetchone()
                state = None
                if row and row["value"]:
                    try:
                        state = json.loads(row["value"]).get("state")
                    except (TypeError, ValueError):
                        state = None
                if state != "running":
                    continue  # 재시작 전에 실행 중이 아니었으면 스킵
                # 잠금 해제: "running" → "interrupted" 로 바꿔 _start_detached_sync가 진입할 수 있게 함
                cur.execute("""
                    UPDATE app_meta
                       SET value      = jsonb_set(value::jsonb, '{state}', '"interrupted"')::text,
                           updated_at = NOW()
                     WHERE key = %s
                """, (meta_key,))
                conn.commit()
                ok, code, payload = _start_detached_sync(meta_key, script_name, script_args)
                app.logger.info("[auto-resume] %s → %s (ok=%s)", meta_key, script_name, ok)
            except Exception:
                app.logger.exception("[auto-resume] %s 재개 시도 중 오류(무시)", meta_key)
    finally:
        cur.close()
        conn.close()


_resume_interrupted_sync_jobs()


def _resume_interrupted_scheduled_sync():
    """배포 중 끊긴 통합 배치를 단계 체크포인트에서 자동 재개한다."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT value FROM app_meta WHERE key=%s",
            (_SCHEDULED_SYNC_META_KEY,),
        )
        row = cur.fetchone()
    except Exception:
        app.logger.exception("[auto-resume] 통합 배치 상태 확인 실패")
        return
    finally:
        cur.close()
        conn.close()
    try:
        status = json.loads(row["value"]) if row and row["value"] else {}
    except (TypeError, ValueError):
        status = {}
    if status.get("state") != "running":
        return
    base_dir = os.path.dirname(os.path.abspath(__file__))
    try:
        proc = subprocess.Popen(
            [
                sys.executable,
                "-u",
                os.path.join(base_dir, "scheduled_sync.py"),
                "--status-key",
                _SCHEDULED_SYNC_META_KEY,
            ],
            cwd=base_dir,
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        threading.Thread(target=proc.wait, daemon=True).start()
        app.logger.info("[auto-resume] 정기 API 통합 배치 재개 시도")
    except Exception:
        app.logger.exception("[auto-resume] 정기 API 통합 배치 재개 실패")


_resume_interrupted_scheduled_sync()


# ---- 우편번호 백필 일일 자동 실행 (소량, 사람 개입 없이 서서히 완료) ----
_ZIP_BACKFILL_AUTO_KEY = "zip_backfill_auto"
_ZIP_BACKFILL_AUTO_CAP = 5000


def _zip_backfill_auto_loop():
    """앱 기동 후 30분마다 오늘 백필이 실행됐는지 확인, 안됐으면 5,000건 실행.
    연결 안 되는 날은 자연히 넘어가고, 되는 날은 채워지는 방식으로 며칠에 걸쳐 완료.
    멀티 워커(gunicorn)에서 첫 번째 워커만 실제 실행 — app_meta 원자 UPSERT로 중복 차단."""
    import time as _t
    _t.sleep(120)  # 부팅 완료 대기
    while True:
        try:
            today = datetime.utcnow().strftime("%Y-%m-%d")
            conn = get_conn()
            cur = conn.cursor()
            try:
                cur.execute("""
                    SELECT
                        (SELECT COUNT(*) FROM master_buildings
                         WHERE zip_code IS NULL AND road_address IS NOT NULL) AS remaining,
                        (SELECT value FROM app_meta WHERE key = %s) AS auto_meta
                """, (_ZIP_BACKFILL_AUTO_KEY,))
                row = cur.fetchone()
            finally:
                cur.close()
                conn.close()

            remaining = row["remaining"] if row else 0
            if remaining == 0:
                app.logger.info("[zip-auto] 우편번호 백필 완료 — 스레드 종료")
                return  # 전체 완료 → 스레드 종료

            last_date = None
            if row and row["auto_meta"]:
                try:
                    last_date = json.loads(row["auto_meta"]).get("date")
                except Exception:
                    pass

            if last_date != today:
                # 원자 UPSERT: 멀티 워커 중 오늘 날짜로 처음 쓰는 워커만 성공
                conn2 = get_conn()
                cur2 = conn2.cursor()
                try:
                    cur2.execute("""
                        INSERT INTO app_meta (key, value, updated_at)
                        VALUES (%s, %s::jsonb, NOW())
                        ON CONFLICT (key) DO UPDATE
                          SET value = EXCLUDED.value, updated_at = NOW()
                          WHERE (app_meta.value::jsonb ->> 'date') IS DISTINCT FROM %s
                    """, (_ZIP_BACKFILL_AUTO_KEY,
                          json.dumps({"date": today, "state": "started"}),
                          today))
                    acquired = cur2.rowcount > 0
                    conn2.commit()
                finally:
                    cur2.close()
                    conn2.close()

                if acquired:
                    base_dir = os.path.dirname(os.path.abspath(__file__))
                    try:
                        log_path = os.path.join(base_dir, "zip_backfill_auto.log")
                        log_f = open(log_path, "a")
                        subprocess.Popen(
                            [sys.executable, "-u",
                             os.path.join(base_dir, "zip_code_backfill.py"),
                             "--daily-cap", str(_ZIP_BACKFILL_AUTO_CAP),
                             "--sleep", "0.3"],
                            cwd=base_dir, start_new_session=True,
                            stdout=log_f, stderr=log_f,
                        )
                        app.logger.info("[zip-auto] 우편번호 백필 자동 실행 시작 (cap=%d, remaining=%d)",
                                       _ZIP_BACKFILL_AUTO_CAP, remaining)
                    except Exception:
                        app.logger.exception("[zip-auto] 백필 Popen 실패")
        except Exception:
            pass
        _t.sleep(1800)  # 30분마다 재확인


threading.Thread(target=_zip_backfill_auto_loop, daemon=True,
                 name="zip-backfill-auto").start()


# ── 이메일 광고배너 관리 (admin) ──────────────────────────────────────────────
@app.route("/api/admin/email-banners", methods=["GET"])
@require_admin
def admin_email_banners_list():
    conn = get_conn(); cur = conn.cursor()
    try:
        cur.execute("""SELECT id, image_url, link_url, start_date::text, end_date::text,
                              is_active, created_at::text
                       FROM email_ad_banners ORDER BY id DESC""")
        rows = [dict(r) for r in cur.fetchall()]
        return jsonify({"ok": True, "items": rows, "total": len(rows)})
    finally:
        cur.close(); conn.close()


@app.route("/api/admin/email-banners", methods=["POST"])
@require_admin
def admin_email_banners_create():
    data = request.get_json(force=True, silent=True) or {}
    image_url  = (data.get("image_url") or "").strip()
    link_url   = (data.get("link_url") or "").strip()
    start_date = data.get("start_date")
    end_date   = data.get("end_date")
    is_active  = bool(data.get("is_active", True))
    if not image_url or not link_url or not start_date or not end_date:
        return jsonify({"ok": False, "message": "image_url, link_url, start_date, end_date는 필수입니다."}), 400
    conn = get_conn(); cur = conn.cursor()
    try:
        cur.execute("""INSERT INTO email_ad_banners (image_url, link_url, start_date, end_date, is_active)
                       VALUES (%s, %s, %s, %s, %s) RETURNING id""",
                    (image_url, link_url, start_date, end_date, is_active))
        new_id = cur.fetchone()["id"]
        conn.commit()
        return jsonify({"ok": True, "id": new_id})
    except Exception as e:
        conn.rollback()
        return jsonify({"ok": False, "message": str(e)}), 400
    finally:
        cur.close(); conn.close()


@app.route("/api/admin/email-banners/<int:bid>", methods=["PUT", "PATCH"])
@require_admin
def admin_email_banners_update(bid):
    data = request.get_json(force=True, silent=True) or {}
    fields, vals = [], []
    for col in ("image_url", "link_url"):
        if col in data:
            fields.append(f"{col} = %s"); vals.append((data[col] or "").strip())
    for col in ("start_date", "end_date"):
        if col in data:
            fields.append(f"{col} = %s"); vals.append(data[col])
    if "is_active" in data:
        fields.append("is_active = %s"); vals.append(bool(data["is_active"]))
    if not fields:
        return jsonify({"ok": False, "message": "변경할 필드가 없습니다."}), 400
    vals.append(bid)
    conn = get_conn(); cur = conn.cursor()
    try:
        cur.execute(f"UPDATE email_ad_banners SET {', '.join(fields)} WHERE id = %s", vals)
        conn.commit()
        return jsonify({"ok": True})
    finally:
        cur.close(); conn.close()


@app.route("/api/admin/email-banners/<int:bid>", methods=["DELETE"])
@require_admin
def admin_email_banners_delete(bid):
    conn = get_conn(); cur = conn.cursor()
    try:
        cur.execute("DELETE FROM email_ad_banners WHERE id = %s", (bid,))
        conn.commit()
        return jsonify({"ok": True})
    finally:
        cur.close(); conn.close()


# ── 주간 이메일 기능 소개 관리 (admin) ────────────────────────────────────────
_FEATURE_TIP_TEXT_LIMITS = {
    "title": 160,
    "body": 4000,
    "cta_label": 80,
    "cta_url": 2000,
}


def _feature_tip_text(data, key, *, required=False):
    if key not in data:
        return None, None
    value = data.get(key)
    if not isinstance(value, str):
        return None, f"{key}은(는) 문자열이어야 합니다."
    value = value.strip()
    if (required or key in {"title", "body", "cta_label", "cta_url"}) and not value:
        return None, f"{key}은(는) 필수입니다."
    if len(value) > _FEATURE_TIP_TEXT_LIMITS[key]:
        return None, f"{key}은(는) {_FEATURE_TIP_TEXT_LIMITS[key]}자 이하여야 합니다."
    return value, None


def _feature_tip_url_is_safe(value):
    """이메일 CTA는 사이트 상대경로 또는 일반 HTTP(S) 주소만 허용한다."""
    if value.startswith("/"):
        return not value.startswith("//")
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _feature_tip_payload_from_request(data, *, creating=False):
    """관리자 입력을 검증하고 SQL 컬럼명만 포함한 변경값을 만든다."""
    if not isinstance(data, dict):
        return None, "요청 본문이 올바르지 않습니다."
    fields = {}
    if creating or "episode" in data:
        episode = data.get("episode")
        if isinstance(episode, bool) or not isinstance(episode, int) or not 1 <= episode <= 8:
            return None, "episode는 1~8 사이의 정수여야 합니다."
        fields["episode"] = episode

    for key in ("title", "body", "cta_label", "cta_url"):
        value, error = _feature_tip_text(data, key, required=creating and key != "cta_label")
        if error:
            return None, error
        if value is not None:
            fields[key] = value

    if creating and "cta_label" not in fields:
        fields["cta_label"] = "기능 자세히 보기"
    if "cta_url" in fields and not _feature_tip_url_is_safe(fields["cta_url"]):
        return None, "cta_url은 '/'로 시작하거나 http/https URL이어야 합니다."

    if "is_active" in data:
        if not isinstance(data["is_active"], bool):
            return None, "is_active는 true 또는 false여야 합니다."
        fields["is_active"] = data["is_active"]
    elif creating:
        fields["is_active"] = True

    if creating and not {"episode", "title", "body", "cta_url"} <= set(fields):
        return None, "episode, title, body, cta_url은 필수입니다."
    if not fields:
        return None, "변경할 필드가 없습니다."
    return fields, None


@app.route("/api/admin/feature-tips", methods=["GET"])
@require_admin
def admin_feature_tips_list():
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT id, episode, title, body, cta_label, cta_url, is_active,
                   created_at::text, updated_at::text
            FROM weekly_feature_tips
            ORDER BY episode ASC, id ASC
        """)
        rows = [dict(row) for row in cur.fetchall()]
        return jsonify({"ok": True, "items": rows, "total": len(rows)})
    finally:
        cur.close()
        conn.close()


@app.route("/api/admin/feature-tips", methods=["POST"])
@require_admin
def admin_feature_tips_create():
    fields, error = _feature_tip_payload_from_request(
        request.get_json(force=True, silent=True) or {}, creating=True
    )
    if error:
        return jsonify({"ok": False, "message": error}), 400

    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO weekly_feature_tips
                (episode, title, body, cta_label, cta_url, is_active)
            VALUES (%(episode)s, %(title)s, %(body)s, %(cta_label)s, %(cta_url)s, %(is_active)s)
            RETURNING id
        """, fields)
        new_id = cur.fetchone()["id"]
        conn.commit()
        return jsonify({"ok": True, "id": new_id}), 201
    except psycopg2_errors.UniqueViolation:
        conn.rollback()
        return jsonify({"ok": False, "message": "이미 등록된 회차입니다."}), 409
    finally:
        cur.close()
        conn.close()


@app.route("/api/admin/feature-tips/<int:tip_id>", methods=["PATCH"])
@require_admin
def admin_feature_tips_update(tip_id):
    fields, error = _feature_tip_payload_from_request(
        request.get_json(force=True, silent=True) or {}, creating=False
    )
    if error:
        return jsonify({"ok": False, "message": error}), 400

    assignments = [f"{column} = %({column})s" for column in fields]
    assignments.append("updated_at = NOW()")
    fields["tip_id"] = tip_id
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(f"""
            UPDATE weekly_feature_tips
            SET {", ".join(assignments)}
            WHERE id = %(tip_id)s
            RETURNING id
        """, fields)
        if not cur.fetchone():
            conn.rollback()
            return jsonify({"ok": False, "message": "기능 소개 회차를 찾을 수 없습니다."}), 404
        conn.commit()
        return jsonify({"ok": True})
    except psycopg2_errors.UniqueViolation:
        conn.rollback()
        return jsonify({"ok": False, "message": "이미 등록된 회차입니다."}), 409
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
