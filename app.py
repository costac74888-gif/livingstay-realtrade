# -*- coding: utf-8 -*-
"""
app.py — 검색 API + 정적 페이지 서빙 (Replit에서 바로 실행)

엔드포인트
------------------------------------------------------------
GET /                          → static/index.html 서빙
GET /api/transactions          → 게시판(전체 최신순) or 검색 결과
    쿼리파라미터:
      q       : 건물명 또는 주소 검색어 (부분일치, 보조 수단)
      si_do   : 시/도 (예: '경기도') — 행정접미사 떼고 코어 이름으로 비교
                ('서울'과 '서울특별시'가 동일하게 취급됨)
      sgg_nm  : 시/군/구 (예: '수원시') — 정확히 일치
      umd_nm  : 읍/면/동 (예: '매산로1가') — 정확히 일치
      year    : 계약연도 (예: '2026', 'all'이면 전체)
      page/size
GET /api/regions               → 계층형 지역 트리 (시도 > 시군구 > 읍면동, 각 count)
GET /api/health                → 배치 마지막 실행 시각/건수 확인용
"""

import os
import time
from urllib.parse import quote
from flask import Flask, request, jsonify, send_from_directory, Response
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from datetime import datetime
from db import get_conn, init_db
from address_utils import normalize_umd_nm, sido_core, sido_match_clause

# 서버 기동 시각 — 정적 SDK URL 캐시 무효화용 (기동할 때만 바뀜)
SERVER_BOOT_V = str(int(time.time()))

app = Flask(__name__, static_folder="static")


def get_client_ip():
    """
    rate limiter가 IP별로 카운터를 나누는 기준 IP를 돌려준다.

    리플릿은 앱 앞에 여러 프록시 홉이 있고(확인된 체인 예:
    '<client>, 10.x, 10.x, 127.0.0.1'), 엣지 프록시가 클라이언트가 보낸
    X-Forwarded-For를 무시하고 새로 세팅한다(위조 XFF가 제거되는 것 확인함).
    따라서 XFF 맨 앞(최초) 항목이 실제 방문자 IP다.
    remote_addr(=마지막 홉 127.0.0.1)을 키로 쓰면 모든 사용자가 한 카운터를
    공유하게 되므로 절대 쓰면 안 된다.
    """
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()
    return get_remote_address()


# 메모리 기반 rate limiter (별도 인프라 불필요).
# 기본값은 걸지 않고, 쓰기성 API에만 데코레이터로 개별 제한을 건다.
limiter = Limiter(
    key_func=get_client_ip,
    app=app,
    storage_uri="memory://",
)


@app.errorhandler(429)
def ratelimit_handler(e):
    return (
        jsonify({"message": "너무 많은 요청입니다. 잠시 후 다시 시도해주세요."}),
        429,
    )

# 앱 부팅 시 스키마를 보장한다 (building_requests 정정 컬럼 등).
# init_db는 CREATE/ALTER ... IF NOT EXISTS라 여러 번 호출해도 안전(멱등).
# 이렇게 해야 배포 직후(아직 sync 스크립트가 안 돈 시점)에도 요청 API가 500 없이 동작한다.
init_db()


@app.route("/")
def index():
    # 정적 index.html을 읽어 카카오맵 JS 키만 서버에서 주입해 서빙한다.
    # (프론트 소스에 키를 직접 박지 않고, 환경변수/시크릿에서 안전하게 넣는다.)
    kakao_js_key = os.environ.get("KAKAO_JS_KEY", "")
    html_path = os.path.join(app.static_folder, "index.html")
    with open(html_path, encoding="utf-8") as f:
        html = f.read()
    html = html.replace("{{KAKAO_JS_KEY}}", quote(kakao_js_key, safe=""))
    html = html.replace("{{KAKAO_SDK_V}}", SERVER_BOOT_V)
    resp = Response(html, mimetype="text/html")
    # 진입 HTML은 캐시하지 않아 항상 최신 SDK URL(_v)을 받도록 한다.
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp


