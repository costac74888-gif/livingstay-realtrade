# -*- coding: utf-8 -*-
"""
app.py — 검색 API + 정적 페이지 서빙 (Replit에서 바로 실행)

엔드포인트
------------------------------------------------------------
GET /                          → static/index.html 서빙
GET /api/transactions          → 게시판(전체 최신순) or 검색 결과
    쿼리파라미터:
      q       : 건물명 또는 주소 검색어 (부분일치, 보조 수단)
      si_do   : 시/도 (예: '경기도') — 정확히 일치
      sgg_nm  : 시/군/구 (예: '수원시') — 정확히 일치
      umd_nm  : 읍/면/동 (예: '매산로1가') — 정확히 일치
      year    : 계약연도 (예: '2026', 'all'이면 전체)
      page/size
GET /api/regions               → 계층형 지역 트리 (시도 > 시군구 > 읍면동, 각 count)
GET /api/health                → 배치 마지막 실행 시각/건수 확인용
"""

from flask import Flask, request, jsonify, send_from_directory
from datetime import datetime
from db import get_conn

app = Flask(__name__, static_folder="static")


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/transactions")
def get_transactions():
    q = request.args.get("q", "").strip()
    si_do = request.args.get("si_do", "").strip()
    sgg_nm = request.args.get("sgg_nm", "").strip()
    umd_nm = request.args.get("umd_nm", "").strip()
    year = request.args.get("year", "").strip()
    page = max(int(request.args.get("page", 1)), 1)
    size = min(int(request.args.get("size", 20)), 200)
    offset = (page - 1) * size

    where = ["1=1"]
    params = []

    if q:
        where.append("(building_name ILIKE %s OR address ILIKE %s)")
        params += [f"%{q}%", f"%{q}%"]
    if si_do:
        where.append("si_do = %s")
        params.append(si_do)
    if sgg_nm:
        where.append("sgg_nm = %s")
        params.append(sgg_nm)
    if umd_nm:
        where.append("umd_nm = %s")
        params.append(umd_nm)
    if year and year != "all":
        where.append("deal_date LIKE %s")
        params.append(f"{year}-%")

    where_sql = " AND ".join(where)

    conn = get_conn()
    cur = conn.cursor()

    cur.execute(f"SELECT COUNT(*) c FROM transactions WHERE {where_sql}", params)
    total = cur.fetchone()["c"]

    cur.execute(f"""
        SELECT building_name, address, si_do, sgg_nm, umd_nm, jibun,
               area, price, deal_date, deal_type, floor, match_source
        FROM transactions
        WHERE {where_sql}
        ORDER BY deal_date DESC, id DESC
        LIMIT %s OFFSET %s
    """, params + [size, offset])
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()

    return jsonify({"total": total, "page": page, "size": size, "items": rows})


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


@app.route("/api/favorites")
def get_favorites():
    """
    관심단지 전용 조회 — /api/transactions의 size 상한(200)과 무관하게
    저장된 관심단지 키(building_name|address) 전체를 한 번에 정확히 조회한다.
    쿼리파라미터: keys = "건물명|주소" 쌍을 파이프(|)로 감싼 문자열들을 쉼표(,)로 연결
        예) keys=오션마크레지던스|우동 1467,센트럴파인스테이|역삼동 712-9
    """
    raw_keys = request.args.get("keys", "").strip()
    if not raw_keys:
        return jsonify({"items": []})

    pairs = []
    for token in raw_keys.split(","):
        if "|" not in token:
            continue
        name, addr = token.split("|", 1)
        pairs.append((name, addr))

    if not pairs:
        return jsonify({"items": []})

    conn = get_conn()
    cur = conn.cursor()

    conditions = " OR ".join(["(building_name = %s AND address = %s)"] * len(pairs))
    params = [v for pair in pairs for v in pair]

    cur.execute(f"""
        SELECT building_name, address, si_do, sgg_nm, umd_nm, jibun,
               area, price, deal_date, deal_type, floor, match_source
        FROM transactions
        WHERE {conditions}
        ORDER BY deal_date DESC, id DESC
    """, params)
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()

    return jsonify({"items": rows, "total": len(rows)})


