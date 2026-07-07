# -*- coding: utf-8 -*-
"""
app.py — 검색 API + 정적 페이지 서빙 (Replit에서 바로 실행)

엔드포인트
------------------------------------------------------------
GET /                          → static/index.html 서빙
GET /api/transactions          → 게시판(전체 최신순) or 검색 결과
    쿼리파라미터:
      q       : 건물명 또는 주소 검색어 (부분일치)
      region  : 시/도 필터 (예: '서울', '부산') — 주소 앞부분 매칭
      page    : 페이지 번호 (기본 1)
      size    : 페이지당 건수 (기본 20)
GET /api/regions               → 지역 탭용 집계 (전체/서울/부산/... 건수)
GET /api/health                → 배치 마지막 실행 시각/건수 확인용
"""

from flask import Flask, request, jsonify, send_from_directory
from db import get_conn

app = Flask(__name__, static_folder="static")


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/transactions")
def get_transactions():
    q = request.args.get("q", "").strip()
    region = request.args.get("region", "").strip()
    page = max(int(request.args.get("page", 1)), 1)
    size = min(int(request.args.get("size", 20)), 100)
    offset = (page - 1) * size

    where = ["1=1"]
    params = []

    if q:
        where.append("(building_name LIKE %s OR address LIKE %s)")
        params += [f"%{q}%", f"%{q}%"]

    if region and region != "전체":
        where.append("address LIKE %s")
        params.append(f"%{region}%")

    where_sql = " AND ".join(where)

    conn = get_conn()
    cur = conn.cursor()

    cur.execute(f"SELECT COUNT(*) c FROM transactions WHERE {where_sql}", params)
    total = cur.fetchone()["c"]

    cur.execute(f"""
        SELECT building_name, address, area, price, deal_date, deal_type, match_source
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
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT address FROM transactions")
    rows = cur.fetchall()
    cur.close()
    conn.close()

    # 주소 첫 토큰(시/도) 기준 집계 — 필요시 시/군/구 단위로 세분화 가능
    from collections import Counter
    counter = Counter()
    for r in rows:
        first_tok = r["address"].split()[0] if r["address"] else "기타"
        counter[first_tok] += 1

    result = [{"region": "전체", "count": sum(counter.values())}]
    result += [{"region": k, "count": v} for k, v in counter.most_common()]
    return jsonify(result)


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