@app.route("/api/transactions")
def get_transactions():
    q = request.args.get("q", "").strip()
    si_do = request.args.get("si_do", "").strip()
    sgg_nm = request.args.get("sgg_nm", "").strip()
    umd_nm = request.args.get("umd_nm", "").strip()
    year = request.args.get("year", "").strip()
    lodging_type = request.args.get("lodging_type", "").strip()
    page = max(int(request.args.get("page", 1)), 1)
    size = min(int(request.args.get("size", 20)), 200)
    offset = (page - 1) * size

    where = ["1=1"]
    params = []

    if q:
        where.append("(building_name ILIKE %s OR address ILIKE %s)")
        params += [f"%{q}%", f"%{q}%"]
    if si_do:
        # '서울' vs '서울특별시' 표기 편차 흡수 — 지도와 동일한 코어 이름 비교 규칙 사용
        where.append(sido_match_clause("si_do"))
        params.append(sido_core(si_do))
    if sgg_nm:
        where.append("sgg_nm = %s")
        params.append(sgg_nm)
    if umd_nm:
        where.append("umd_nm = %s")
        params.append(umd_nm)
    if year and year != "all":
        where.append("deal_date LIKE %s")
        params.append(f"{year}-%")
    if lodging_type == "복합":
        # '호텔·콘도'처럼 여러 용도가 병기된 건물만 (백엔드가 LIKE '%·%'로 처리)
        where.append("lodging_type LIKE %s")
        params.append("%·%")
    elif lodging_type:
        where.append("lodging_type = %s")
        params.append(lodging_type)

    where_sql = " AND ".join(where)

    conn = get_conn()
    cur = conn.cursor()

    cur.execute(f"SELECT COUNT(*) c FROM transactions WHERE {where_sql}", params)
    total = cur.fetchone()["c"]

    cur.execute(f"""
        SELECT building_name, address, si_do, sgg_nm, umd_nm, jibun, sgg_cd,
               area, price, deal_date, deal_type, floor,
               lodging_type, lodging_type_detail, match_source
        FROM transactions
        WHERE {where_sql}
        ORDER BY deal_date DESC, id DESC
        LIMIT %s OFFSET %s
    """, params + [size, offset])
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()

    return jsonify({"total": total, "page": page, "size": size, "items": rows})


@app.route("/api/buildings-geo")
def get_buildings_geo():
    """지도 마커용 — 좌표(lat/lng)가 있는 마스터 건물.

    선택적 필터(지역/건물명/용도)를 /api/transactions와 동일한 파라미터
    이름으로 지원한다. 단, 기간(year)은 건물 위치와 무관하므로 지도에는
    적용하지 않는다(게시판 전용).

    master_buildings에는 si_do/sgg_nm 컬럼이 없고 sgg_text('서울특별시 서초구')
    와 umd_nm만 있으므로:
      - si_do  : 표기 편차('서울' vs '서울특별시')로 인한 누락을 막기 위해
                 양쪽 모두 행정접미사를 떼어낸 코어 이름으로 정확 비교
      - sgg_nm : sgg_text 포함 매칭
      - umd_nm : 공백 유무 차이('손양면 동호리' vs '손양면동호리')를 흡수하기
                 위해 공백 제거 후 포함 매칭
    """
    q = request.args.get("q", "").strip()
    si_do = request.args.get("si_do", "").strip()
    sgg_nm = request.args.get("sgg_nm", "").strip()
    umd_nm = request.args.get("umd_nm", "").strip()
    lodging_type = request.args.get("lodging_type", "").strip()

    where = ["lat IS NOT NULL", "lng IS NOT NULL"]
    params = []

    if q:
        where.append("(building_name ILIKE %s OR road_address ILIKE %s OR jibun_address ILIKE %s)")
        params += [f"%{q}%", f"%{q}%", f"%{q}%"]
    if si_do:
        # '서울' vs '서울특별시' 표기 편차 흡수 — 게시판과 동일한 코어 이름 비교 규칙 사용.
        # sgg_text('서울특별시 서초구')의 첫 토큰을 정규화해 비교한다.
        where.append(sido_match_clause("split_part(sgg_text, ' ', 1)"))
        params.append(sido_core(si_do))
    if sgg_nm:
        where.append("sgg_text LIKE %s")
        params.append(f"%{sgg_nm}%")
    if umd_nm:
        where.append("REPLACE(umd_nm, ' ', '') ILIKE %s")
        params.append(f"%{umd_nm.replace(' ', '')}%")
    if lodging_type == "복합":
        where.append("lodging_type LIKE %s")
        params.append("%·%")
    elif lodging_type:
        where.append("lodging_type = %s")
        params.append(lodging_type)

    where_sql = " AND ".join(where)

    conn = get_conn()
    cur = conn.cursor()
    # 각 건물의 '가장 최근 실거래가'를 건물명 기준으로 1건만 붙인다.
    # N+1 방지를 위해 LEFT JOIN LATERAL로 건물당 최신 1행만 조회하고,
    # 실거래 이력이 없으면 latest_price/latest_deal_date가 NULL로 반환된다.
    cur.execute(f"""
        SELECT mb.id, mb.building_name, mb.lat, mb.lng, mb.lodging_type,
               lt.price AS latest_price, lt.deal_date AS latest_deal_date,
               lt.floor AS latest_floor, lt.area AS latest_area,
               lt.deal_type AS latest_deal_type
        FROM master_buildings mb
        LEFT JOIN LATERAL (
            SELECT t.price, t.deal_date, t.floor, t.area, t.deal_type
            FROM transactions t
            WHERE t.building_name = mb.building_name
            ORDER BY t.deal_date DESC
            LIMIT 1
        ) lt ON TRUE
        WHERE {where_sql}
        ORDER BY mb.id
    """, params)
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return jsonify({"total": len(rows), "items": rows})


