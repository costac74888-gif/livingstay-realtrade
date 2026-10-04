"""공매 공개 읽기 API 및 관리자 수집 실행. 외부 API는 이 요청 경로에서 호출하지 않는다."""
import json
import math
import os
import threading
import time
from datetime import datetime
from functools import wraps

from flask import jsonify, request, redirect, abort
from auction_domain import CURRENT_SQL, VISIBLE_SQL, EFFECTIVE_STATUS_SQL, ELIGIBLE_SQL, KST, safe_url, number
from db import get_conn

STATUS_KEY = "onbid_sync_status"
SUCCESS_KEY = "onbid_last_success_at"


def auction_deep_link(item_id, building_id=None):
    """기존 외부 링크와 새 목록·알림의 공통 지도 진입 주소."""
    from urllib.parse import urlencode
    params = {"building": building_id, "tab": "auction", "auction": item_id} if building_id else {"auction": item_id}
    return "/?" + urlencode(params)


def redirect_auction_to_map(item_id):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT a.master_building_id FROM auction_items a WHERE a.id=%s AND {ELIGIBLE_SQL}", [item_id])
            item = cur.fetchone()
    if not item:
        abort(404)
    return redirect(auction_deep_link(item_id, item["master_building_id"]), code=301)
PUBLIC_COLUMNS = f"""a.id,a.source,a.source_item_id,a.pbct_cdtn_no,a.sale_kind,a.usage_name,
a.lodging_category,a.title,a.unit_label,a.address_road,a.address_jibun,a.area_m2,
a.appraisal_price,a.min_bid_price,a.min_bid_ratio,a.round_no,a.failed_count,
a.bid_start_at,a.bid_end_at,({EFFECTIVE_STATUS_SQL}) AS status,a.status_changed_at,a.disposal_method,
a.notice_org,a.notice_no,a.detail_url,a.lat,a.lng,a.master_building_id,
a.first_seen_at,a.last_seen_at,a.updated_at,
a.raw->'list'->>'prptDivNm' AS property_type,
a.raw->'list'->>'cltrMngNo' AS management_no,
a.raw->'list'->>'landSqms' AS land_area_m2,
a.raw->'list'->>'bldSqms' AS building_area_m2"""
CARD_SELECT = f"""SELECT {PUBLIC_COLUMNS},
 {VISIBLE_SQL} AS is_visible,
 COALESCE((SELECT p.url FROM auction_photos p JOIN auction_items owner ON owner.id=p.auction_item_id
 WHERE owner.source=a.source AND owner.source_item_id=a.source_item_id
 ORDER BY (owner.id=a.id) DESC,owner.updated_at DESC,p.sort_order,p.id LIMIT 1),
 NULLIF(a.raw->'list'->>'thnlImgUrlAdr','')) AS thumbnail_url,
 'auction'::text AS photo_source"""
_cache, _cache_lock = {}, threading.Lock()
_scheduler_started = False


def serial(row):
    result = {k: v.isoformat() if isinstance(v, datetime) else v for k, v in dict(row).items()}
    for field in ("land_area_m2", "building_area_m2"):
        if field in result:
            result[field] = number(result[field])
    if "thumbnail_url" in result:
        result["thumbnail_url"] = safe_url(result["thumbnail_url"])
    return result