@app.route("/api/submit-building", methods=["POST"])
def submit_building():
    """
    사용자가 '내 건물 추가해주세요' 버튼으로 주소를 제출하면:
      1) 도로명→지번 변환
      2) building_registry.is_living_stay()로 실시간 검증
      3) 통과하면 즉시 master_buildings에 편입(verified_at 찍힘) → 검증실패는 사유와 함께 거절
    거절/보류 이력도 building_requests에 전부 남긴다 (나중에 수동 검토용).
    """
    from address_utils import road_to_jibun, BjdongMap, parse_jibun
    from building_registry import is_living_stay
    import os as _os

    data = request.get_json(force=True) or {}
    road_address = (data.get("road_address") or "").strip()
    building_name_hint = (data.get("building_name_hint") or "").strip()
    requester_note = (data.get("requester_note") or "").strip()

    if not road_address:
        return jsonify({"status": "error", "message": "주소를 입력해주세요."}), 400

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO building_requests (road_address, building_name_hint, requester_note)
        VALUES (%s, %s, %s) RETURNING id
    """, (road_address, building_name_hint, requester_note))
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
    umd_nm = juso.get("emdNm", "")
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
        verdict, title, reason = is_living_stay(sgg_cd, bjdong_cd, plat_gb, bun2, ji2)
    except Exception as e:
        return fail(f"건축물대장 조회 중 오류: {e}")

    if verdict is None:
        return fail(f"건축물대장에서 집합건축물 정보를 찾지 못했습니다 ({reason}). "
                     f"등록된 생활숙박시설이 맞는지 다시 확인해주세요.")
    if verdict is False:
        return fail(f"건축물대장 확인 결과 생활숙박시설이 아닙니다 ({reason}).")

    # 검증 통과 → 마스터에 즉시 편입
    building_name = building_name_hint or title["bld_nm"] or "(이름 미상)"
    sgg_text = f"{si_do} {sgg_nm}".strip()
    road_addr_final = title["new_plat_plc"] or title["plat_plc"] or road_address

    cur.execute("""
        INSERT INTO master_buildings
            (building_name, road_address, sgg_text, sgg_cd, umd_nm, jibun, units, source, verified_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, 'user_submitted', NOW())
        RETURNING id
    """, (building_name, road_addr_final, sgg_text, sgg_cd, umd_nm, jibun_str, title["ho_cnt"]))
    master_id = cur.fetchone()["id"]

    cur.execute("""
        UPDATE building_requests SET status='verified', master_building_id=%s, processed_at=NOW()
        WHERE id=%s
    """, (master_id, request_id))
    conn.commit()
    cur.close()
    conn.close()

    return jsonify({
        "status": "verified",
        "message": f"'{building_name}'이(가) 생활숙박시설로 확인되어 등록되었습니다. "
                    f"다음 실거래 갱신부터 이 건물의 거래가 표시됩니다.",
        "building_name": building_name,
        "units": title["ho_cnt"],
    })


@app.route("/api/years")
def get_years():
    """
    실거래 연도 목록 (기간 필터 드롭다운용).
    - 실제 데이터에 존재하는 연도는 항상 유지 (나중에 데이터가 있던 과거 연도가 목록에서 사라지지 않음)
    - 기본으로 "현재년-2 ~ 현재년"도 항상 포함 (아직 그 해 데이터가 없어도 선택지로 보이도록)
    - 미래 연도는 실제 거래가 생기는 시점에 자동으로 추가됨 (하드코딩 아님)
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT LEFT(deal_date, 4) y FROM transactions WHERE deal_date IS NOT NULL")
    data_years = {r["y"] for r in cur.fetchall() if r["y"]}
    cur.close()
    conn.close()

    current_year = datetime.now().year
    default_years = {str(current_year - 2), str(current_year - 1), str(current_year)}
    years = sorted(data_years | default_years, reverse=True)

    return jsonify({"years": years, "current_year": str(current_year)})


@app.route("/api/health")
def health():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM sync_log ORDER BY id DESC LIMIT 1")
    last = cur.fetchone()
    cur.close()
    conn.close()
    return jsonify(dict(last) if last else {"status": "no sync yet"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