@app.route("/api/monthly-trend")
def get_monthly_trend():
    """
    최근 12개월 월별 실거래 집계 (좌측 패널 '실거래추세' 콤보차트용).
    - count     : 월별 거래건수 (막대)
    - sum_price : 월별 거래금액 합계, 만원 단위 (선)
    데이터가 없는 달은 0으로 채워 항상 12개 버킷을 반환한다.
    """
    now = datetime.now()
    # 이번 달부터 11개월 전까지 12개 버킷(YYYY-MM) 생성
    months = []
    y, m = now.year, now.month
    for _ in range(12):
        months.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    months.reverse()  # 과거 → 최근 순
    start_ym = months[0]

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT substring(deal_date, 1, 7) AS ym,
               COUNT(*) AS cnt,
               COALESCE(SUM(price), 0) AS sum_price
        FROM transactions
        WHERE deal_date IS NOT NULL
          AND substring(deal_date, 1, 7) >= %s
        GROUP BY ym
    """, [start_ym])
    agg = {r["ym"]: {"cnt": r["cnt"], "sum_price": int(r["sum_price"] or 0)} for r in cur.fetchall()}
    cur.close()
    conn.close()

    items = [{
        "ym": ym,
        "count": agg.get(ym, {}).get("cnt", 0),
        "sum_price": agg.get(ym, {}).get("sum_price", 0),
    } for ym in months]

    return jsonify({"items": items})


@app.route("/api/regions")
def get_regions():
    """시도 > 시군구 > 읍면동 계층 트리 (계층 검색 드롭다운용)"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT si_do, sgg_nm, umd_nm, COUNT(*) c
        FROM transactions
        WHERE si_do IS NOT NULL
        GROUP BY si_do, sgg_nm, umd_nm
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    tree = {}
    for r in rows:
        sd, sg, um, c = r["si_do"], r["sgg_nm"], r["umd_nm"], r["c"]
        tree.setdefault(sd, {"count": 0, "sgg": {}})
        tree[sd]["count"] += c
        tree[sd]["sgg"].setdefault(sg, {"count": 0, "umd": {}})
        tree[sd]["sgg"][sg]["count"] += c
        tree[sd]["sgg"][sg]["umd"][um] = tree[sd]["sgg"][sg]["umd"].get(um, 0) + c

    return jsonify(tree)