def public_cache(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        key = request.full_path
        with _cache_lock:
            entry = _cache.get(key)
        if entry and time.monotonic() - entry[0] < 60:
            return jsonify(entry[1])
        result = fn(*args, **kwargs)
        if isinstance(result, dict):
            with _cache_lock:
                if len(_cache) >= 128:
                    _cache.clear()
                _cache[key] = (time.monotonic(), result)
            return jsonify(result)
        return result
    return wrapped


def filters():
    where, params = ["TRUE"], []
    region = request.args.get("region", "").strip()[:100]
    if "\0" in region:
        raise ValueError("지역 입력을 확인해 주세요.")
    if region:
        where.append("(a.address_road LIKE %s OR a.address_jibun LIKE %s)")
        # LIKE 와일드카드를 사용자가 임의로 넣지 못하게 한다.
        pattern = region.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        params.extend((pattern, pattern))
    for key, column, choices in (
        ("category", "lodging_category", ("생활숙박", "호텔", "콘도", "모텔", "펜션", "기타")),
        ("kind", "sale_kind", ("압류", "국유", "이용기관", "신탁", "기타")),
        ("status", "status", ("scheduled", "bidding", "failed", "sold", "canceled", "closed")),
    ):
        value = request.args.get(key, "")
        if value:
            if value not in choices:
                raise ValueError("유효하지 않은 " + key)
            where.append(f"({EFFECTIVE_STATUS_SQL})=%s" if column == "status" else f"a.{column}=%s")
            params.append(value)
    for key, operator in (("ratio_min", ">="), ("ratio_max", "<=")):
        value = request.args.get(key)
        if value is not None and value != "":
            value = float(value)
            if not math.isfinite(value) or not 0 <= value <= 1000:
                raise ValueError("최저가율 범위를 확인해 주세요.")
            where.append(f"a.min_bid_ratio {operator} %s")
            params.append(value)
    minimum = request.args.get("failed_min")
    if minimum not in (None, ""):
        minimum = int(minimum)
        if not 0 <= minimum <= 1000:
            raise ValueError("유찰 횟수를 확인해 주세요.")
        where.append("a.failed_count >= %s")
        params.append(minimum)
    return " AND ".join(where), params


def building_photos(cur, building_id, photo_reader):
    """공개 직거래 사진만 합친다. 제한공개·철회 매물의 위치/사진 노출은 금지."""
    if not building_id:
        return []
    cur.execute("""
      SELECT p.id,p.image_key FROM listing_photos p
      JOIN listing_requests lr ON lr.id=p.listing_request_id
      WHERE lr.master_building_id=%s AND lr.deal_mode='direct'
        AND COALESCE(lr.disclosure_scope,'limited')='public'
        AND COALESCE(lr.status,'') NOT IN ('withdrawn','철회됨','보류')
        AND COALESCE(p.is_public,TRUE)
      ORDER BY lr.updated_at DESC NULLS LAST,p.sort_order,p.id LIMIT 30
    """, [building_id])
    photos = [
        {"id": "listing-" + str(r["id"]), "url": "/api/listing-photos/img/" + r["image_key"],
         "source": "listing", "sort_order": n}
        for n, r in enumerate(cur.fetchall())
    ]
    for photo in photo_reader(cur, building_id):
        # 기존 공개 사진 도우미는 키가 포함된 공급자 URL을 공개하지 않는다.
        photo = dict(photo)
        url = photo.get("url") or photo.get("photo_url")
        if isinstance(url, str) and (url.startswith("/") and not url.startswith("//") or safe_url(url)):
            source = photo.get("source")
            if source == "upload":
                source = "listing" if photo.get("listing_photo_id") else "operator"
            photos.append({"id": photo.get("id"), "url": url, "source": source,
                           "sort_order": photo.get("priority_rank") or 0})
    return photos


def cluster_counts(level):
    """기존 숙박 분모·색상은 유지하고 노출 공매를 독립 집계한다."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(CURRENT_SQL + """
              SELECT COALESCE(b.sgg_text,CONCAT_WS(' ',a.raw->'list'->>'lctnSdnm',
                           a.raw->'list'->>'lctnSggnm')) AS sgg_text,
                     COALESCE(b.umd_nm,a.raw->'list'->>'lctnEmdNm') AS umd_nm,COUNT(*) AS n
              FROM current_auctions a LEFT JOIN master_buildings b ON b.id=a.master_building_id
              GROUP BY 1,2
            """)
            rows = cur.fetchall()
    counts = {}
    for row in rows:
        sgg = row["sgg_text"] or ""
        key = cluster_key(
            sgg.split(" ")[0] if level == "sido" else (
            sgg if level == "sgg" else (sgg + " " + (row["umd_nm"] or "")).strip()
            ), level,
        )
        counts[key] = counts.get(key, 0) + int(row["n"])
    return counts


def cluster_key(name, level):
    from addr_norm import _normalize_region_prefix
    from address_utils import sido_core
    name = _normalize_region_prefix(name).strip()
    parts = name.split()
    if not parts:
        return ""
    return sido_core(parts[0]) if level == "sido" else " ".join([sido_core(parts[0]), *parts[1:]])


def enrich_cards(cur, items, photo_reader):
    for item in items:
        if item.get("master_building_id"):
            photos = building_photos(cur, item["master_building_id"], photo_reader)
            listing = next((p for p in photos if p.get("source") == "listing"), None)
            fallback = listing or (photos[0] if photos and not item.get("thumbnail_url") else None)
            if fallback:
                item["thumbnail_url"] = fallback["url"]
                item["photo_source"] = fallback.get("source")
    return items


def register_auction_routes(app, limiter, serve_html, require_admin, start_job, photo_reader, streetview_reader, user_loader):
    @app.get("/auctions")
    def auction_page():
        return serve_html("auctions.html")

    @app.get("/auctions/<int:item_id>")
    def auction_detail_page(item_id):
        return redirect_auction_to_map(item_id)

    @app.get("/api/auctions")
    @limiter.limit("60 per minute")
    @public_cache
    def auction_list():
        try:
            where, params = filters()
            page = int(request.args.get("page") or 1)
            if not 1 <= page <= 10000:
                raise ValueError("페이지를 확인해 주세요.")
            page_size = int(request.args.get("page_size") or 20)
            if page_size not in (10, 20, 50, 100):
                raise ValueError("페이지당 건수를 확인해 주세요.")
            order = {
                "deadline": "a.bid_end_at ASC NULLS LAST,a.id DESC",
                "deadline_desc": "a.bid_end_at DESC NULLS LAST,a.id DESC",
                "appraisal_asc": "a.appraisal_price ASC NULLS LAST,a.bid_end_at ASC NULLS LAST,a.id DESC",
                "appraisal_desc": "a.appraisal_price DESC NULLS LAST,a.bid_end_at ASC NULLS LAST,a.id DESC",
                "price_asc": "a.min_bid_price ASC NULLS LAST,a.bid_end_at ASC NULLS LAST,a.id DESC",
                "price_desc": "a.min_bid_price DESC NULLS LAST,a.bid_end_at ASC NULLS LAST,a.id DESC",
                "discount": "a.min_bid_ratio ASC NULLS LAST,a.bid_end_at ASC NULLS LAST,a.id DESC",
                "ratio_asc": "a.min_bid_ratio ASC NULLS LAST,a.bid_end_at ASC NULLS LAST,a.id DESC",
                "ratio_desc": "a.min_bid_ratio DESC NULLS LAST,a.bid_end_at ASC NULLS LAST,a.id DESC",
                "failed_asc": "a.failed_count ASC NULLS LAST,a.bid_end_at ASC NULLS LAST,a.id DESC",
                "failed_desc": "a.failed_count DESC NULLS LAST,a.bid_end_at ASC NULLS LAST,a.id DESC",
                "new": "a.first_seen_at DESC NULLS LAST,a.id DESC",
                "new_asc": "a.first_seen_at ASC NULLS LAST,a.id DESC",
                **{f"{key}_{direction}": f"{column} {direction.upper()} NULLS LAST,a.id DESC"
                   for key, column in (("status", "a.status"), ("category", "a.lodging_category"),
                                       ("address", "COALESCE(NULLIF(a.address_road,''),a.address_jibun)"),
                                       ("area", "a.area_m2"))
                   for direction in ("asc", "desc")},
            }.get(request.args.get("sort", "deadline"))
            if not order:
                raise ValueError("정렬을 확인해 주세요.")
        except (ValueError, TypeError):
            return jsonify({"ok": False, "message": "검색 조건을 확인해 주세요."}), 400
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(CURRENT_SQL + " SELECT COUNT(*) AS n FROM current_auctions a WHERE " + where, params)
                total = int(cur.fetchone()["n"])
                cur.execute(CURRENT_SQL + CARD_SELECT + " FROM current_auctions a WHERE " + where
                            + " ORDER BY " + order + " LIMIT %s OFFSET %s", params + [page_size, (page - 1) * page_size])
                items = [serial(r) for r in cur.fetchall()]
                cur.execute("SELECT value FROM app_meta WHERE key=%s", [SUCCESS_KEY])
                success = cur.fetchone()
                last_success_at = success["value"] if success else None
                if not last_success_at:
                    # 이전 버전도 전체 목록 완료 여부를 기록했다. 실패·미완료
                    # 실행은 사용하지 않으며, 상세 보강 실패는 목록 성공과 구분한다.
                    cur.execute("SELECT value FROM app_meta WHERE key=%s", [STATUS_KEY])
                    legacy = cur.fetchone()
                    try:
                        state = json.loads(legacy["value"]) if legacy else {}
                        if state.get("list_complete") is True and state.get("state") in ("done", "partial", "waiting_quota"):
                            timestamp = state.get("finished_at")
                            if timestamp:
                                datetime.fromisoformat(timestamp)
                                last_success_at = timestamp
                    except (ValueError, TypeError, AttributeError):
                        pass
        return {"ok": True, "items": items, "total": total, "page": page, "page_size": page_size,
                "pages": (total + page_size - 1) // page_size, "last_success_at": last_success_at}

    @app.get("/api/auctions/map")
    @limiter.limit("60 per minute")
    @public_cache
    def auction_map():
        try:
            vals = [float(v) for v in request.args.get("bbox", "").split(",")]
            if len(vals) != 4 or not all(math.isfinite(v) for v in vals):
                raise ValueError()
            west, south, east, north = vals
            if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
                raise ValueError()
        except ValueError:
            return jsonify({"ok": False, "message": "유효한 지도 영역이 필요합니다."}), 400
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(CURRENT_SQL + CARD_SELECT + """,
                  b.lodging_type AS building_lodging_type,b.building_status,b.building_name
                  FROM current_auctions a LEFT JOIN master_buildings b ON b.id=a.master_building_id
                  WHERE a.lng BETWEEN %s AND %s AND a.lat BETWEEN %s AND %s
                  ORDER BY a.bid_end_at ASC NULLS LAST,a.id DESC LIMIT 501
                """, [west, east, south, north])
                rows = cur.fetchall()
        return {"ok": True, "items": [serial(r) for r in rows[:500]], "truncated": len(rows) > 500}

    @app.get("/api/building/<int:building_id>/auctions")
    @limiter.limit("60 per minute")
    @public_cache
    def building_auctions(building_id):
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM master_buildings WHERE id=%s", [building_id])
                if not cur.fetchone():
                    return jsonify({"ok": False, "message": "건물을 찾을 수 없습니다."}), 404
                cur.execute(CARD_SELECT + f""" FROM auction_items a WHERE a.master_building_id=%s AND {ELIGIBLE_SQL}
                  ORDER BY a.bid_start_at DESC NULLS LAST,a.id DESC LIMIT 200""", [building_id])
                items = [serial(r) for r in cur.fetchall()]
                cur.execute(f"""SELECT p.id,p.url,'auction'::text AS source,p.sort_order FROM auction_photos p
                  JOIN auction_items a ON a.id=p.auction_item_id WHERE a.master_building_id=%s AND {ELIGIBLE_SQL}
                  ORDER BY a.updated_at DESC,p.sort_order LIMIT 60""", [building_id])
                photos = [serial(r) for r in cur.fetchall()]
                photos = building_photos(cur, building_id, photo_reader) + photos
        active = {r["source_item_id"] for r in items if r["is_visible"]}
        return {"ok": True, "items": items, "active_count": len(active), "photos": photos}

    @app.get("/api/auctions/<int:item_id>")
    @limiter.limit("60 per minute")
    @public_cache
    def auction_detail(item_id):
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(CARD_SELECT + f" FROM auction_items a WHERE a.id=%s AND {ELIGIBLE_SQL}", [item_id])
                row = cur.fetchone()
                if not row:
                    return jsonify({"ok": False, "message": "공매 정보를 찾을 수 없습니다."}), 404
                item = serial(row)
                cur.execute("""SELECT round_no,bid_start_at,bid_end_at,min_bid_price,result,result_at,
                  source_round_key='current' AS is_current,source_round_key LIKE 'next:%%' AS is_upcoming
                  FROM auction_rounds WHERE auction_item_id=%s
                  ORDER BY COALESCE(bid_start_at,result_at) ASC NULLS LAST,round_no""", [item_id])
                rounds = [serial(r) for r in cur.fetchall()]
                if not rounds:
                    # 같은 물건의 먼저 검증한 회차 이력은 재사용하되 현재 금액·일정은
                    # 반드시 선택한 회차의 목록 원장에서 가져온다.
                    cur.execute("""SELECT r.round_no,r.bid_start_at,r.bid_end_at,r.min_bid_price,r.result,r.result_at,
                      FALSE AS is_current,r.source_round_key LIKE 'next:%%' AS is_upcoming
                      FROM auction_rounds r WHERE r.auction_item_id=(
                        SELECT owner.id FROM auction_items owner
                        WHERE owner.source=%s AND owner.source_item_id=%s AND owner.detail_fingerprint IS NOT NULL
                        ORDER BY owner.updated_at DESC LIMIT 1
                      ) AND r.source_round_key<>'current'
                      ORDER BY COALESCE(r.bid_start_at,r.result_at) ASC NULLS LAST,r.round_no""",
                                [item["source"], item["source_item_id"]])
                    rounds = [serial(r) for r in cur.fetchall() if not (
                        r["round_no"] == item["round_no"] and r["bid_start_at"] and
                        r["bid_start_at"].isoformat() == item["bid_start_at"]
                    )]
                    rounds.append({
                        "round_no": item["round_no"], "bid_start_at": item["bid_start_at"],
                        "bid_end_at": item["bid_end_at"], "min_bid_price": item["min_bid_price"],
                        "result": {"scheduled": "예정", "bidding": "입찰중", "sold": "낙찰",
                                   "failed": "유찰", "canceled": "취소"}.get(item["status"], "결과 확인 중"),
                        "result_at": None, "is_current": True, "is_upcoming": False,
                    })
                    rounds.sort(key=lambda r: r["bid_start_at"] or r["result_at"] or "9999")
                cur.execute("""SELECT p.id,p.url,'auction'::text AS source,p.sort_order FROM auction_photos p
                  JOIN auction_items owner ON owner.id=p.auction_item_id
                  WHERE owner.source=%s AND owner.source_item_id=%s
                  ORDER BY (owner.id=%s) DESC,owner.updated_at DESC,p.sort_order,p.id""",
                            [item["source"], item["source_item_id"], item_id])
                auction_photos = [serial(r) for r in cur.fetchall()]
                building, photos = None, auction_photos
                if item["master_building_id"]:
                    cur.execute("""SELECT id,building_name,road_address,jibun_address,sgg_cd,umd_nm,jibun,lat,lng
                      FROM master_buildings WHERE id=%s""", [item["master_building_id"]])
                    b = cur.fetchone()
                    building = serial(b) if b else None
                    existing = building_photos(cur, item["master_building_id"], photo_reader)
                    photos = [p for p in existing if p.get("source") == "listing"] + auction_photos + [
                        p for p in existing if p.get("source") != "listing"
                    ]
                    if building and not photos:
                        photos += streetview_reader(building)
                # 동일 URL은 출처 우선순위가 높은 한 장만 표시.
                unique = {}
                for photo in photos:
                    unique.setdefault(photo["url"], photo)
        return {"ok": True, "item": item, "rounds": rounds, "photos": list(unique.values()), "building": building}

    @app.get("/api/admin/onbid-status")
    @require_admin
    @limiter.limit("30 per minute")
    def auction_admin_status():
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT value FROM app_meta WHERE key=%s", [STATUS_KEY])
                r = cur.fetchone()
                state = json.loads(r["value"]) if r else {"state": "not_started"}
                cur.execute("SELECT COUNT(DISTINCT (source,source_item_id)) AS n FROM auction_items")
                total = int(cur.fetchone()["n"])
                cur.execute(CURRENT_SQL + " SELECT COUNT(*) AS n FROM current_auctions")
                active = int(cur.fetchone()["n"])
        return jsonify({"ok": True, "status": state, "total_items": total, "active_items": active})

    @app.route("/api/building/<int:building_id>/auction-watch", methods=["GET", "POST", "DELETE"])
    @limiter.limit("20 per minute")
    def auction_watch(building_id):
        user = user_loader()
        if not user:
            return jsonify({"ok": False, "message": "로그인이 필요합니다."}), 401
        if request.headers.get("Sec-Fetch-Site") == "cross-site":
            return jsonify({"ok": False, "message": "허용되지 않은 요청입니다."}), 403
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM master_buildings WHERE id=%s", [building_id])
                if not cur.fetchone():
                    return jsonify({"ok": False, "message": "건물을 찾을 수 없습니다."}), 404
                if request.method == "POST":
                    cur.execute("""INSERT INTO auction_watches(user_id,master_building_id) VALUES(%s,%s)
                      ON CONFLICT(user_id,master_building_id) DO UPDATE SET enabled=TRUE""",
                                [user["id"], building_id])
                elif request.method == "DELETE":
                    cur.execute("DELETE FROM auction_watches WHERE user_id=%s AND master_building_id=%s",
                                [user["id"], building_id])
                cur.execute("SELECT enabled FROM auction_watches WHERE user_id=%s AND master_building_id=%s",
                            [user["id"], building_id])
                row = cur.fetchone()
        return jsonify({"ok": True, "enabled": bool(row and row["enabled"]), "channel": "in_app"})

    @app.post("/api/admin/sync-onbid")
    @require_admin
    @limiter.limit("3 per minute")
    def auction_admin_run():
        if request.headers.get("Sec-Fetch-Site") == "cross-site":
            return jsonify({"ok": False, "message": "허용되지 않은 요청입니다."}), 403
        if not os.environ.get("DATA_GO_KR_BROKER_API_KEY"):
            return jsonify({"ok": False, "message": "공공데이터포털 인증키가 등록되지 않았습니다."}), 503
        ok, code, payload = start_job(
            STATUS_KEY, "sync_onbid.py",
            ["--status-key", STATUS_KEY, "--run-id", "__RUN_ID__"],
        )
        if ok:
            payload["message"] = "온비드 공매 수집을 시작했습니다."
        return jsonify(payload), code


def start_onbid_scheduler(start_job, logger):
    """워커에서는 짧은 스케줄 판정만 수행. API 수집은 detached child에서 실행."""
    global _scheduler_started
    if _scheduler_started or os.environ.get("REPLIT_DEPLOYMENT") != "1":
        return
    _scheduler_started = True

    def loop():
        while True:
            try:
                now = datetime.now(KST)
                if (now.hour, now.minute) >= (6, 10):
                    key = "onbid_daily:" + now.date().isoformat()
                    with get_conn() as conn:
                        with conn.cursor() as cur:
                            cur.execute("SELECT value FROM app_meta WHERE key=%s", [key])
                            done = cur.fetchone()
                    if not done:
                        ok, _, _ = start_job(STATUS_KEY, "sync_onbid.py", [
                            "--status-key", STATUS_KEY, "--run-id", "__RUN_ID__",
                        ])
                        if ok:
                            with get_conn() as conn:
                                with conn.cursor() as cur:
                                    cur.execute("""INSERT INTO app_meta(key,value,updated_at) VALUES(%s,'started',NOW())
                                      ON CONFLICT(key) DO NOTHING""", [key])
            except Exception as exc:
                logger.warning("온비드 스케줄 확인 실패: %s", type(exc).__name__)
            time.sleep(60)
    threading.Thread(target=loop, daemon=True, name="onbid-schedule").start()