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
               area, price, deal_date, deal_type, match_source
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


@app.route("/api/years")
def get_years():
    """실제 데이터에 존재하는 계약연도 목록 (기간 필터 드롭다운용)"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT LEFT(deal_date, 4) y FROM transactions ORDER BY y DESC")
    years = [r["y"] for r in cur.fetchall() if r["y"]]
    cur.close()
    conn.close()
    return jsonify({"years": years, "current_year": str(datetime.now().year)})


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