@app.route("/api/years")
def get_years():
    """
    실거래 연도 목록 (기간 필터 드롭다운용).
    - 실제 데이터에 존재하는 연도만 노출 (데이터 없는 연도는 드롭다운에서 제외)
    - 데이터가 하나도 없으면 현재 연도만 표시
    - 새 연도 데이터가 들어오면 자동으로 목록에 추가됨 (하드코딩 아님)
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT LEFT(deal_date, 4) y FROM transactions WHERE deal_date IS NOT NULL")
    data_years = {r["y"] for r in cur.fetchall() if r["y"]}
    cur.close()
    conn.close()

    current_year = datetime.now().year
    years = sorted(data_years, reverse=True) if data_years else [str(current_year)]

    return jsonify({"years": years, "current_year": str(current_year)})


@app.route("/api/favorites")
def get_favorites():
    """
    관심단지 전용 조회 — /api/transactions의 size 상한(200)과 무관하게
    저장된 관심단지 키(building_name|address) 전체를 한 번에 정확히 조회한다.
    쿼리파라미터: keys = "건물명|주소" 쌍을 쉼표(,)로 연결
    """
    raw_keys = request.args.get("keys", "").strip()
    if not raw_keys:
        return jsonify({"items": [], "total": 0})

    pairs = []
    for token in raw_keys.split(","):
        if "|" not in token:
            continue
        name, addr = token.split("|", 1)
        pairs.append((name, addr))

    if not pairs:
        return jsonify({"items": [], "total": 0})

    conn = get_conn()
    cur = conn.cursor()
    # 미매칭 거래는 building_name이 NULL이고, 프론트 favKey는 이를 문자열 "null"로 저장한다.
    # SQL에서 = 'null'은 실제 NULL과 매칭되지 않으므로 그런 항목은 IS NULL로 조회한다.
    conditions = []
    params = []
    for name, addr in pairs:
        if name in ("null", "undefined", ""):
            conditions.append("(building_name IS NULL AND address = %s)")
            params.append(addr)
        else:
            conditions.append("(building_name = %s AND address = %s)")
            params.extend([name, addr])
    conditions = " OR ".join(conditions)
    cur.execute(f"""
        SELECT building_name, address, si_do, sgg_nm, umd_nm, jibun, sgg_cd,
               area, price, deal_date, deal_type, floor,
               lodging_type, lodging_type_detail, match_source
        FROM transactions
        WHERE {conditions}
        ORDER BY deal_date DESC, id DESC
    """, params)
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return jsonify({"items": rows, "total": len(rows)})


@app.route("/api/submit-building", methods=["POST"])
@limiter.limit("3 per minute; 10 per hour")
def submit_building():
    """
    사용자가 "내 건물이 목록에 없다"며 도로명주소를 제출하면:
      1) building_requests에 요청 기록
      2) 도로명→지번 변환(JUSO) → building_registry.classify_lodging_type()로 실시간 재검증
      3) 사용자가 고른 용도(suggested)는 참고용으로만 기록하고, 실제 반영은 검증 결과만 사용.
         검증 통과 시에만 master_buildings(신마스터)에 편입(source='user_submitted').
         판정 불가 시 사유와 함께 거절 (요청 기록에 남김)
    """
    from address_utils import road_to_jibun, BjdongMap, parse_jibun
    from building_registry import classify_lodging_type
    import os as _os

    data = request.get_json(force=True) or {}
    road_address = (data.get("road_address") or "").strip()
    building_name_hint = (data.get("building_name_hint") or "").strip()
    suggested_lodging_type = (data.get("suggested_lodging_type") or "").strip()  # 참고용, 신뢰 안 함
    requester_note = (data.get("requester_note") or "").strip()

    if not road_address:
        return jsonify({"status": "error", "message": "주소를 입력해주세요."}), 400

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO building_requests (request_type, road_address, building_name_hint, suggested_lodging_type, requester_note)
        VALUES ('new', %s, %s, %s, %s) RETURNING id
    """, (road_address, building_name_hint, suggested_lodging_type, requester_note))
    request_id = cur.fetchone()["id"]
    conn.commit()

    def fail(reason, http_code=200):
        cur.execute("""
            UPDATE building_requests SET status='rejected', reject_reason=%s, processed_at=NOW()
            WHERE id=%s
        """, (reason, request_id))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"status": "rejected", "message": reason}), http_code

    try:
        juso = road_to_jibun(road_address)
    except Exception as e:
        return fail(f"주소 변환 중 오류: {e}")

    if not juso:
        return fail("입력하신 주소로 지번 정보를 찾지 못했습니다. 도로명주소를 다시 확인해주세요.")

    si_do = juso.get("siNm", "")
    sgg_nm = juso.get("sggNm", "")
    # umd_nm은 마스터/실거래 매칭키다. sync_batch가 emdNm+liNm을 공백제거해 저장하므로
    # 여기서도 동일한 표준 함수로 정규화해야 이후 실거래 sync에서 이 건물이 누락되지 않는다.
    umd_nm = normalize_umd_nm(juso.get("emdNm", "") + juso.get("liNm", ""))
    bun = juso.get("lnbrMnnm", "0")
    ji = juso.get("lnbrSlno", "0")
    jibun_str = f"{bun}-{ji}" if ji not in ("0", "", None) else bun

    bjdong_csv = _os.environ.get("BJDONG_CODE_CSV", "법정동코드 전체자료.csv")
    bjdong = BjdongMap(bjdong_csv)
    sgg_cd = bjdong.find_sgg_cd(si_do, sgg_nm)
    if not sgg_cd:
        return fail("법정동코드 매칭에 실패했습니다. 주소 표기를 확인해주세요.")

    bjdong_cd = bjdong.find_bjdong_cd(sgg_cd, umd_nm)
    if not bjdong_cd:
        return fail("읍/면/동 코드 매칭에 실패했습니다.")

    plat_gb, bun2, ji2 = parse_jibun(jibun_str)

    try:
        label, detail, title, reason = classify_lodging_type(sgg_cd, bjdong_cd, plat_gb, bun2, ji2)
    except Exception as e:
        return fail(f"건축물대장 조회 중 오류: {e}")

    if label is None:
        return fail(f"건축물대장으로 확인한 결과 판정이 어렵습니다 ({reason}). "
                     f"집합건축물(생숙/호텔/콘도)이 맞는지 다시 확인해주세요.")

    # 검증 통과 → 사용자가 뭐라고 골랐든 상관없이, 여기서 확정된 label만 반영
    building_name = building_name_hint or title["bld_nm"] or "(이름 미상)"
    sgg_text = f"{si_do} {sgg_nm}".strip()
    road_addr_final = title["new_plat_plc"] or title["plat_plc"] or road_address

    # 같은 지번의 건물이 이미 신마스터에 있으면 중복 INSERT 대신 검증값으로 갱신한다
    # (같은 주소를 여러 번 요청해도 마스터 키가 중복되지 않도록).
    cur.execute(
        "SELECT id FROM master_buildings WHERE sgg_cd=%s AND umd_nm=%s AND jibun=%s",
        (sgg_cd, umd_nm, jibun_str),
    )
    existing = cur.fetchone()
    if existing:
        master_id = existing["id"]
        cur.execute("""
            UPDATE master_buildings
            SET lodging_type=%s, lodging_type_detail=%s, verified_at=NOW()
            WHERE id=%s
        """, (label, detail, master_id))
    else:
        cur.execute("""
            INSERT INTO master_buildings
                (building_name, road_address, sgg_text, sgg_cd, umd_nm, jibun, units, source,
                 lodging_type, lodging_type_detail, verified_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'user_submitted', %s, %s, NOW())
            RETURNING id
        """, (building_name, road_addr_final, sgg_text, sgg_cd, umd_nm, jibun_str, title["ho_cnt"], label, detail))
        master_id = cur.fetchone()["id"]

    mismatch_note = ""
    if suggested_lodging_type and suggested_lodging_type != label:
        mismatch_note = f" (제출하신 예상 용도 '{suggested_lodging_type}'와 다르게, 건축물대장 확인 결과는 '{label}'입니다.)"

    cur.execute("""
        UPDATE building_requests
        SET status='verified', verified_lodging_type=%s, master_building_id=%s, processed_at=NOW()
        WHERE id=%s
    """, (label, master_id, request_id))
    conn.commit()
    cur.close()
    conn.close()

    return jsonify({
        "status": "verified",
        "message": f"'{building_name}'이(가) '{label}'(으)로 확인되어 등록되었습니다.{mismatch_note} "
                    f"다음 실거래 갱신부터 이 건물의 거래가 표시됩니다.",
        "building_name": building_name,
        "lodging_type": label,
        "units": title["ho_cnt"],
    })


@app.route("/api/request-correction", methods=["POST"])
@limiter.limit("3 per minute; 10 per hour")
def request_correction():
    """
    이미 목록에 있는 건물의 용도 라벨이 잘못됐다고 생각될 때 정정을 요청하는 API.

    핵심 원칙: 사용자가 "이거 아니고 저거예요"라고 제안해도, 그 제안을 그대로 반영하지
    않는다. 반드시 building_registry.classify_lodging_type()으로 그 자리에서 다시
    조회해서, 실제로 확인된 결과만 반영한다. 사용자 제안과 재검증 결과가 같으면
    "확인되어 반영됨", 다르면 "확인해봤지만 제안하신 내용과는 다릅니다"로 응답한다.
    """
    from address_utils import BjdongMap, parse_jibun
    from building_registry import classify_lodging_type
    import os as _os

    data = request.get_json(force=True) or {}
    sgg_cd = (data.get("sgg_cd") or "").strip()
    umd_nm = (data.get("umd_nm") or "").strip()
    jibun = (data.get("jibun") or "").strip()
    suggested_lodging_type = (data.get("suggested_lodging_type") or "").strip()
    requester_note = (data.get("requester_note") or "").strip()

    if not (sgg_cd and umd_nm and jibun):
        return jsonify({"status": "error", "message": "대상 건물 정보가 올바르지 않습니다."}), 400

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO building_requests
            (request_type, target_sgg_cd, target_umd_nm, target_jibun, suggested_lodging_type, requester_note)
        VALUES ('correction', %s, %s, %s, %s, %s) RETURNING id
    """, (sgg_cd, umd_nm, jibun, suggested_lodging_type, requester_note))
    request_id = cur.fetchone()["id"]
    conn.commit()

    def fail(reason):
        cur.execute("""
            UPDATE building_requests SET status='rejected', reject_reason=%s, processed_at=NOW()
            WHERE id=%s
        """, (reason, request_id))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"status": "rejected", "message": reason})

    # 매칭키 정규화: 마스터는 umd_nm을 공백 없이("봉평면면온리"), 실거래는 공백 포함으로
    # ("봉평면 면온리") 저장하므로, 양쪽 컬럼에서 공백을 제거해 비교해야 면/리 지역도 매칭된다.
    umd_key = normalize_umd_nm(umd_nm)

    cur.execute("""
        SELECT id, building_name, lodging_type FROM master_buildings
        WHERE sgg_cd=%s AND REPLACE(umd_nm, ' ', '')=%s AND jibun=%s
    """, (sgg_cd, umd_key, jibun))
    building = cur.fetchone()
    if not building:
        return fail("해당 건물을 마스터 목록에서 찾지 못했습니다.")

    bjdong_csv = _os.environ.get("BJDONG_CODE_CSV", "법정동코드 전체자료.csv")
    bjdong = BjdongMap(bjdong_csv)
    bjdong_cd = bjdong.find_bjdong_cd(sgg_cd, umd_nm)
    if not bjdong_cd:
        return fail("읍/면/동 코드 매칭에 실패했습니다.")

    plat_gb, bun, ji = parse_jibun(jibun)

    try:
        label, detail, title, reason = classify_lodging_type(sgg_cd, bjdong_cd, plat_gb, bun, ji)
    except Exception as e:
        return fail(f"건축물대장 재조회 중 오류: {e}")

    if label is None:
        return fail(f"재검증했지만 판정이 어렵습니다 ({reason}). 기존 값을 그대로 유지합니다.")

    old_label = building["lodging_type"]
    changed = (label != old_label)

    if changed:
        cur.execute("""
            UPDATE master_buildings SET lodging_type=%s, lodging_type_detail=%s, verified_at=NOW()
            WHERE id=%s
        """, (label, detail, building["id"]))
        cur.execute("""
            UPDATE transactions SET lodging_type=%s, lodging_type_detail=%s
            WHERE sgg_cd=%s AND REPLACE(umd_nm, ' ', '')=%s AND jibun=%s
        """, (label, detail, sgg_cd, umd_key, jibun))

    cur.execute("""
        UPDATE building_requests
        SET status='verified', verified_lodging_type=%s, changed=%s, master_building_id=%s, processed_at=NOW()
        WHERE id=%s
    """, (label, changed, building["id"], request_id))
    conn.commit()
    cur.close()
    conn.close()

    if changed:
        message = f"재검증 결과 '{old_label or '미확인'}' → '{label}'(으)로 확인되어 반영했습니다."
    else:
        message = f"건축물대장을 다시 확인했지만, 기존 라벨 '{old_label or '미확인'}'이 맞는 것으로 확인됐습니다."
        if suggested_lodging_type and suggested_lodging_type != label:
            message += f" (제안하신 '{suggested_lodging_type}'과는 다릅니다.)"

    return jsonify({
        "status": "verified",
        "changed": changed,
        "lodging_type": label,
        "message": message,
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
