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
import re
import io
import sys
import json
import time
import hashlib
import threading
import subprocess
import secrets as _secrets
from functools import wraps
from urllib.parse import quote, urlencode
import requests
from werkzeug.security import generate_password_hash, check_password_hash

from sms_util import send_sms
from psycopg2 import errors as psycopg2_errors
from psycopg2.extras import execute_values
from flask import Flask, request, jsonify, send_from_directory, Response, abort, session, redirect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from datetime import datetime
from db import get_conn, init_db
from address_utils import (
    normalize_umd_nm, sido_core, sido_match_clause,
    build_authority_index, match_authority_contact,
)

# 서버 기동 시각 — 정적 SDK URL 캐시 무효화용 (기동할 때만 바뀜)
SERVER_BOOT_V = str(int(time.time()))

# 정적 JS/CSS 자산에 배포마다 바뀌는 버전 쿼리스트링(?v=SERVER_BOOT_V)을 붙여
# 새 배포 때 브라우저가 무조건 새 파일을 받도록 한다(캐시버스팅). 버전 값은
# 하드코딩하지 않고 서버 기동 시각(=배포마다 갱신)을 재사용한다.
_ASSET_VER_RE = re.compile(r'(src|href)="(/static/(?:js|css)/[^"?]+\.(?:js|css))"')


def _inject_asset_version(html):
    return _ASSET_VER_RE.sub(
        lambda m: f'{m.group(1)}="{m.group(2)}?v={SERVER_BOOT_V}"', html
    )

app = Flask(__name__, static_folder="static")
# 관리자 세션(서명된 쿠키) 서명 키. FLASK_SECRET_KEY가 없으면 세션이 유지되지
# 않아 관리자 로그인이 동작하지 않으므로 Secrets에 반드시 등록되어 있어야 한다.
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "")
if not app.secret_key:
    # 세션 쿠키는 이 키로 서명된다. 빈 키면 누구나 세션(회원/관리자)을 위조할 수
    # 있으므로 로그인 기능의 신뢰가 붕괴된다. 없으면 기동 자체를 중단한다.
    raise RuntimeError(
        "FLASK_SECRET_KEY가 설정되지 않았습니다. Secrets에 등록 후 다시 실행하세요."
    )

# 세션 쿠키 보안 플래그.
#  - HTTPONLY: JS(document.cookie)에서 세션 쿠키를 읽지 못하게 하여 XSS 탈취 방지.
#  - SECURE: HTTPS로만 전송(리플릿은 dev/prod 모두 HTTPS).
#  - SAMESITE=Lax: 카카오 OAuth 콜백처럼 외부에서 되돌아오는 top-level GET 이동에는
#    쿠키가 실려야 state(CSRF) 검증이 가능하므로 Strict가 아닌 Lax를 사용한다.
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_SAMESITE="Lax",
)


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

# 방문 기록(page_views)용 고정 salt — 원본 IP를 그대로 저장하지 않고 해시할 때 쓴다.
# 코드에 평문 salt를 박지 않으려고 FLASK_SECRET_KEY를 재사용(이미 시크릿). 없으면 폴백.
_PAGE_VIEW_SALT = os.environ.get("FLASK_SECRET_KEY", "") or "livingstay_pageview_salt_v1"


def _record_page_view(path, resp_status):
    """실제 사용자 페이지(GET·200)만 page_views에 1건 기록한다.
    개인정보 최소수집: 방문자 IP는 원본 저장 없이 sha256(IP+salt)로만 남긴다.
    통계 기록 실패가 절대 실서비스 요청을 죽이지 않도록 전 구간을 try/except로 감싼다."""
    conn = None
    cur = None
    try:
        ip = get_client_ip() or ""
        ip_hash = hashlib.sha256((ip + _PAGE_VIEW_SALT).encode("utf-8")).hexdigest()
        ua = (request.headers.get("User-Agent") or "")[:500]
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO page_views (path, ip_hash, user_agent) VALUES (%s, %s, %s)",
            [path[:500], ip_hash, ua],
        )
        conn.commit()
    except Exception:
        # 통계 때문에 사용자 요청이 실패하면 안 된다 → 조용히 무시.
        pass
    finally:
        # 예외가 나도 커서/커넥션은 반드시 정리해 연결 누수를 막는다.
        if cur is not None:
            try:
                cur.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


@app.after_request
def _log_page_view(resp):
    """사용자 페이지 조회만 집계: GET·200이고 /api·/admin·/static 이 아닌 경로.
    (실제 집계 대상: /, /building/<id>, /apply/agent, /apply/operator 등)"""
    try:
        if request.method == "GET" and resp.status_code == 200:
            path = request.path or "/"
            excluded = any(
                path == p or path.startswith(p + "/")
                for p in ("/api", "/admin", "/static")
            )
            # 정적 자산(favicon.ico, .js, .css 등)도 페이지 조회가 아니므로 제외
            is_asset = "." in path.rsplit("/", 1)[-1]
            if not excluded and not is_asset:
                _record_page_view(path, resp.status_code)
    except Exception:
        pass
    return resp


# 앱 부팅 시 스키마를 보장한다 (building_requests 정정 컬럼 등).
# init_db는 CREATE/ALTER ... IF NOT EXISTS라 여러 번 호출해도 안전(멱등).
# 이렇게 해야 배포 직후(아직 sync 스크립트가 안 돈 시점)에도 요청 API가 500 없이 동작한다.
init_db()


def _serve_app_shell():
    # 정적 index.html을 읽어 카카오맵 JS 키만 서버에서 주입해 서빙한다.
    # (프론트 소스에 키를 직접 박지 않고, 환경변수/시크릿에서 안전하게 넣는다.)
    kakao_js_key = os.environ.get("KAKAO_JS_KEY", "")
    html_path = os.path.join(app.static_folder, "index.html")
    with open(html_path, encoding="utf-8") as f:
        html = f.read()
    html = html.replace("{{KAKAO_JS_KEY}}", quote(kakao_js_key, safe=""))
    html = html.replace("{{KAKAO_SDK_V}}", SERVER_BOOT_V)
    html = _inject_asset_version(html)
    resp = Response(html, mimetype="text/html")
    # 진입 HTML은 캐시하지 않아 항상 최신 SDK URL(_v)을 받도록 한다.
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp


@app.route("/")
def index():
    return _serve_app_shell()


@app.route("/building/<int:building_id>")
def building_page(building_id):
    """건물 상세 — 별도 페이지가 아니라 홈화면(index.html)을 그대로 서빙한다.

    상세 내용은 프런트(main.js renderBuildingPanel)에서 좌측 패널 안에 그린다.
    새로고침/공유 링크로 /building/<id>에 직접 들어와도 index.html이 로드되며,
    main.js가 URL을 확인해 자동으로 해당 건물 상세를 좌측 패널에 표시한다.
    (static/building.html은 롤백 대비 남겨두되 더 이상 서빙하지 않는다.)
    """
    return _serve_app_shell()


_AUTHORITY_INDEX = None


def get_authority_index():
    """lodging_authority_contacts(135행)로 담당부서 매칭 인덱스를 1회 만들어 캐시한다.

    데이터가 정적(엑셀 적재본)이고 gunicorn 자동 리로드가 없어 프로세스 단위 캐시로 충분.
    적재를 다시 하면(load_authority_contacts.py) 앱을 재시작해야 새 값이 반영된다.
    """
    global _AUTHORITY_INDEX
    if _AUTHORITY_INDEX is None:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT region_name_raw, dept, phone FROM lodging_authority_contacts")
        rows = [dict(r) for r in cur.fetchall()]
        cur.close()
        conn.close()
        _AUTHORITY_INDEX = build_authority_index(rows)
    return _AUTHORITY_INDEX


@app.route("/api/building/<int:building_id>")
def get_building(building_id):
    """건물 상세페이지용 단건 조회 — master_buildings 기준."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT mb.building_name, mb.road_address, mb.lodging_type, mb.lodging_type_detail,
               mb.units, mb.biz_units, mb.lat, mb.lng, mb.sgg_text,
               mb.use_apr_day, mb.tot_pkng_cnt, mb.grnd_flr_cnt, mb.ugrnd_flr_cnt,
               mb.tot_area, mb.plat_area, mb.hhld_cnt, mb.strct_nm,
               lt.address AS address
        FROM master_buildings mb
        LEFT JOIN LATERAL (
            SELECT t.address
            FROM transactions t
            WHERE (
                    mb.sgg_cd IS NOT NULL AND mb.umd_nm IS NOT NULL AND mb.jibun IS NOT NULL
                    AND t.sgg_cd = mb.sgg_cd
                    AND t.umd_nm = mb.umd_nm
                    AND t.jibun  = mb.jibun
                  )
               OR (
                    (mb.sgg_cd IS NULL OR mb.umd_nm IS NULL OR mb.jibun IS NULL)
                    AND mb.building_name <> '-'
                    AND t.building_name = mb.building_name
                  )
            ORDER BY (t.building_name = mb.building_name) DESC NULLS LAST, t.deal_date DESC
            LIMIT 1
        ) lt ON TRUE
        WHERE mb.id = %s
    """, [building_id])
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        return jsonify({"error": "not found"}), 404

    # 전속중개사: 이 건물의 활성 매물(status='active') 중 agent가 연결된 것을 agents와 JOIN.
    # 없으면 agent: null. 여러 건이면 최근 갱신 순 1건.
    cur.execute("""
        SELECT a.office_name, a.owner_name, a.phone
        FROM listings l
        JOIN agents a ON a.id = l.agent_id
        WHERE l.master_building_id = %s
          AND l.status = 'active'
          AND l.agent_id IS NOT NULL
        ORDER BY l.updated_at DESC NULLS LAST, l.id DESC
        LIMIT 1
    """, [building_id])
    agent_row = cur.fetchone()
    cur.close()
    conn.close()

    result = dict(row)
    result["agent"] = dict(agent_row) if agent_row else None

    # 담당부처/연락처: sgg_text를 지자체 담당부서 인덱스와 매칭.
    #   source='exact'(시군구 전용) | 'fallback'(시도 대표) → 화면에서 "(시/도 대표)" 꼬리표 판단용.
    #   매칭 실패면 dept=phone=None → 화면은 "확인중" 유지.
    #   매칭/인덱스 조회가 어떤 이유로 실패해도 건물 상세 전체가 죽지 않도록 방어(담당부처만 확인중).
    try:
        dept, phone, source = match_authority_contact(result.get("sgg_text"), get_authority_index())
    except Exception:
        app.logger.exception("담당부서 매칭 실패 (building_id=%s)", building_id)
        dept, phone, source = None, None, None
    result["authority_dept"] = dept
    result["authority_phone"] = phone
    result["authority_source"] = source if dept is not None else None
    return jsonify(result)


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

    # 선택적 building_id → 해당 건물의 실거래만(get_buildings_geo/get_monthly_trend와 동일 전략).
    #   - 지번키(sgg_cd+umd_nm+jibun)가 모두 있으면 지번 정확 매칭(동명 건물 오염 방지)
    #   - 셋 중 하나라도 NULL이면 building_name 폴백('-'/미존재/빈값은 0매칭 처리)
    #   - 정수가 아니거나 없으면 기존 동작(q/지역/연도 등) 그대로 유지(하위호환)
    building_id = request.args.get("building_id", "").strip()
    if building_id.isdigit():
        mconn = get_conn()
        mcur = mconn.cursor()
        mcur.execute("""
            SELECT building_name, sgg_cd, umd_nm, jibun
            FROM master_buildings WHERE id = %s
        """, [int(building_id)])
        b = mcur.fetchone()
        mcur.close()
        mconn.close()
        if b and b["sgg_cd"] and b["umd_nm"] and b["jibun"]:
            where.append("sgg_cd = %s AND umd_nm = %s AND jibun = %s")
            params += [b["sgg_cd"], b["umd_nm"], b["jibun"]]
        else:
            name = (b["building_name"] if b else None) or ""
            where.append("building_name = %s")
            params.append(name if name and name != "-" else "\x00")

    where_sql = " AND ".join(where)

    conn = get_conn()
    cur = conn.cursor()

    cur.execute(f"SELECT COUNT(*) c FROM transactions WHERE {where_sql}", params)
    total = cur.fetchone()["c"]

    # master_building_id: 각 거래의 지번키(sgg_cd+umd_nm+jibun)로 master_buildings를
    # 역매칭(get_buildings_geo/get_monthly_trend와 동일한 지번 정확 매칭 전략).
    #   - 세 키가 모두 있고 대응 건물이 있으면 그 건물 id, 없으면 NULL.
    #   - 필터/정렬/페이지네이션(where_sql/ORDER BY/LIMIT)에는 영향 없음.
    cur.execute(f"""
        SELECT building_name, address, si_do, sgg_nm, umd_nm, jibun, sgg_cd,
               area, price, deal_date, deal_type, floor,
               lodging_type, lodging_type_detail, match_source,
               (SELECT mb.id FROM master_buildings mb
                 WHERE mb.sgg_cd = transactions.sgg_cd
                   AND mb.umd_nm = transactions.umd_nm
                   AND mb.jibun = transactions.jibun
                 ORDER BY mb.id LIMIT 1) AS master_building_id
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
    # 각 건물의 '가장 최근 실거래가'를 지번(sgg_cd+umd_nm+jibun) 기준으로 1건만 붙인다.
    # 건물명 매칭은 마스터에 건물명이 "-"처럼 여러 건물이 공유하는 플레이스홀더로
    # 채워진 경우, "-"인 실거래 1건이 "-" 이름의 모든 건물에 잘못 붙는 버그가 있어
    # 지번 튜플 매칭으로 대체한다(sync_batch.py가 transactions에 적재할 때 쓰는
    # (sgg_cd, 정규화 umd_nm, jibun)과 동일한 키).
    #   - 지번 3개 컬럼이 모두 있으면 지번으로 정확 매칭.
    #   - 셋 중 하나라도 NULL이라 지번 매칭이 불가능하면, 예외적으로 건물명으로
    #     한 번 더 시도하되 "-" 같은 플레이스홀더 이름은 제외한다.
    # 같은 지번에 여러 건물(동/호로 구분되는 단지)이 있으면 서로 다른 건물의 거래가
    # 섞일 수 있으므로, 지번이 같은 후보 안에서 건물명(t.building_name = mb.building_name)
    # 까지 정확히 일치하는 거래를 최우선으로 고르고(name_exact DESC), 그런 거래가
    # 없으면 그 지번의 최신 거래를 대체값으로 쓴다(그다음 deal_date DESC).
    #   - latest_price_exact=TRUE  : 건물명까지 정확히 일치한 확정 거래
    #   - latest_price_exact=FALSE : 같은 필지의 대체(참고) 거래
    # N+1 방지를 위해 LEFT JOIN LATERAL로 건물당 최신 1행만 조회하고,
    # 실거래 이력이 없으면 latest_price/latest_deal_date가 NULL로 반환된다.
    cur.execute(f"""
        SELECT mb.id, mb.building_name, mb.road_address, mb.lat, mb.lng, mb.lodging_type,
               lt.price AS latest_price, lt.deal_date AS latest_deal_date,
               lt.floor AS latest_floor, lt.area AS latest_area,
               lt.deal_type AS latest_deal_type,
               COALESCE(lt.name_exact, FALSE) AS latest_price_exact,
               lt.address AS address
        FROM master_buildings mb
        LEFT JOIN LATERAL (
            SELECT t.price, t.deal_date, t.floor, t.area, t.deal_type, t.address,
                   (t.building_name = mb.building_name) AS name_exact
            FROM transactions t
            WHERE (
                    mb.sgg_cd IS NOT NULL AND mb.umd_nm IS NOT NULL AND mb.jibun IS NOT NULL
                    AND t.sgg_cd = mb.sgg_cd
                    AND t.umd_nm = mb.umd_nm
                    AND t.jibun  = mb.jibun
                  )
               OR (
                    (mb.sgg_cd IS NULL OR mb.umd_nm IS NULL OR mb.jibun IS NULL)
                    AND mb.building_name <> '-'
                    AND t.building_name = mb.building_name
                  )
            ORDER BY (t.building_name = mb.building_name) DESC NULLS LAST, t.deal_date DESC
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

    선택적 building_id가 있으면 해당 건물(master_buildings.building_name)의
    실거래만 집계하고, 없으면 기존처럼 전체를 집계한다(하위호환).
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

    where = ["deal_date IS NOT NULL", "substring(deal_date, 1, 7) >= %s"]
    params = [start_ym]

    # 선택적 building_id → 해당 건물의 실거래만 집계(하위호환: 없거나 정수 아니면 전체 집계).
    # 정확도: A화면 마커(get_buildings_geo)와 동일한 키 전략을 쓴다.
    #   - 지번키(sgg_cd+umd_nm+jibun)가 모두 있으면 지번으로 정확 매칭
    #     (건물명은 유니크 키가 아니라 동명 건물 거래가 섞일 수 있어 지번을 우선).
    #   - 셋 중 하나라도 NULL이면 예외적으로 건물명 매칭('-' 플레이스홀더는 제외).
    # 정수가 아닌 값은 무시하고 전체 집계로 폴백해 500(정수 캐스팅 오류)을 막는다.
    building_id = request.args.get("building_id", "").strip()
    if building_id.isdigit():
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT building_name, sgg_cd, umd_nm, jibun
            FROM master_buildings WHERE id = %s
        """, [int(building_id)])
        b = cur.fetchone()
        cur.close()
        conn.close()
        if b and b["sgg_cd"] and b["umd_nm"] and b["jibun"]:
            where.append("sgg_cd = %s AND umd_nm = %s AND jibun = %s")
            params += [b["sgg_cd"], b["umd_nm"], b["jibun"]]
        else:
            # 지번키 불완전 → 건물명 폴백. 건물 미존재/이름 없음/'-'는 매칭 0으로 처리.
            name = (b["building_name"] if b else None) or ""
            where.append("building_name = %s")
            params.append(name if name and name != "-" else "\x00")

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(f"""
        SELECT substring(deal_date, 1, 7) AS ym,
               COUNT(*) AS cnt,
               COALESCE(SUM(price), 0) AS sum_price
        FROM transactions
        WHERE {" AND ".join(where)}
        GROUP BY ym
    """, params)
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
               lodging_type, lodging_type_detail, match_source,
               (SELECT mb.id FROM master_buildings mb
                 WHERE mb.sgg_cd = transactions.sgg_cd
                   AND mb.umd_nm = transactions.umd_nm
                   AND mb.jibun = transactions.jibun
                 ORDER BY mb.id LIMIT 1) AS master_building_id
        FROM transactions
        WHERE {conditions}
        ORDER BY deal_date DESC, id DESC
    """, params)
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return jsonify({"items": rows, "total": len(rows)})


def _fill_master_coords(cur, master_id, road_address):
    """신규 master_buildings 행에 카카오 지오코딩(geocode_buildings.geocode_address)으로
    lat/lng을 채운다. 이미 열려 있는 커서를 받아 UPDATE만 수행하고 커밋은 호출측에 맡긴다.

    주소 미인식/카카오 API 오류/키 미설정 등으로 실패해도 예외를 밖으로 던지지 않아
    건물 등록 자체는 막지 않는다(좌표만 NULL로 남기고 넘어감)."""
    if not road_address:
        return
    try:
        from geocode_buildings import geocode_address
        result = geocode_address(road_address)
        if not result:
            return
        lat, lng = result
        # 보조 UPDATE는 SAVEPOINT로 감싼다. UPDATE 자체가 DB 오류를 내도
        # 메인 INSERT 트랜잭션이 aborted 상태로 오염되지 않아, 호출측 commit이
        # 정상 진행되고 건물 등록은 좌표 NULL로라도 유지된다.
        cur.execute("SAVEPOINT geocode_sp")
        try:
            cur.execute(
                "UPDATE master_buildings SET lat=%s, lng=%s WHERE id=%s",
                (lat, lng, master_id),
            )
            cur.execute("RELEASE SAVEPOINT geocode_sp")
        except Exception:
            cur.execute("ROLLBACK TO SAVEPOINT geocode_sp")
            raise
    except Exception as e:
        app.logger.warning(
            "신규 건물 지오코딩 실패(등록은 계속) id=%s: %s / %s",
            master_id, road_address, e,
        )


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
        # 신규 편입 건물의 좌표를 도로명주소로 즉시 채운다(실패해도 등록은 계속).
        _fill_master_coords(cur, master_id, road_addr_final)

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


@app.route("/apply/agent")
def apply_agent_page():
    """중개사 회원신청(C화면) 정적 폼 HTML 서빙.

    카카오맵이 필요 없는 단순 정적 폼이므로 키 주입 없이 그대로 서빙한다.
    """
    html_path = os.path.join(app.static_folder, "apply_agent.html")
    with open(html_path, encoding="utf-8") as f:
        html = f.read()
    html = _inject_asset_version(html)
    resp = Response(html, mimetype="text/html")
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp


@app.route("/api/apply/agent", methods=["POST"])
@limiter.limit("3 per minute; 10 per hour")
def apply_agent():
    """중개사 회원신청 접수 API.

    텍스트 항목만 받아 applications 테이블에 applicant_type='agent',
    status='submitted'로 INSERT한다. 서류(자격증/등록증 등)는 이번엔 미사용이라
    doc_* 및 intro_text는 NULL로 둔다.
    """
    data = request.get_json(force=True) or {}

    office_or_company_name = (data.get("office_or_company_name") or "").strip()
    owner_name = (data.get("owner_name") or "").strip()
    reg_number = (data.get("reg_number") or "").strip()
    biz_reg_number = (data.get("biz_reg_number") or "").strip()
    phone = (data.get("phone") or "").strip()
    email = (data.get("email") or "").strip()
    # 희망지역 → 희망건물로 변경. 구버전 호환을 위해 preferred_region도 함께 받아둔다.
    preferred_building = (data.get("preferred_building") or "").strip()
    preferred_region = (data.get("preferred_region") or "").strip()

    # 필수값 검증
    missing = []
    if not office_or_company_name:
        missing.append("중개사무소명")
    if not owner_name:
        missing.append("대표자")
    if not reg_number:
        missing.append("등록번호")
    if not phone:
        missing.append("연락처")
    if not email:
        missing.append("이메일")
    if missing:
        return jsonify({"ok": False, "message": "필수 항목을 입력해주세요: " + ", ".join(missing)}), 400

    # 간단한 이메일 형식 체크 (@ 앞뒤로 내용, . 포함)
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return jsonify({"ok": False, "message": "이메일 형식이 올바르지 않습니다."}), 400

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO applications
            (applicant_type, office_or_company_name, owner_name, reg_number,
             biz_reg_number, phone, email, preferred_region, preferred_building, status,
             intro_text, doc_license_url, doc_office_reg_url, doc_biz_reg_url)
        VALUES ('agent', %s, %s, %s, %s, %s, %s, %s, %s, 'submitted',
                NULL, NULL, NULL, NULL)
        RETURNING id
    """, (office_or_company_name, owner_name, reg_number,
          biz_reg_number or None, phone, email, preferred_region or None,
          preferred_building or None))
    new_id = cur.fetchone()["id"]
    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"ok": True, "id": new_id})


@app.route("/apply/operator")
def apply_operator_page():
    """운영업체 등록신청(D화면) 정적 폼 HTML 서빙.

    apply_agent_page()과 동일하게, 카카오맵이 필요 없는 단순 정적 폼이므로
    키 주입 없이 그대로 서빙한다.
    """
    html_path = os.path.join(app.static_folder, "apply_operator.html")
    with open(html_path, encoding="utf-8") as f:
        html = f.read()
    html = _inject_asset_version(html)
    resp = Response(html, mimetype="text/html")
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp


# 운영업체 업종: 이 6개만 허용한다(operators.category와 동일 기준).
OPERATOR_CATEGORIES = {"위탁운영", "청소", "세탁", "용품", "대출상담사", "인테리어"}


@app.route("/api/apply/operator", methods=["POST"])
@limiter.limit("3 per minute; 10 per hour")
def apply_operator():
    """운영업체 등록신청 접수 API.

    apply/agent와 동일한 구조로 텍스트 항목만 받아 applications 테이블에
    applicant_type='operator', status='submitted'로 INSERT한다. 서류(명함/영업
    허가증 등)는 이번엔 미사용이라 doc_* 및 reg_number/intro_text는 NULL로 둔다.
    """
    data = request.get_json(force=True) or {}

    office_or_company_name = (data.get("office_or_company_name") or "").strip()
    owner_name = (data.get("owner_name") or "").strip()
    category = (data.get("category") or "").strip()
    biz_reg_number = (data.get("biz_reg_number") or "").strip()
    phone = (data.get("phone") or "").strip()
    email = (data.get("email") or "").strip()
    website_url = (data.get("website_url") or "").strip()
    preferred_region = (data.get("preferred_region") or "").strip()

    # 필수값 검증
    missing = []
    if not office_or_company_name:
        missing.append("업체명")
    if not owner_name:
        missing.append("대표자")
    if not category:
        missing.append("업종")
    if not phone:
        missing.append("연락처")
    if not email:
        missing.append("이메일")
    if missing:
        return jsonify({"ok": False, "message": "필수 항목을 입력해주세요: " + ", ".join(missing)}), 400

    # 업종은 허용된 6개 중 하나만
    if category not in OPERATOR_CATEGORIES:
        return jsonify({"ok": False, "message": "업종은 다음 중 하나여야 합니다: " + ", ".join(sorted(OPERATOR_CATEGORIES))}), 400

    # 간단한 이메일 형식 체크 (apply/agent와 동일 정규식)
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return jsonify({"ok": False, "message": "이메일 형식이 올바르지 않습니다."}), 400

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO applications
            (applicant_type, office_or_company_name, owner_name, category,
             biz_reg_number, phone, email, website_url, preferred_region, status,
             reg_number, intro_text, doc_business_card_url, doc_biz_license_url)
        VALUES ('operator', %s, %s, %s, %s, %s, %s, %s, %s, 'submitted',
                NULL, NULL, NULL, NULL)
        RETURNING id
    """, (office_or_company_name, owner_name, category,
          biz_reg_number or None, phone, email,
          website_url or None, preferred_region or None))
    new_id = cur.fetchone()["id"]
    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"ok": True, "id": new_id})


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


# ============================================================
# 관리자(E화면) — admin_users 기반 이메일/비밀번호 로그인 + 건물마스터 CRUD
# 로그인 성공 시 서명된 세션 쿠키에 admin=True, admin_user_id=행 id를 저장한다.
# require_admin 및 /api/admin/* 나머지 API는 session["admin"] 여부만 확인한다.
# ============================================================

def require_admin(f):
    """세션에 admin=True가 없으면 차단한다.
    /api/admin/* 요청은 401 JSON, 그 외(/admin/*)는 /admin/login으로 리다이렉트."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            if request.path.startswith("/api/"):
                return jsonify({"ok": False, "message": "로그인이 필요합니다."}), 401
            return redirect("/admin/login")
        return f(*args, **kwargs)
    return wrapper


def _serve_static_html(filename):
    """정적 HTML을 no-cache 헤더와 함께 서빙 (apply 페이지들과 동일 방식)."""
    html_path = os.path.join(app.static_folder, filename)
    with open(html_path, encoding="utf-8") as fp:
        html = fp.read()
    html = _inject_asset_version(html)
    resp = Response(html, mimetype="text/html")
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp


@app.route("/notices")
def notices_page():
    """공지사항 페이지 (현재는 정적 안내만)."""
    return _serve_static_html("notices.html")


@app.route("/mypage")
def mypage_page():
    """마이페이지 — 로그인 여부는 /api/auth/me로 클라이언트에서 판단한다."""
    return _serve_static_html("mypage.html")


@app.route("/transactions")
def transactions_page():
    """실거래목록 전용 페이지 (검색 필터 + 게시판, /api/transactions 재사용)."""
    return _serve_static_html("transactions.html")


@app.route("/terms")
def terms_page():
    """이용약관 페이지 (정적)."""
    return _serve_static_html("terms.html")


@app.route("/privacy")
def privacy_page():
    """개인정보처리방침 페이지 — 뼈대는 정적, 본문은 /api/legal/privacy에서 로드."""
    return _serve_static_html("privacy.html")


# ---- 약관/개인정보처리방침 (legal_documents) ----
# doc_type은 'terms' 또는 'privacy' 두 값만 허용한다.
_LEGAL_DOC_TYPES = ("terms", "privacy")


@app.route("/api/legal/<doc_type>")
def public_legal_get(doc_type):
    """공개 조회 — 인증 불필요. /terms, /privacy 페이지가 본문을 채울 때 사용."""
    if doc_type not in _LEGAL_DOC_TYPES:
        return jsonify({"ok": False, "message": "존재하지 않는 문서입니다."}), 404
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT content, to_char(updated_at, 'YYYY-MM-DD') AS updated_at "
            "FROM legal_documents WHERE doc_type = %s",
            [doc_type],
        )
        row = cur.fetchone()
    finally:
        cur.close()
        conn.close()
    if not row:
        return jsonify({"ok": False, "message": "존재하지 않는 문서입니다."}), 404
    return jsonify({"ok": True, "doc_type": doc_type,
                    "content": row["content"], "updated_at": row["updated_at"]})


@app.route("/api/admin/legal/<doc_type>")
@require_admin
def admin_legal_get(doc_type):
    """관리자 조회 — 현재 저장된 본문 반환."""
    if doc_type not in _LEGAL_DOC_TYPES:
        return jsonify({"ok": False, "message": "존재하지 않는 문서입니다."}), 404
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT content, to_char(updated_at, 'YYYY-MM-DD HH24:MI') AS updated_at "
            "FROM legal_documents WHERE doc_type = %s",
            [doc_type],
        )
        row = cur.fetchone()
    finally:
        cur.close()
        conn.close()
    if not row:
        return jsonify({"ok": False, "message": "존재하지 않는 문서입니다."}), 404
    return jsonify({"ok": True, "doc_type": doc_type,
                    "content": row["content"], "updated_at": row["updated_at"]})


@app.route("/api/admin/legal/<doc_type>", methods=["PUT"])
@require_admin
def admin_legal_update(doc_type):
    """관리자 저장 — content 통째로 교체. 없으면 새로 만든다(upsert)."""
    if doc_type not in _LEGAL_DOC_TYPES:
        return jsonify({"ok": False, "message": "존재하지 않는 문서입니다."}), 404
    data = request.get_json(force=True, silent=True) or {}
    content = (data.get("content") or "").strip()
    if not content:
        return jsonify({"ok": False, "message": "본문은 비울 수 없습니다."}), 400
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """INSERT INTO legal_documents (doc_type, content, updated_at)
               VALUES (%s, %s, NOW())
               ON CONFLICT (doc_type)
               DO UPDATE SET content = EXCLUDED.content, updated_at = NOW()""",
            [doc_type, content],
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()
    return jsonify({"ok": True})


# =====================================================================
# 일반 회원(users) 인증 — 이메일/비밀번호 + 카카오 소셜 로그인
# 관리자(admin_users / session["admin"])와는 완전히 분리된 세션 키를 쓴다.
#   - 일반 회원 세션 키: session["user_id"]
#   - 관리자 세션 키   : session["admin"]
# =====================================================================

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _valid_email(email):
    return bool(email) and len(email) <= 254 and _EMAIL_RE.match(email) is not None


def current_user():
    """세션의 user_id로 현재 로그인한 일반 회원 행을 돌려준다. 없으면 None."""
    uid = session.get("user_id")
    if not uid:
        return None
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id, email, name, provider FROM users WHERE id = %s AND status <> 'withdrawn'",
            (uid,),
        )
        return cur.fetchone()
    finally:
        cur.close()
        conn.close()


@app.route("/api/auth/signup", methods=["POST"])
@limiter.limit("5 per minute; 20 per hour")
def auth_signup():
    """이메일 회원가입 → 성공 시 자동 로그인."""
    data = request.get_json(force=True, silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    name = (data.get("name") or "").strip()

    if not _valid_email(email):
        return jsonify({"ok": False, "message": "올바른 이메일 형식이 아닙니다."}), 400
    if len(password) < 8:
        return jsonify({"ok": False, "message": "비밀번호는 8자 이상이어야 합니다."}), 400
    if not name:
        return jsonify({"ok": False, "message": "이름을 입력해주세요."}), 400

    pw_hash = generate_password_hash(password)
    conn = get_conn()
    cur = conn.cursor()
    try:
        # 이메일 중복 확인 (대소문자 무시). DB UNIQUE 제약도 있지만 친절한 메시지를 위해 먼저 확인.
        cur.execute("SELECT id FROM users WHERE LOWER(email) = %s", (email,))
        if cur.fetchone():
            return jsonify({"ok": False, "message": "이미 가입된 이메일입니다."}), 400
        cur.execute(
            """INSERT INTO users (email, password_hash, name, provider, last_login_at)
               VALUES (%s, %s, %s, 'email', NOW()) RETURNING id""",
            (email, pw_hash, name),
        )
        new_id = cur.fetchone()["id"]
        conn.commit()
    except Exception:
        conn.rollback()
        # DB UNIQUE 제약 위반 등 → 중복으로 간주(경합 상황 대비)
        return jsonify({"ok": False, "message": "이미 가입된 이메일입니다."}), 400
    finally:
        cur.close()
        conn.close()

    session["user_id"] = new_id
    session.permanent = True
    return jsonify({"ok": True})


@app.route("/api/auth/login", methods=["POST"])
@limiter.limit("5 per minute; 20 per hour")
def auth_login():
    """이메일/비밀번호 로그인. 실패 시 계정 존재 여부를 노출하지 않도록 메시지를 통일한다."""
    data = request.get_json(force=True, silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    fail_msg = "이메일 또는 비밀번호가 올바르지 않습니다."

    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id, password_hash, status FROM users WHERE LOWER(email) = %s",
            (email,),
        )
        row = cur.fetchone()
        # 카카오 전용 가입자(password_hash NULL)·탈퇴 계정은 이메일 로그인 불가 → 동일 메시지로 통일.
        if (not row or not row["password_hash"] or row.get("status") == "withdrawn"
                or not check_password_hash(row["password_hash"], password)):
            return jsonify({"ok": False, "message": fail_msg}), 401
        cur.execute("UPDATE users SET last_login_at = NOW() WHERE id = %s", (row["id"],))
        conn.commit()
        uid = row["id"]
    finally:
        cur.close()
        conn.close()

    session["user_id"] = uid
    session.permanent = True
    return jsonify({"ok": True})


@app.route("/api/auth/logout", methods=["POST"])
def auth_logout():
    """일반 회원 로그아웃 — 관리자 세션은 건드리지 않고 회원 키만 제거한다."""
    session.pop("user_id", None)
    session.pop("kakao_oauth_state", None)
    return jsonify({"ok": True})


@app.route("/api/auth/me")
def auth_me():
    """로그인 상태 조회. 프런트 헤더가 로그인/로그아웃 표시를 결정하는 데 쓴다."""
    u = current_user()
    if not u:
        return jsonify({"logged_in": False})
    return jsonify({
        "logged_in": True,
        "name": u.get("name"),
        "email": u.get("email"),
        "provider": u.get("provider"),
    })


@app.route("/api/auth/me", methods=["PUT"])
@limiter.limit("5 per minute; 20 per hour")
def auth_update_name():
    """이름 변경 — 로그인 필요. 이메일/카카오 공통. name만 바꾼다."""
    u = current_user()
    if not u:
        return jsonify({"ok": False, "message": "로그인이 필요합니다."}), 401
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "message": "이름을 입력해주세요."}), 400
    if len(name) > 50:
        return jsonify({"ok": False, "message": "이름은 50자 이하로 입력해주세요."}), 400

    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE users SET name = %s WHERE id = %s", (name, u["id"]))
        conn.commit()
    finally:
        cur.close()
        conn.close()
    return jsonify({"ok": True, "name": name, "email": u.get("email"), "provider": u.get("provider")})


@app.route("/api/auth/password", methods=["PUT"])
@limiter.limit("5 per minute; 20 per hour")
def auth_change_password():
    """비밀번호 변경 — 로그인 필요, 이메일 계정만. 현재 비밀번호 확인 후 교체."""
    u = current_user()
    if not u:
        return jsonify({"ok": False, "message": "로그인이 필요합니다."}), 401
    if u.get("provider") != "email":
        return jsonify({"ok": False, "message": "카카오 로그인 계정은 비밀번호 변경이 필요 없습니다."}), 400
    data = request.get_json(force=True, silent=True) or {}
    current_pw = data.get("current_password") or ""
    new_pw = data.get("new_password") or ""
    if len(new_pw) < 8:
        return jsonify({"ok": False, "message": "비밀번호는 8자 이상이어야 합니다."}), 400

    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT password_hash FROM users WHERE id = %s", (u["id"],))
        row = cur.fetchone()
        if not row or not row["password_hash"] or not check_password_hash(row["password_hash"], current_pw):
            return jsonify({"ok": False, "message": "현재 비밀번호가 올바르지 않습니다."}), 401
        cur.execute(
            "UPDATE users SET password_hash = %s WHERE id = %s",
            (generate_password_hash(new_pw), u["id"]),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()
    return jsonify({"ok": True})


@app.route("/api/auth/me", methods=["DELETE"])
@limiter.limit("5 per minute; 20 per hour")
def auth_withdraw():
    """회원탈퇴 — 로그인 필요. 완전삭제 대신 status='withdrawn' 소프트삭제 후 세션 초기화."""
    u = current_user()
    if not u:
        return jsonify({"ok": False, "message": "로그인이 필요합니다."}), 401
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE users SET status = 'withdrawn' WHERE id = %s", (u["id"],))
        conn.commit()
    finally:
        cur.close()
        conn.close()
    session.pop("user_id", None)
    session.pop("kakao_oauth_state", None)
    return jsonify({"ok": True})


# ---- 카카오 소셜 로그인 (OAuth 2.0 Authorization Code) ----

_KAKAO_AUTHORIZE_URL = "https://kauth.kakao.com/oauth/authorize"
_KAKAO_TOKEN_URL = "https://kauth.kakao.com/oauth/token"
_KAKAO_USERME_URL = "https://kapi.kakao.com/v2/user/me"


def _kakao_redirect_uri():
    """콜백 URL을 현재 요청 호스트 기준으로 만든다(https 강제).
    카카오 개발자센터의 'Redirect URI'에 이 값이 정확히 등록돼 있어야 한다.
    (개발 도메인·배포 도메인 두 개를 모두 등록하면 양쪽에서 동작)"""
    host = request.host
    return f"https://{host}/auth/kakao/callback"


@app.route("/auth/kakao/start")
def kakao_start():
    """카카오 인증 페이지로 리다이렉트. CSRF 방지용 state를 세션에 저장한다."""
    client_id = os.environ.get("KAKAO_REST_API_KEY", "")
    if not client_id:
        return redirect("/?login_error=1")
    state = _secrets.token_urlsafe(24)
    session["kakao_oauth_state"] = state
    params = {
        "client_id": client_id,
        "redirect_uri": _kakao_redirect_uri(),
        "response_type": "code",
        "state": state,
    }
    return redirect(f"{_KAKAO_AUTHORIZE_URL}?{urlencode(params)}")


@app.route("/auth/kakao/callback")
def kakao_callback():
    """카카오 콜백: code→token→사용자정보→users upsert→세션 저장→홈으로.
    어떤 단계든 실패/거부 시 에러 페이지 대신 홈으로 리다이렉트(?login_error=1)."""
    # 사용자가 동의 취소하면 error 파라미터가 붙어 돌아온다.
    if request.args.get("error"):
        return redirect("/?login_error=1")

    # CSRF: 세션에 저장한 state와 콜백 state가 일치해야 한다. (1회용 → 즉시 제거)
    expected_state = session.pop("kakao_oauth_state", None)
    if not expected_state or request.args.get("state") != expected_state:
        return redirect("/?login_error=1")

    code = request.args.get("code")
    if not code:
        return redirect("/?login_error=1")

    client_id = os.environ.get("KAKAO_REST_API_KEY", "")
    client_secret = os.environ.get("KAKAO_CLIENT_SECRET", "")  # 선택: 카카오 콘솔에서 'client_secret' 사용 설정 시에만 필요
    if not client_id:
        return redirect("/?login_error=1")

    try:
        token_data = {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "redirect_uri": _kakao_redirect_uri(),
            "code": code,
        }
        if client_secret:
            token_data["client_secret"] = client_secret
        tok = requests.post(
            _KAKAO_TOKEN_URL,
            data=token_data,
            headers={"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"},
            timeout=10,
        )
        tok.raise_for_status()
        access_token = tok.json().get("access_token")
        if not access_token:
            return redirect("/?login_error=1")

        me = requests.get(
            _KAKAO_USERME_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        me.raise_for_status()
        me_json = me.json()
    except Exception:
        return redirect("/?login_error=1")

    kakao_id = str(me_json.get("id") or "").strip()
    if not kakao_id:
        return redirect("/?login_error=1")
    account = me_json.get("kakao_account") or {}
    profile = account.get("profile") or {}
    email = (account.get("email") or "").strip().lower() or None
    nickname = (profile.get("nickname") or "").strip() or "카카오회원"

    conn = get_conn()
    cur = conn.cursor()
    try:
        # kakao_id 기준 upsert: 있으면 로그인(마지막 로그인 갱신), 없으면 신규 생성.
        cur.execute("SELECT id, status FROM users WHERE kakao_id = %s", (kakao_id,))
        row = cur.fetchone()
        if row and row.get("status") == "withdrawn":
            # 탈퇴한 카카오 계정은 자동 부활시키지 않는다(로그인 차단).
            conn.rollback()
            return redirect("/?login_error=1")
        if row:
            uid = row["id"]
            cur.execute("UPDATE users SET last_login_at = NOW() WHERE id = %s", (uid,))
        else:
            # 이메일이 이미 이메일가입으로 존재하면 충돌 방지를 위해 email은 비우고 카카오 계정으로 신규 생성.
            email_to_store = email
            if email_to_store:
                cur.execute("SELECT id FROM users WHERE LOWER(email) = %s", (email_to_store,))
                if cur.fetchone():
                    email_to_store = None
            cur.execute(
                """INSERT INTO users (email, password_hash, name, provider, kakao_id, last_login_at)
                   VALUES (%s, NULL, %s, 'kakao', %s, NOW()) RETURNING id""",
                (email_to_store, nickname, kakao_id),
            )
            uid = cur.fetchone()["id"]
        conn.commit()
    except Exception:
        conn.rollback()
        return redirect("/?login_error=1")
    finally:
        cur.close()
        conn.close()

    session["user_id"] = uid
    session.permanent = True
    return redirect("/")


# =====================================================================
# 로그인 회원 관심단지(user_favorites) — 비로그인은 기존 localStorage만 사용.
#   프론트 favKey = "building_name|address" 규칙과 동일하게 (building_name,address)로 저장한다.
#   미매칭(건물명 NULL) 거래는 프론트에서 "null" 문자열로 표현하므로 저장 시 NULL로 정규화한다.
# =====================================================================

def _norm_fav_name(name):
    """프론트 favKey의 건물명 부분을 서버 저장용으로 정규화. "null"/"undefined"/빈값 → None."""
    if name is None:
        return None
    s = str(name).strip()
    if s in ("", "null", "undefined"):
        return None
    return s


@app.route("/api/favorites/mine")
def favorites_mine():
    """로그인 회원의 관심단지 목록 + 각 단지의 최신 실거래가 + 건물상세 링크용 building_id."""
    u = current_user()
    if not u:
        return jsonify({"ok": False, "message": "로그인이 필요합니다."}), 401
    conn = get_conn()
    cur = conn.cursor()
    try:
        # lt: 관심키(건물명+주소)에 해당하는 최신 실거래 1건.
        # bid: 같은 관심키의 거래가 속한 마스터 건물 id (지번 튜플로 master_buildings 역매칭,
        #      같은 지번에 여러 동이면 건물명이 정확히 일치하는 것을 우선).
        cur.execute("""
            SELECT uf.building_name, uf.address, uf.created_at,
                   lt.price, lt.deal_date, lt.area, lt.floor, lt.deal_type,
                   lt.lodging_type, lt.lodging_type_detail,
                   bid.id AS building_id
            FROM user_favorites uf
            LEFT JOIN LATERAL (
                SELECT t.price, t.deal_date, t.area, t.floor, t.deal_type,
                       t.lodging_type, t.lodging_type_detail
                FROM transactions t
                WHERE ((uf.building_name IS NULL AND t.building_name IS NULL)
                       OR t.building_name = uf.building_name)
                  AND t.address = uf.address
                ORDER BY t.deal_date DESC, t.id DESC
                LIMIT 1
            ) lt ON TRUE
            LEFT JOIN LATERAL (
                SELECT mb.id
                FROM transactions t2
                JOIN master_buildings mb
                  ON mb.sgg_cd = t2.sgg_cd AND mb.umd_nm = t2.umd_nm AND mb.jibun = t2.jibun
                WHERE ((uf.building_name IS NULL AND t2.building_name IS NULL)
                       OR t2.building_name = uf.building_name)
                  AND t2.address = uf.address
                ORDER BY (mb.building_name = uf.building_name) DESC NULLS LAST, mb.id
                LIMIT 1
            ) bid ON TRUE
            WHERE uf.user_id = %s
            ORDER BY uf.created_at DESC, uf.id DESC
        """, (u["id"],))
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        cur.close()
        conn.close()
    return jsonify({"ok": True, "items": rows, "total": len(rows)})


@app.route("/api/favorites/mine", methods=["POST"])
def favorites_mine_add():
    """관심단지 1건 저장 — 이미 있으면 무시(중복 스킵)."""
    u = current_user()
    if not u:
        return jsonify({"ok": False, "message": "로그인이 필요합니다."}), 401
    data = request.get_json(force=True, silent=True) or {}
    name = _norm_fav_name(data.get("building_name"))
    addr = (data.get("address") or "").strip()
    if not addr:
        return jsonify({"ok": False, "message": "주소가 필요합니다."}), 400
    conn = get_conn()
    cur = conn.cursor()
    try:
        # 표현식 UNIQUE 인덱스(uq_user_favorites) 기준으로 원자적 dedup — 동시요청 안전
        cur.execute(
            "INSERT INTO user_favorites (user_id, building_name, address) VALUES (%s, %s, %s) "
            "ON CONFLICT (user_id, COALESCE(building_name, ''), address) DO NOTHING",
            (u["id"], name, addr),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()
    return jsonify({"ok": True})


@app.route("/api/favorites/mine", methods=["DELETE"])
def favorites_mine_remove():
    """관심단지 1건 삭제."""
    u = current_user()
    if not u:
        return jsonify({"ok": False, "message": "로그인이 필요합니다."}), 401
    data = request.get_json(force=True, silent=True) or {}
    name = _norm_fav_name(data.get("building_name"))
    addr = (data.get("address") or "").strip()
    if not addr:
        return jsonify({"ok": False, "message": "주소가 필요합니다."}), 400
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "DELETE FROM user_favorites "
            "WHERE user_id = %s AND COALESCE(building_name,'') = COALESCE(%s,'') AND address = %s",
            (u["id"], name, addr),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()
    return jsonify({"ok": True})


@app.route("/api/favorites/migrate", methods=["POST"])
def favorites_migrate():
    """로그인 직후 1회 호출용. localStorage favKey 배열을 받아 없는 것만 채우고,
    합쳐진 최종 관심키 목록을 돌려준다(프론트가 localStorage를 이 값으로 동기화)."""
    u = current_user()
    if not u:
        return jsonify({"ok": False, "message": "로그인이 필요합니다."}), 401
    data = request.get_json(force=True, silent=True) or {}
    keys = data.get("keys") or []
    pairs = []
    if isinstance(keys, list):
        for token in keys:
            if not isinstance(token, str) or "|" not in token:
                continue
            name, addr = token.split("|", 1)
            addr = addr.strip()
            if not addr:
                continue
            pairs.append((_norm_fav_name(name), addr))
    conn = get_conn()
    cur = conn.cursor()
    try:
        for name, addr in pairs:
            # 표현식 UNIQUE 인덱스 기준 원자적 dedup — 동시요청/중복키 안전
            cur.execute(
                "INSERT INTO user_favorites (user_id, building_name, address) VALUES (%s, %s, %s) "
                "ON CONFLICT (user_id, COALESCE(building_name, ''), address) DO NOTHING",
                (u["id"], name, addr),
            )
        conn.commit()
        cur.execute(
            "SELECT building_name, address FROM user_favorites "
            "WHERE user_id = %s ORDER BY created_at ASC, id ASC",
            (u["id"],),
        )
        rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()
    merged = []
    for r in rows:
        nm = r["building_name"]
        merged.append(f"{nm if nm is not None else 'null'}|{r['address']}")
    return jsonify({"ok": True, "keys": merged})


# =====================================================================
# 실거래 알림 구독(user_alert_subscriptions) — user_favorites 와 동일 패턴.
#   관심저장과 독립적으로 켜고 끌 수 있는 별도 테이블. 새 실거래가 들어오면
#   sync_batch.py 가 이 구독을 조회해 notifications 를 만든다.
# =====================================================================

@app.route("/api/alerts/mine")
def alerts_mine():
    """로그인 회원의 실거래 알림 구독 목록 + 각 단지 최신 실거래가 + building_id."""
    u = current_user()
    if not u:
        return jsonify({"ok": False, "message": "로그인이 필요합니다."}), 401
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT us.building_name, us.address, us.created_at,
                   lt.price, lt.deal_date, lt.area, lt.floor, lt.deal_type,
                   lt.lodging_type, lt.lodging_type_detail,
                   bid.id AS building_id
            FROM user_alert_subscriptions us
            LEFT JOIN LATERAL (
                SELECT t.price, t.deal_date, t.area, t.floor, t.deal_type,
                       t.lodging_type, t.lodging_type_detail
                FROM transactions t
                WHERE ((us.building_name IS NULL AND t.building_name IS NULL)
                       OR t.building_name = us.building_name)
                  AND t.address = us.address
                ORDER BY t.deal_date DESC, t.id DESC
                LIMIT 1
            ) lt ON TRUE
            LEFT JOIN LATERAL (
                SELECT mb.id
                FROM transactions t2
                JOIN master_buildings mb
                  ON mb.sgg_cd = t2.sgg_cd AND mb.umd_nm = t2.umd_nm AND mb.jibun = t2.jibun
                WHERE ((us.building_name IS NULL AND t2.building_name IS NULL)
                       OR t2.building_name = us.building_name)
                  AND t2.address = us.address
                ORDER BY (mb.building_name = us.building_name) DESC NULLS LAST, mb.id
                LIMIT 1
            ) bid ON TRUE
            WHERE us.user_id = %s
            ORDER BY us.created_at DESC, us.id DESC
        """, (u["id"],))
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        cur.close()
        conn.close()
    # 프론트가 구독 여부 판정에 쓰는 favKey 목록도 함께 내려준다.
    keys = [f"{(r['building_name'] if r['building_name'] is not None else 'null')}|{r['address']}" for r in rows]
    return jsonify({"ok": True, "items": rows, "keys": keys, "total": len(rows)})


@app.route("/api/alerts/mine", methods=["POST"])
def alerts_mine_add():
    """실거래 알림 구독 1건 추가 — 이미 있으면 무시(중복 스킵)."""
    u = current_user()
    if not u:
        return jsonify({"ok": False, "message": "로그인이 필요합니다."}), 401
    data = request.get_json(force=True, silent=True) or {}
    name = _norm_fav_name(data.get("building_name"))
    addr = (data.get("address") or "").strip()
    if not addr:
        return jsonify({"ok": False, "message": "주소가 필요합니다."}), 400
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO user_alert_subscriptions (user_id, building_name, address) VALUES (%s, %s, %s) "
            "ON CONFLICT (user_id, COALESCE(building_name, ''), address) DO NOTHING",
            (u["id"], name, addr),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()
    return jsonify({"ok": True})


@app.route("/api/alerts/mine", methods=["DELETE"])
def alerts_mine_remove():
    """실거래 알림 구독 1건 삭제."""
    u = current_user()
    if not u:
        return jsonify({"ok": False, "message": "로그인이 필요합니다."}), 401
    data = request.get_json(force=True, silent=True) or {}
    name = _norm_fav_name(data.get("building_name"))
    addr = (data.get("address") or "").strip()
    if not addr:
        return jsonify({"ok": False, "message": "주소가 필요합니다."}), 400
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "DELETE FROM user_alert_subscriptions "
            "WHERE user_id = %s AND COALESCE(building_name,'') = COALESCE(%s,'') AND address = %s",
            (u["id"], name, addr),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()
    return jsonify({"ok": True})


@app.route("/api/alerts/migrate", methods=["POST"])
def alerts_migrate():
    """로그인 직후 1회 호출용. localStorage 알림구독(favKey 배열)을 서버로 이관하고,
    합쳐진 최종 구독키 목록을 돌려준다(프론트가 localStorage를 이 값으로 동기화)."""
    u = current_user()
    if not u:
        return jsonify({"ok": False, "message": "로그인이 필요합니다."}), 401
    data = request.get_json(force=True, silent=True) or {}
    keys = data.get("keys") or []
    pairs = []
    if isinstance(keys, list):
        for token in keys:
            if not isinstance(token, str) or "|" not in token:
                continue
            name, addr = token.split("|", 1)
            addr = addr.strip()
            if not addr:
                continue
            pairs.append((_norm_fav_name(name), addr))
    conn = get_conn()
    cur = conn.cursor()
    try:
        for name, addr in pairs:
            cur.execute(
                "INSERT INTO user_alert_subscriptions (user_id, building_name, address) VALUES (%s, %s, %s) "
                "ON CONFLICT (user_id, COALESCE(building_name, ''), address) DO NOTHING",
                (u["id"], name, addr),
            )
        conn.commit()
        cur.execute(
            "SELECT building_name, address FROM user_alert_subscriptions "
            "WHERE user_id = %s ORDER BY created_at ASC, id ASC",
            (u["id"],),
        )
        rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()
    merged = [f"{(r['building_name'] if r['building_name'] is not None else 'null')}|{r['address']}" for r in rows]
    return jsonify({"ok": True, "keys": merged})


# =====================================================================
# 알림함(notifications) — 헤더 벨 아이콘. 새 실거래 발생 시 sync_batch 가 쌓아둔다.
# =====================================================================

@app.route("/api/notifications/mine")
def notifications_mine():
    """최근 알림 목록 — 안읽음 우선, 최신순, 최대 30개. 클릭 이동용 building_id 포함."""
    u = current_user()
    if not u:
        return jsonify({"ok": False, "message": "로그인이 필요합니다."}), 401
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT n.id, n.title, n.body, n.building_name, n.address,
                   n.is_read, n.created_at,
                   bid.id AS building_id
            FROM notifications n
            LEFT JOIN LATERAL (
                SELECT mb.id
                FROM transactions t2
                JOIN master_buildings mb
                  ON mb.sgg_cd = t2.sgg_cd AND mb.umd_nm = t2.umd_nm AND mb.jibun = t2.jibun
                WHERE ((n.building_name IS NULL AND t2.building_name IS NULL)
                       OR t2.building_name = n.building_name)
                  AND t2.address = n.address
                ORDER BY (mb.building_name = n.building_name) DESC NULLS LAST, mb.id
                LIMIT 1
            ) bid ON TRUE
            WHERE n.user_id = %s
            ORDER BY n.is_read ASC, n.created_at DESC, n.id DESC
            LIMIT 30
        """, (u["id"],))
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        cur.close()
        conn.close()
    return jsonify({"ok": True, "items": rows, "total": len(rows)})


@app.route("/api/notifications/unread-count")
def notifications_unread_count():
    """헤더 벨 뱃지용 안 읽은 알림 개수."""
    u = current_user()
    if not u:
        return jsonify({"ok": False, "message": "로그인이 필요합니다."}), 401
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT COUNT(*) AS c FROM notifications WHERE user_id = %s AND is_read = FALSE",
            (u["id"],),
        )
        c = cur.fetchone()["c"]
    finally:
        cur.close()
        conn.close()
    return jsonify({"ok": True, "count": c})


@app.route("/api/notifications/mine/read-all", methods=["POST"])
def notifications_read_all():
    """전체 읽음 처리."""
    u = current_user()
    if not u:
        return jsonify({"ok": False, "message": "로그인이 필요합니다."}), 401
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE notifications SET is_read = TRUE WHERE user_id = %s AND is_read = FALSE",
            (u["id"],),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()
    return jsonify({"ok": True})


@app.route("/api/notifications/mine/read", methods=["POST"])
def notifications_read_one():
    """알림 1건 읽음 처리 — 항목 클릭 시 사용."""
    u = current_user()
    if not u:
        return jsonify({"ok": False, "message": "로그인이 필요합니다."}), 401
    data = request.get_json(force=True, silent=True) or {}
    nid = data.get("id")
    if not isinstance(nid, int):
        try:
            nid = int(nid)
        except (TypeError, ValueError):
            return jsonify({"ok": False, "message": "알림 id가 필요합니다."}), 400
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE notifications SET is_read = TRUE WHERE id = %s AND user_id = %s",
            (nid, u["id"]),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()
    return jsonify({"ok": True})


@app.route("/admin/login")
def admin_login_page():
    return _serve_static_html("admin_login.html")


@app.route("/api/admin/login", methods=["POST"])
@limiter.limit("5 per minute; 30 per hour")
def admin_login():
    """admin_users 테이블 기반 이메일/비밀번호 로그인.
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
            "SELECT id, password_hash FROM admin_users WHERE email = %s",
            (email,),
        )
        row = cur.fetchone()
        if not row or not row["password_hash"] or not check_password_hash(row["password_hash"], password):
            return fail
        cur.execute("UPDATE admin_users SET last_login_at = NOW() WHERE id = %s", (row["id"],))
        conn.commit()
    finally:
        cur.close()
        conn.close()

    session["admin"] = True
    session["admin_user_id"] = row["id"]
    session.permanent = True
    return jsonify({"ok": True})


@app.route("/api/admin/logout", methods=["POST"])
def admin_logout():
    session.clear()
    return jsonify({"ok": True})


@app.route("/api/admin/password", methods=["PUT"])
@require_admin
@limiter.limit("5 per minute; 20 per hour")
def admin_change_password():
    """관리자 비밀번호 변경 — 로그인 필요. 현재 비밀번호 확인 후 새 비밀번호로 교체."""
    admin_id = session.get("admin_user_id")
    if not admin_id:
        return jsonify({"ok": False, "message": "다시 로그인해주세요."}), 401
    data = request.get_json(force=True, silent=True) or {}
    current_pw = data.get("current_password") or ""
    new_pw = data.get("new_password") or ""
    if len(new_pw) < 8:
        return jsonify({"ok": False, "message": "새 비밀번호는 8자 이상이어야 합니다."}), 400

    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT password_hash FROM admin_users WHERE id = %s", (admin_id,))
        row = cur.fetchone()
        if not row or not row["password_hash"] or not check_password_hash(row["password_hash"], current_pw):
            return jsonify({"ok": False, "message": "현재 비밀번호가 올바르지 않습니다."}), 401
        cur.execute(
            "UPDATE admin_users SET password_hash = %s WHERE id = %s",
            (generate_password_hash(new_pw), admin_id),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()
    return jsonify({"ok": True})


# ============================================================
# 중개사(agents) 로그인 — 승인된 중개사만. admin 로그인과 같은 패턴.
# 세션에 agent_id 저장. require_agent 로 보호.
# ============================================================

def require_agent(f):
    """세션에 agent_id가 없으면 차단한다.
    /api/* 요청은 401 JSON, 그 외는 /agent/login으로 리다이렉트."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("agent_id"):
            if request.path.startswith("/api/"):
                return jsonify({"ok": False, "message": "로그인이 필요합니다."}), 401
            return redirect("/agent/login")
        return f(*args, **kwargs)
    return wrapper


@app.route("/agent/login")
def agent_login_page():
    return _serve_static_html("agent_login.html")


@app.route("/api/agent/login", methods=["POST"])
@limiter.limit("5 per minute; 20 per hour")
def agent_login():
    """agents 테이블 기반 이메일/비밀번호 로그인. status='approved'만 허용.
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
            "SELECT id, password_hash, status FROM agents WHERE LOWER(email) = LOWER(%s)",
            (email,),
        )
        row = cur.fetchone()
        if not row or not row["password_hash"] or not check_password_hash(row["password_hash"], password):
            return fail
        if row["status"] != "approved":
            return jsonify({"ok": False, "message": "승인된 중개사 계정이 아닙니다."}), 403
    finally:
        cur.close()
        conn.close()

    session["agent_id"] = row["id"]
    session.permanent = True
    return jsonify({"ok": True})


@app.route("/api/agent/logout", methods=["POST"])
def agent_logout():
    session.pop("agent_id", None)
    return jsonify({"ok": True})


@app.route("/api/agent/password", methods=["PUT"])
@require_agent
@limiter.limit("5 per minute; 20 per hour")
def agent_change_password():
    """중개사 비밀번호 변경 — 현재 비밀번호 확인 후 교체 (admin/mypage와 같은 패턴)."""
    agent_id = session.get("agent_id")
    data = request.get_json(force=True, silent=True) or {}
    current_pw = data.get("current_password") or ""
    new_pw = data.get("new_password") or ""
    if len(new_pw) < 8:
        return jsonify({"ok": False, "message": "새 비밀번호는 8자 이상이어야 합니다."}), 400

    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT password_hash FROM agents WHERE id = %s", (agent_id,))
        row = cur.fetchone()
        if not row or not row["password_hash"] or not check_password_hash(row["password_hash"], current_pw):
            return jsonify({"ok": False, "message": "현재 비밀번호가 올바르지 않습니다."}), 401
        cur.execute(
            "UPDATE agents SET password_hash = %s WHERE id = %s",
            (generate_password_hash(new_pw), agent_id),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()
    return jsonify({"ok": True})


# ---- 지도 좌표 채우기 (배포 후 운영 DB에 좌표 주입용) ----
# 에이전트/개발자는 운영(production) DB에 직접 쓸 수 없으므로, 개발에서 확보한
# 좌표를 data/building_coords.json 으로 배포에 포함시키고, 관리자가 이 API를
# 호출하면 배포된 앱(=운영 DB 연결)이 id 기준으로 lat/lng 를 채운다.
# id 기준 UPDATE라 여러 번 눌러도 결과가 동일한 idempotent 작업이다.
_COORDS_JSON_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "building_coords.json"
)


def _load_coords_seed():
    """data/building_coords.json → [(id, lat, lng), ...] (형식 오류 행은 건너뜀)."""
    with open(_COORDS_JSON_PATH, encoding="utf-8") as fp:
        rows = json.load(fp)
    out = []
    for r in rows:
        try:
            out.append((int(r["id"]), float(r["lat"]), float(r["lng"])))
        except (KeyError, TypeError, ValueError):
            continue
    return out


@app.route("/api/admin/geocode/status")
@require_admin
def admin_geocode_status():
    """좌표 확보 현황 + 마지막 실행 기록 반환 (관리자 화면 표시용)."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE lat IS NOT NULL AND lng IS NOT NULL) AS with_geo
            FROM master_buildings
        """)
        s = cur.fetchone()
        cur.execute("SELECT value, updated_at FROM app_meta WHERE key = 'geocode_last_run'")
        meta = cur.fetchone()
    finally:
        cur.close()
        conn.close()
    try:
        seed_count = len(_load_coords_seed())
    except Exception:
        seed_count = None
    return jsonify({
        "ok": True,
        "total": s["total"],
        "with_geo": s["with_geo"],
        "seed_count": seed_count,
        "last_run": (meta["value"] if meta else None),
        "last_run_at": (
            meta["updated_at"].strftime("%Y-%m-%d %H:%M")
            if meta and meta["updated_at"] else None
        ),
    })


@app.route("/api/admin/geocode", methods=["POST"])
@require_admin
@limiter.limit("6 per hour")
def admin_geocode_run():
    """data/building_coords.json 의 좌표를 master_buildings 에 id 기준으로 주입.
    값이 실제로 바뀐 행만 세어 반환(재실행 시 0건 → 이미 최신)."""
    try:
        seed = _load_coords_seed()
    except FileNotFoundError:
        return jsonify({"ok": False, "message": "좌표 데이터 파일(data/building_coords.json)을 찾을 수 없습니다."}), 500
    except (json.JSONDecodeError, ValueError):
        return jsonify({"ok": False, "message": "좌표 데이터 파일 형식이 올바르지 않습니다(JSON 파싱 실패)."}), 500
    if not seed:
        return jsonify({"ok": False, "message": "좌표 데이터가 비어 있습니다."}), 400

    conn = get_conn()
    cur = conn.cursor()
    try:
        # 값이 실제로 달라지는 행만 UPDATE → 재실행 시 0건이 나와 idempotent 확인 가능
        execute_values(cur, """
            UPDATE master_buildings AS m
            SET lat = v.lat, lng = v.lng
            FROM (VALUES %s) AS v(id, lat, lng)
            WHERE m.id = v.id
              AND (m.lat IS DISTINCT FROM v.lat OR m.lng IS DISTINCT FROM v.lng)
        """, seed, template="(%s, %s::double precision, %s::double precision)")
        updated = cur.rowcount
        cur.execute("""
            SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE lat IS NOT NULL AND lng IS NOT NULL) AS with_geo
            FROM master_buildings
        """)
        s = cur.fetchone()
        summary = f"{updated}건 갱신 (좌표 확보 {s['with_geo']}/{s['total']}건)"
        cur.execute("""
            INSERT INTO app_meta (key, value, updated_at)
            VALUES ('geocode_last_run', %s, NOW())
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
        """, (summary,))
        conn.commit()
    finally:
        cur.close()
        conn.close()
    return jsonify({
        "ok": True,
        "updated": updated,
        "with_geo": s["with_geo"],
        "total": s["total"],
        "message": summary,
    })


# ---- 실거래 동기화 (관리자 버튼) ----
# 배포된 앱(=운영 DB 연결)에서 sync_runner.py 를 '독립 프로세스'로 띄운다.
# - 요청은 즉시 202 반환(웹 타임아웃 방지), 진행상황은 app_meta('tx_sync_status')에 기록.
# - app_meta UPSERT의 WHERE 조건으로 중복 실행을 원자적으로 차단(멀티 워커에서도 안전).
# - 러너가 30초마다 하트비트(updated_at 갱신) → _SYNC_STALE_MIN 이상 끊기면
#   비정상 종료로 간주하고 재실행을 허용한다.
# - start_new_session=True 라 웹 워커가 재시작/강제종료돼도 러너는 계속 실행되고
#   완료/실패를 스스로 기록한다.
_SYNC_META_KEY = "tx_sync_status"
_SYNC_STALE_MIN = 5  # 하트비트(30초 주기)가 이 시간 이상 끊기면 stale


@app.route("/api/admin/sync-transactions", methods=["POST"])
@require_admin
@limiter.limit("2 per hour")
def admin_sync_run():
    """실거래 동기화 시작. 이미 실행 중이면 409. 시작되면 즉시 202 반환."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) AS c FROM transactions")
        tx_before = cur.fetchone()["c"]
        status = {
            "run_id": _secrets.token_hex(8),  # 실행 식별자 — 이전 러너가 새 실행 상태를 덮어쓰지 못하게 함
            "state": "running",
            "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "finished_at": None,
            "tx_before": tx_before,
            "inserted": None,
            "error": None,
        }
        # 원자적 잠금(DB 기준이라 멀티 워커/인스턴스에서도 전역 일관):
        # - running 인데 하트비트가 살아있으면 차단(중복 실행 방지)
        # - 직전 실행이 성공(done)했으면 30분 재실행 금지(국토부 API 쿼터 보호 —
        #   메모리 기반 rate limit 과 달리 워커/인스턴스가 여러 개여도 전역 강제됨)
        # - 실패(failed)했거나 하트비트가 끊겼으면(비정상 종료) 즉시 재실행 허용
        cur.execute(f"""
            INSERT INTO app_meta (key, value, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
            WHERE ((app_meta.value::jsonb ->> 'state') IS DISTINCT FROM 'running'
                   OR app_meta.updated_at < NOW() - INTERVAL '{int(_SYNC_STALE_MIN)} minutes')
              AND ((app_meta.value::jsonb ->> 'state') IS DISTINCT FROM 'done'
                   OR app_meta.updated_at < NOW() - INTERVAL '30 minutes')
        """, (_SYNC_META_KEY, json.dumps(status, ensure_ascii=False)))
        acquired = cur.rowcount > 0
        prev_state = None
        if not acquired:
            cur.execute("SELECT value FROM app_meta WHERE key = %s", (_SYNC_META_KEY,))
            prev = cur.fetchone()
            try:
                prev_state = json.loads(prev["value"]).get("state") if prev and prev["value"] else None
            except (TypeError, ValueError):
                prev_state = None
        conn.commit()
    finally:
        cur.close()
        conn.close()

    if not acquired:
        if prev_state == "done":
            return jsonify({"ok": False, "message": "직전 동기화가 완료된 지 30분이 지나지 않았습니다. 잠시 후 다시 시도해 주세요."}), 429
        return jsonify({"ok": False, "message": "이미 동기화가 실행 중입니다. 완료 후 다시 시도해 주세요."}), 409

    base_dir = os.path.dirname(os.path.abspath(__file__))
    try:
        proc = subprocess.Popen(
            [sys.executable, "-u", os.path.join(base_dir, "sync_runner.py")],
            cwd=base_dir, start_new_session=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        # 러너 종료 시 좀비 프로세스가 남지 않도록 백그라운드에서 회수
        threading.Thread(target=proc.wait, daemon=True).start()
    except Exception as e:
        status.update({"state": "failed", "error": f"러너 실행 실패: {e}"[:300],
                       "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
        conn = get_conn()
        cur = conn.cursor()
        try:
            cur.execute("""
                INSERT INTO app_meta (key, value, updated_at) VALUES (%s, %s, NOW())
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
            """, (_SYNC_META_KEY, json.dumps(status, ensure_ascii=False)))
            conn.commit()
        finally:
            cur.close()
            conn.close()
        return jsonify({"ok": False, "message": "동기화 프로세스를 시작하지 못했습니다."}), 500

    return jsonify({"ok": True, "message": "동기화를 시작했습니다.", "started_at": status["started_at"]}), 202


@app.route("/api/admin/sync-status")
@require_admin
def admin_sync_status():
    """실거래 동기화 진행상황 + 거래 데이터 현황(총 건수·최근 계약일)."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) AS c, MAX(deal_date) AS md FROM transactions")
        row = cur.fetchone()
        cur.execute("SELECT value, updated_at FROM app_meta WHERE key = %s", (_SYNC_META_KEY,))
        meta = cur.fetchone()
    finally:
        cur.close()
        conn.close()

    status = None
    if meta and meta["value"]:
        try:
            status = json.loads(meta["value"])
        except (TypeError, ValueError):
            status = None

    running = bool(status and status.get("state") == "running")
    stale = False
    if running and meta["updated_at"]:
        age = (datetime.now() - meta["updated_at"]).total_seconds()
        if age > _SYNC_STALE_MIN * 60:
            running, stale = False, True

    inserted = status.get("inserted") if status else None
    if running and status.get("tx_before") is not None:
        # 실행 중에는 시작 시점 대비 증가분을 실시간 표시
        inserted = max(0, row["c"] - status["tx_before"])

    return jsonify({
        "ok": True,
        "running": running,
        "state": ("stale" if stale else (status.get("state") if status else None)),
        "started_at": (status.get("started_at") if status else None),
        "finished_at": (status.get("finished_at") if status else None),
        "inserted": inserted,
        "error": ((status.get("error") if status else None)
                  or ("이전 실행이 비정상 종료된 것으로 보입니다(장시간 응답 없음). 다시 실행할 수 있습니다." if stale else None)),
        "tx_total": row["c"],
        "max_deal_date": (row["md"].strftime("%Y-%m-%d") if hasattr(row["md"], "strftime") else row["md"]) if row["md"] else None,
    })


@app.route("/admin")
@app.route("/admin/")
@require_admin
def admin_page():
    return _serve_static_html("admin.html")


# ---- 건물마스터 CRUD (모두 require_admin) ----
# 정렬 허용 컬럼 화이트리스트 (SQL 인젝션 방지 — 목록에 없으면 id로 폴백)
ADMIN_BLD_SORT = {"id", "building_name", "road_address", "units", "biz_units", "lodging_type"}
# 생성/수정 가능한 컬럼 화이트리스트 (이 목록의 키만 반영)
ADMIN_BLD_EDITABLE = [
    "building_name", "road_address", "jibun_address", "sgg_text", "sgg_cd",
    "umd_nm", "jibun", "units", "biz_units", "lodging_type", "lodging_type_detail",
]
ADMIN_BLD_INT_COLS = {"units", "biz_units"}


def _parse_int_or_none(v):
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


def _clean_bld_value(col, v):
    """편집 컬럼 값을 DB 저장형으로 정규화 (숫자 컬럼은 int/None, 그 외 문자열/None)."""
    if col in ADMIN_BLD_INT_COLS:
        return _parse_int_or_none(v)
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _admin_bld_filters():
    """목록/엑셀 공용: q, sort, order, WHERE절, 파라미터를 계산."""
    q = (request.args.get("q") or "").strip()
    sort = (request.args.get("sort") or "id").strip()
    if sort not in ADMIN_BLD_SORT:
        sort = "id"
    order = "DESC" if (request.args.get("order") or "asc").strip().lower() == "desc" else "ASC"
    where = "1=1"
    params = []
    if q:
        where = "(building_name ILIKE %s OR road_address ILIKE %s)"
        params = [f"%{q}%", f"%{q}%"]
    return q, sort, order, where, params


@app.route("/api/admin/buildings")
@require_admin
def admin_buildings_list():
    q, sort, order, where_sql, params = _admin_bld_filters()
    try:
        page = max(int(request.args.get("page", 1)), 1)
    except (ValueError, TypeError):
        page = 1
    try:
        size = min(max(int(request.args.get("size", 50)), 1), 200)
    except (ValueError, TypeError):
        size = 50
    offset = (page - 1) * size
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(f"SELECT COUNT(*) c FROM master_buildings WHERE {where_sql}", params)
    total = cur.fetchone()["c"]
    # sort/order는 화이트리스트로만 정해지므로 f-string 삽입이 안전하다.
    cur.execute(f"""
        SELECT id, building_name, road_address, jibun_address, sgg_text,
               sgg_cd, umd_nm, jibun, units, biz_units, lodging_type, lodging_type_detail
        FROM master_buildings
        WHERE {where_sql}
        ORDER BY {sort} {order}, id ASC
        LIMIT %s OFFSET %s
    """, params + [size, offset])
    items = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return jsonify({"total": total, "page": page, "size": size, "items": items})


@app.route("/api/admin/buildings", methods=["POST"])
@require_admin
def admin_buildings_create():
    data = request.get_json(force=True, silent=True) or {}
    building_name = (data.get("building_name") or "").strip()
    road_address = (data.get("road_address") or "").strip()
    if not building_name or not road_address:
        return jsonify({"ok": False, "message": "건물명과 도로명주소는 필수입니다."}), 400
    cols, vals = [], []
    for c in ADMIN_BLD_EDITABLE:
        if c in data or c in ("building_name", "road_address"):
            cols.append(c)
            vals.append(_clean_bld_value(c, data.get(c)))
    collist = ", ".join(cols)
    placeholders = ", ".join(["%s"] * len(vals))
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        f"INSERT INTO master_buildings ({collist}) VALUES ({placeholders}) RETURNING id",
        vals,
    )
    new_id = cur.fetchone()["id"]
    # 신규 건물의 좌표를 도로명주소로 즉시 채운다(실패해도 등록은 계속).
    _fill_master_coords(cur, new_id, road_address)
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"ok": True, "id": new_id})


@app.route("/api/admin/buildings/<int:building_id>", methods=["PUT"])
@require_admin
def admin_buildings_update(building_id):
    data = request.get_json(force=True, silent=True) or {}
    sets, vals = [], []
    for c in ADMIN_BLD_EDITABLE:
        if c in data:
            # 필수 컬럼을 빈값으로 지우려는 시도는 막는다.
            if c in ("building_name", "road_address") and not (str(data.get(c) or "").strip()):
                return jsonify({"ok": False, "message": "건물명과 도로명주소는 비울 수 없습니다."}), 400
            sets.append(f"{c} = %s")
            vals.append(_clean_bld_value(c, data.get(c)))
    if not sets:
        return jsonify({"ok": False, "message": "수정할 항목이 없습니다."}), 400
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM master_buildings WHERE id=%s", [building_id])
    if not cur.fetchone():
        cur.close()
        conn.close()
        return jsonify({"ok": False, "message": "존재하지 않는 건물입니다."}), 404
    vals.append(building_id)
    cur.execute(f"UPDATE master_buildings SET {', '.join(sets)} WHERE id = %s", vals)
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/admin/buildings/<int:building_id>", methods=["DELETE"])
@require_admin
def admin_buildings_delete(building_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT sgg_cd, umd_nm, jibun, building_name FROM master_buildings WHERE id=%s",
        [building_id],
    )
    b = cur.fetchone()
    if not b:
        cur.close()
        conn.close()
        return jsonify({"ok": False, "message": "존재하지 않는 건물입니다."}), 404
    # 참조 매물(listings) / 슬롯(slots) — master_building_id FK
    cur.execute("SELECT COUNT(*) c FROM listings WHERE master_building_id=%s", [building_id])
    listing_cnt = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) c FROM slots WHERE master_building_id=%s", [building_id])
    slot_cnt = cur.fetchone()["c"]
    # 참조 실거래(transactions) — 지번키(sgg_cd+umd_nm+jibun) 매칭, 없으면 건물명.
    # umd_nm은 마스터/실거래 간 띄어쓰기 표기가 다를 수 있어(예: '강동면 정동진리' vs
    # '강동면정동진리') REPLACE로 공백을 제거해 정규화 매칭한다. 삭제 가드는 참조를
    # 놓쳐 고아 데이터를 만드는 것보다 넉넉히 잡는 편이 안전하다.
    if b["sgg_cd"] and b["umd_nm"] and b["jibun"]:
        cur.execute(
            "SELECT COUNT(*) c FROM transactions "
            "WHERE sgg_cd=%s AND REPLACE(umd_nm,' ','')=REPLACE(%s,' ','') AND jibun=%s",
            [b["sgg_cd"], b["umd_nm"], b["jibun"]],
        )
        tx_cnt = cur.fetchone()["c"]
    elif b["building_name"] and b["building_name"] != "-":
        cur.execute(
            "SELECT COUNT(*) c FROM transactions WHERE building_name=%s",
            [b["building_name"]],
        )
        tx_cnt = cur.fetchone()["c"]
    else:
        tx_cnt = 0
    if listing_cnt or slot_cnt or tx_cnt:
        parts = []
        if listing_cnt:
            parts.append(f"매물 {listing_cnt}건")
        if slot_cnt:
            parts.append(f"슬롯 {slot_cnt}건")
        if tx_cnt:
            parts.append(f"실거래 {tx_cnt}건")
        cur.close()
        conn.close()
        return jsonify({
            "ok": False,
            "message": "연결된 " + ", ".join(parts) + "이(가) 있어 삭제할 수 없습니다.",
        }), 400
    cur.execute("DELETE FROM master_buildings WHERE id=%s", [building_id])
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/admin/buildings/export.xlsx")
@require_admin
def admin_buildings_export():
    q, sort, order, where_sql, params = _admin_bld_filters()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(f"""
        SELECT id, building_name, road_address, sgg_text, umd_nm, jibun,
               units, biz_units, lodging_type, lodging_type_detail
        FROM master_buildings
        WHERE {where_sql}
        ORDER BY {sort} {order}, id ASC
    """, params)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "건물마스터"
    headers = ["ID", "건물명", "도로명주소", "시군구", "읍면동", "지번",
               "호실수", "영업신고호수", "용도", "용도상세"]
    ws.append(headers)
    for r in rows:
        ws.append([
            r["id"], r["building_name"], r["road_address"], r["sgg_text"],
            r["umd_nm"], r["jibun"], r["units"], r["biz_units"],
            r["lodging_type"], r["lodging_type_detail"],
        ])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    resp = Response(
        buf.read(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp.headers["Content-Disposition"] = "attachment; filename=buildings.xlsx"
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp


# ---- 매물(listings) 관리 (모두 require_admin) ----
# 정렬 허용 컬럼 화이트리스트 → 실제 SQL 표현식 매핑 (인젝션 방지, 없으면 l.id 폴백)
ADMIN_LST_SORT = {
    "id": "l.id", "deal_type": "l.deal_type", "price": "l.price",
    "status": "l.status", "created_at": "l.created_at",
}
# 수정 가능한 컬럼 → 값 형변환 종류
ADMIN_LST_EDITABLE = {
    "deal_type": "text", "price": "int", "monthly_rent": "int",
    "floor": "text", "area": "float", "status": "text",
}


def _parse_float_or_none(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _clean_typed_value(kind, v):
    """editable 화이트리스트의 종류(int/float/text)에 맞춰 DB 저장형으로 정규화."""
    if kind == "int":
        return _parse_int_or_none(v)
    if kind == "float":
        return _parse_float_or_none(v)
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _admin_paging():
    try:
        page = max(int(request.args.get("page", 1)), 1)
    except (ValueError, TypeError):
        page = 1
    try:
        size = min(max(int(request.args.get("size", 50)), 1), 200)
    except (ValueError, TypeError):
        size = 50
    return page, size, (page - 1) * size


def _admin_lst_filters():
    """매물 목록/엑셀 공용: sort_expr, order, WHERE절, 파라미터. 검색은 건물ID로 필터."""
    q = (request.args.get("q") or "").strip()
    sort_key = (request.args.get("sort") or "id").strip()
    sort_expr = ADMIN_LST_SORT.get(sort_key, "l.id")
    order = "DESC" if (request.args.get("order") or "asc").strip().lower() == "desc" else "ASC"
    where = "1=1"
    params = []
    if q.isdigit():
        where = "l.master_building_id = %s"
        params = [int(q)]
    return sort_expr, order, where, params


@app.route("/api/admin/listings")
@require_admin
def admin_listings_list():
    sort_expr, order, where_sql, params = _admin_lst_filters()
    page, size, offset = _admin_paging()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(f"SELECT COUNT(*) c FROM listings l WHERE {where_sql}", params)
    total = cur.fetchone()["c"]
    # sort_expr/order는 화이트리스트로만 정해지므로 f-string 삽입이 안전하다.
    cur.execute(f"""
        SELECT l.id, l.master_building_id, mb.building_name,
               l.deal_type, l.price, l.monthly_rent, l.floor, l.area, l.status,
               to_char(l.created_at, 'YYYY-MM-DD') AS created_at
        FROM listings l
        LEFT JOIN master_buildings mb ON mb.id = l.master_building_id
        WHERE {where_sql}
        ORDER BY {sort_expr} {order}, l.id ASC
        LIMIT %s OFFSET %s
    """, params + [size, offset])
    items = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return jsonify({"total": total, "page": page, "size": size, "items": items})


@app.route("/api/admin/listings/<int:listing_id>", methods=["PUT"])
@require_admin
def admin_listings_update(listing_id):
    data = request.get_json(force=True, silent=True) or {}
    sets, vals = [], []
    for c, kind in ADMIN_LST_EDITABLE.items():
        if c in data:
            sets.append(f"{c} = %s")
            vals.append(_clean_typed_value(kind, data.get(c)))
    if not sets:
        return jsonify({"ok": False, "message": "수정할 항목이 없습니다."}), 400
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM listings WHERE id=%s", [listing_id])
    if not cur.fetchone():
        cur.close()
        conn.close()
        return jsonify({"ok": False, "message": "존재하지 않는 매물입니다."}), 404
    sets.append("updated_at = NOW()")
    vals.append(listing_id)
    cur.execute(f"UPDATE listings SET {', '.join(sets)} WHERE id = %s", vals)
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/admin/listings/<int:listing_id>", methods=["DELETE"])
@require_admin
def admin_listings_delete(listing_id):
    # 매물은 다른 테이블이 참조하지 않으므로 참조 무결성 이슈 없이 바로 삭제한다.
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM listings WHERE id=%s RETURNING id", [listing_id])
    deleted = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    if not deleted:
        return jsonify({"ok": False, "message": "존재하지 않는 매물입니다."}), 404
    return jsonify({"ok": True})


@app.route("/api/admin/listings/export.xlsx")
@require_admin
def admin_listings_export():
    sort_expr, order, where_sql, params = _admin_lst_filters()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(f"""
        SELECT l.id, l.master_building_id, mb.building_name,
               l.deal_type, l.price, l.monthly_rent, l.floor, l.area, l.status,
               to_char(l.created_at, 'YYYY-MM-DD') AS created_at
        FROM listings l
        LEFT JOIN master_buildings mb ON mb.id = l.master_building_id
        WHERE {where_sql}
        ORDER BY {sort_expr} {order}, l.id ASC
    """, params)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "매물"
    ws.append(["ID", "건물ID", "건물명", "거래유형", "가격(만원)", "월세(만원)",
               "층", "면적(㎡)", "상태", "등록일"])
    for r in rows:
        ws.append([
            r["id"], r["master_building_id"], r["building_name"], r["deal_type"],
            r["price"], r["monthly_rent"], r["floor"], r["area"],
            r["status"], r["created_at"],
        ])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    resp = Response(
        buf.read(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp.headers["Content-Disposition"] = "attachment; filename=listings.xlsx"
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp


# ---- 실거래(transactions) 관리 (모두 require_admin) ----
# 실거래는 공공데이터 원본이라 삭제는 만들지 않고, 이상치 정정용 수정만 허용한다.
# 수정 시 반드시 사유(reason)를 받아 admin_edit_log에 필드 단위로 남긴다.
ADMIN_TX_SORT = {"id": "id", "deal_date": "deal_date", "price": "price", "area": "area"}
ADMIN_TX_EDITABLE = {
    "price": "int", "area": "float", "floor": "text",
    "deal_type": "text", "deal_date": "text",
}


def _admin_tx_filters():
    """실거래 목록/엑셀 공용: sort_expr, order, WHERE절, 파라미터. 검색은 건물명·주소."""
    q = (request.args.get("q") or "").strip()
    sort_key = (request.args.get("sort") or "id").strip()
    sort_expr = ADMIN_TX_SORT.get(sort_key, "id")
    order = "DESC" if (request.args.get("order") or "asc").strip().lower() == "desc" else "ASC"
    where = "1=1"
    params = []
    if q:
        where = "(building_name ILIKE %s OR address ILIKE %s)"
        params = [f"%{q}%", f"%{q}%"]
    return sort_expr, order, where, params


@app.route("/api/admin/transactions")
@require_admin
def admin_transactions_list():
    sort_expr, order, where_sql, params = _admin_tx_filters()
    page, size, offset = _admin_paging()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(f"SELECT COUNT(*) c FROM transactions WHERE {where_sql}", params)
    total = cur.fetchone()["c"]
    cur.execute(f"""
        SELECT id, building_name, address, area, floor, price, deal_date, deal_type
        FROM transactions
        WHERE {where_sql}
        ORDER BY {sort_expr} {order}, id ASC
        LIMIT %s OFFSET %s
    """, params + [size, offset])
    items = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return jsonify({"total": total, "page": page, "size": size, "items": items})


@app.route("/api/admin/transactions/<int:tx_id>", methods=["PUT"])
@require_admin
def admin_transactions_update(tx_id):
    data = request.get_json(force=True, silent=True) or {}
    reason = (data.get("reason") or "").strip()
    if not reason:
        return jsonify({"ok": False, "message": "수정 사유(reason)는 필수입니다."}), 400
    # 계약일은 관리자 오입력 방지를 위해 YYYY-MM-DD 형식만 허용한다(데이터 오염 방지).
    if "deal_date" in data:
        dd = (str(data.get("deal_date") or "")).strip()
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", dd):
            return jsonify({"ok": False, "message": "계약일은 YYYY-MM-DD 형식이어야 합니다."}), 400
    # 수정 요청된 편집 컬럼만 추린다.
    changes = {}
    for c, kind in ADMIN_TX_EDITABLE.items():
        if c in data:
            changes[c] = _clean_typed_value(kind, data.get(c))
    if not changes:
        return jsonify({"ok": False, "message": "수정할 항목이 없습니다."}), 400
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        f"SELECT {', '.join(changes.keys())} FROM transactions WHERE id=%s",
        [tx_id],
    )
    old = cur.fetchone()
    if not old:
        cur.close()
        conn.close()
        return jsonify({"ok": False, "message": "존재하지 않는 실거래입니다."}), 404
    # 실제로 값이 달라진 필드만 로그로 남긴다.
    logged = 0
    for field, new_val in changes.items():
        old_val = old[field]
        if str(old_val) == str(new_val):
            continue
        cur.execute(
            """INSERT INTO admin_edit_log
               (table_name, record_id, field, old_value, new_value, reason, admin)
               VALUES (%s, %s, %s, %s, %s, %s, TRUE)""",
            ["transactions", tx_id, field,
             None if old_val is None else str(old_val),
             None if new_val is None else str(new_val),
             reason],
        )
        logged += 1
    sets = [f"{c} = %s" for c in changes]
    vals = list(changes.values()) + [tx_id]
    cur.execute(f"UPDATE transactions SET {', '.join(sets)} WHERE id = %s", vals)
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"ok": True, "logged": logged})


@app.route("/api/admin/transactions/export.xlsx")
@require_admin
def admin_transactions_export():
    sort_expr, order, where_sql, params = _admin_tx_filters()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(f"""
        SELECT id, building_name, address, area, floor, price, deal_date, deal_type
        FROM transactions
        WHERE {where_sql}
        ORDER BY {sort_expr} {order}, id ASC
    """, params)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "실거래"
    ws.append(["ID", "건물명", "주소", "면적(㎡)", "층", "거래금액(만원)",
               "계약일", "거래유형"])
    for r in rows:
        ws.append([
            r["id"], r["building_name"], r["address"], r["area"], r["floor"],
            r["price"], r["deal_date"], r["deal_type"],
        ])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    resp = Response(
        buf.read(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp.headers["Content-Disposition"] = "attachment; filename=transactions.xlsx"
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp


# ---- 공지사항(notices) 관리 (모두 require_admin) ----
# 정렬 허용 컬럼 화이트리스트 (SQL 인젝션 방지 — 없으면 기본 정렬로 폴백)
ADMIN_NOTICE_SORT = {
    "id": "id", "title": "title", "is_pinned": "is_pinned", "created_at": "created_at",
}


def _admin_notice_filters():
    """공지 목록 공용: sort_expr, order, WHERE절, 파라미터. 검색은 제목·본문."""
    q = (request.args.get("q") or "").strip()
    sort_key = (request.args.get("sort") or "").strip()
    sort_expr = ADMIN_NOTICE_SORT.get(sort_key)
    order = "DESC" if (request.args.get("order") or "").strip().lower() == "desc" else "ASC"
    where = "1=1"
    params = []
    if q:
        where = "(title ILIKE %s OR body ILIKE %s)"
        params = [f"%{q}%", f"%{q}%"]
    return sort_expr, order, where, params


def _parse_bool(v):
    """폼/JSON에서 온 다양한 표기('true','1','on', True 등)를 파이썬 bool로."""
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("1", "true", "yes", "on", "y")


@app.route("/api/admin/notices")
@require_admin
def admin_notices_list():
    sort_expr, order, where_sql, params = _admin_notice_filters()
    page, size, offset = _admin_paging()
    # 명시 정렬이 있으면 그걸 우선하되, 기본은 항상 '고정 우선 → 최신순'.
    order_sql = f"{sort_expr} {order}, id DESC" if sort_expr else "is_pinned DESC, created_at DESC, id DESC"
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(f"SELECT COUNT(*) c FROM notices WHERE {where_sql}", params)
    total = cur.fetchone()["c"]
    cur.execute(f"""
        SELECT id, title, body, is_pinned,
               to_char(created_at, 'YYYY-MM-DD') AS created_at,
               to_char(updated_at, 'YYYY-MM-DD') AS updated_at
        FROM notices
        WHERE {where_sql}
        ORDER BY {order_sql}
        LIMIT %s OFFSET %s
    """, params + [size, offset])
    items = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return jsonify({"total": total, "page": page, "size": size, "items": items})


@app.route("/api/admin/notices", methods=["POST"])
@require_admin
def admin_notices_create():
    data = request.get_json(force=True, silent=True) or {}
    title = (data.get("title") or "").strip()
    body = (data.get("body") or "").strip()
    if not title or not body:
        return jsonify({"ok": False, "message": "제목과 본문은 필수입니다."}), 400
    is_pinned = _parse_bool(data.get("is_pinned"))
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO notices (title, body, is_pinned) VALUES (%s, %s, %s) RETURNING id",
        [title, body, is_pinned],
    )
    new_id = cur.fetchone()["id"]
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"ok": True, "id": new_id})


@app.route("/api/admin/notices/<int:notice_id>", methods=["PUT"])
@require_admin
def admin_notices_update(notice_id):
    data = request.get_json(force=True, silent=True) or {}
    sets, vals = [], []
    if "title" in data:
        title = (data.get("title") or "").strip()
        if not title:
            return jsonify({"ok": False, "message": "제목은 비울 수 없습니다."}), 400
        sets.append("title = %s")
        vals.append(title)
    if "body" in data:
        body = (data.get("body") or "").strip()
        if not body:
            return jsonify({"ok": False, "message": "본문은 비울 수 없습니다."}), 400
        sets.append("body = %s")
        vals.append(body)
    if "is_pinned" in data:
        sets.append("is_pinned = %s")
        vals.append(_parse_bool(data.get("is_pinned")))
    if not sets:
        return jsonify({"ok": False, "message": "수정할 항목이 없습니다."}), 400
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM notices WHERE id=%s", [notice_id])
    if not cur.fetchone():
        cur.close()
        conn.close()
        return jsonify({"ok": False, "message": "존재하지 않는 공지입니다."}), 404
    sets.append("updated_at = NOW()")
    vals.append(notice_id)
    cur.execute(f"UPDATE notices SET {', '.join(sets)} WHERE id = %s", vals)
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/admin/notices/<int:notice_id>", methods=["DELETE"])
@require_admin
def admin_notices_delete(notice_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM notices WHERE id=%s RETURNING id", [notice_id])
    deleted = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    if not deleted:
        return jsonify({"ok": False, "message": "존재하지 않는 공지입니다."}), 404
    return jsonify({"ok": True})


# ---- 공지사항 공개 API (로그인 불필요) ----
@app.route("/api/notices")
def get_notices():
    """공개 공지 목록 — 고정 우선 → 최신순. {total, page, size, items} 형태."""
    try:
        page = max(int(request.args.get("page", 1)), 1)
    except (ValueError, TypeError):
        page = 1
    try:
        size = min(max(int(request.args.get("size", 10)), 1), 100)
    except (ValueError, TypeError):
        size = 10
    offset = (page - 1) * size
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) c FROM notices")
    total = cur.fetchone()["c"]
    cur.execute("""
        SELECT id, title, body, is_pinned,
               to_char(created_at, 'YYYY-MM-DD') AS created_at
        FROM notices
        ORDER BY is_pinned DESC, created_at DESC, id DESC
        LIMIT %s OFFSET %s
    """, [size, offset])
    items = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return jsonify({"total": total, "page": page, "size": size, "items": items})


# ---- 신청 승인 큐 (applications, 모두 require_admin) ----
# C/D 화면에서 들어온 중개사/운영업체 신청을 관리자가 승인/반려한다.
# 데이터 정확성 관련: 승인 시 agents/operators로 실제 INSERT되므로 중복 검사 후에만 상태를 바꾼다.
ADMIN_APP_SORT = {"id": "id", "created_at": "submitted_at", "submitted_at": "submitted_at"}


def _admin_app_filters():
    """신청 목록/엑셀 공용: sort_expr, order, WHERE절, 파라미터.
    상태 기본값은 submitted(대기중), status=all이면 전체. applicant_type로 유형 필터.
    검색어는 업체명/대표자/이메일 부분일치."""
    q = (request.args.get("q") or "").strip()
    sort_key = (request.args.get("sort") or "id").strip()
    sort_expr = ADMIN_APP_SORT.get(sort_key, "id")
    order = "DESC" if (request.args.get("order") or "asc").strip().lower() == "desc" else "ASC"
    conds, params = [], []
    status = (request.args.get("status") or "submitted").strip()
    if status and status != "all":
        conds.append("status = %s")
        params.append(status)
    atype = (request.args.get("applicant_type") or "all").strip()
    if atype in ("agent", "operator"):
        conds.append("applicant_type = %s")
        params.append(atype)
    if q:
        conds.append("(office_or_company_name ILIKE %s OR owner_name ILIKE %s OR email ILIKE %s)")
        params += [f"%{q}%", f"%{q}%", f"%{q}%"]
    where = " AND ".join(conds) if conds else "1=1"
    return sort_expr, order, where, params


@app.route("/api/admin/applications")
@require_admin
def admin_applications_list():
    sort_expr, order, where_sql, params = _admin_app_filters()
    page, size, offset = _admin_paging()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(f"SELECT COUNT(*) c FROM applications WHERE {where_sql}", params)
    total = cur.fetchone()["c"]
    cur.execute(f"""
        SELECT id, applicant_type, office_or_company_name, owner_name, reg_number,
               category, phone, email, preferred_region, preferred_building, status, reject_reason,
               to_char(submitted_at, 'YYYY-MM-DD HH24:MI') AS submitted_at
        FROM applications
        WHERE {where_sql}
        ORDER BY {sort_expr} {order}, id ASC
        LIMIT %s OFFSET %s
    """, params + [size, offset])
    items = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return jsonify({"total": total, "page": page, "size": size, "items": items})


@app.route("/api/admin/applications/<int:app_id>/approve", methods=["POST"])
@require_admin
def admin_applications_approve(app_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM applications WHERE id=%s", [app_id])
    ap = cur.fetchone()
    if not ap:
        cur.close()
        conn.close()
        return jsonify({"ok": False, "message": "존재하지 않는 신청입니다."}), 404
    if ap["status"] != "submitted":
        cur.close()
        conn.close()
        return jsonify({"ok": False, "message": "이미 처리된 신청입니다."}), 400

    atype = ap["applicant_type"]
    temp_pw = None
    sms_sent = False
    sms_msg = None
    try:
        if atype == "agent":
            # 등록번호(reg_number) 중복이면 승인 불가 — applications 상태는 그대로 둔다.
            cur.execute("SELECT id FROM agents WHERE reg_number=%s", [ap["reg_number"]])
            if cur.fetchone():
                cur.close()
                conn.close()
                return jsonify({"ok": False, "message": "이미 등록된 중개사무소입니다."}), 400
            # subdomain_slug: 전화번호 숫자만 추출, 중복이면 -2, -3 … 붙여 유니크화.
            # 동시 승인 경쟁 대비: SAVEPOINT + UNIQUE 충돌 시 새 slug로 재시도(최대 5회).
            base_slug = re.sub(r"\D", "", ap["phone"] or "") or f"agent{app_id}"
            # 임시 비밀번호(랜덤 8자리 영숫자) — 해시만 저장
            alphabet = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789"
            temp_pw = "".join(_secrets.choice(alphabet) for _ in range(8))
            pw_hash = generate_password_hash(temp_pw)
            created_id = None
            n = 2
            slug = base_slug
            for _attempt in range(5):
                # 다음 빈 slug 후보 탐색
                while True:
                    cur.execute("SELECT 1 FROM agents WHERE subdomain_slug=%s", [slug])
                    if not cur.fetchone():
                        break
                    slug = f"{base_slug}-{n}"
                    n += 1
                cur.execute("SAVEPOINT sp_agent_insert")
                try:
                    cur.execute("""
                        INSERT INTO agents
                            (office_name, owner_name, reg_number, biz_reg_number,
                             phone, email, status, subdomain_slug, password_hash, approved_at)
                        VALUES (%s, %s, %s, %s, %s, %s, 'approved', %s, %s, NOW())
                        RETURNING id
                    """, [ap["office_or_company_name"], ap["owner_name"], ap["reg_number"],
                          ap["biz_reg_number"], ap["phone"], ap["email"], slug, pw_hash])
                    created_id = cur.fetchone()["id"]
                    cur.execute("RELEASE SAVEPOINT sp_agent_insert")
                    break
                except psycopg2_errors.UniqueViolation as ue:
                    cur.execute("ROLLBACK TO SAVEPOINT sp_agent_insert")
                    cname = getattr(getattr(ue, "diag", None), "constraint_name", "") or ""
                    if "slug" in cname:
                        # 동시 승인으로 slug 선점됨 — 다음 후보로 재시도
                        slug = f"{base_slug}-{n}"
                        n += 1
                        continue
                    raise  # reg_number 등 다른 UNIQUE 충돌은 일반 오류로 처리
            if created_id is None:
                conn.rollback()
                cur.close()
                conn.close()
                return jsonify({"ok": False, "message": "페이지 주소(slug) 발급에 실패했습니다. 다시 시도해주세요."}), 409
            cur.execute(
                "UPDATE applications SET status='approved', reviewed_at=NOW(), linked_agent_id=%s WHERE id=%s",
                [created_id, app_id],
            )
        elif atype == "operator":
            # 운영업체는 이메일 기준 중복 검사. category는 NOT NULL이라 값이 없으면 승인 불가.
            if not (ap["category"] or "").strip():
                cur.close()
                conn.close()
                return jsonify({"ok": False, "message": "업종 정보가 없어 승인할 수 없습니다."}), 400
            cur.execute("SELECT id FROM operators WHERE email=%s", [ap["email"]])
            if cur.fetchone():
                cur.close()
                conn.close()
                return jsonify({"ok": False, "message": "이미 등록된 운영업체입니다."}), 400
            cur.execute("""
                INSERT INTO operators
                    (company_name, owner_name, category, biz_reg_number,
                     phone, email, website_url, status, approved_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'approved', NOW())
                RETURNING id
            """, [ap["office_or_company_name"], ap["owner_name"], ap["category"],
                  ap["biz_reg_number"], ap["phone"], ap["email"], ap["website_url"]])
            created_id = cur.fetchone()["id"]
            cur.execute(
                "UPDATE applications SET status='approved', reviewed_at=NOW(), linked_operator_id=%s WHERE id=%s",
                [created_id, app_id],
            )
        else:
            cur.close()
            conn.close()
            return jsonify({"ok": False, "message": "알 수 없는 신청 유형입니다."}), 400
    except Exception:
        app.logger.exception("신청 승인 처리 실패 (application id=%s)", app_id)
        conn.rollback()
        cur.close()
        conn.close()
        return jsonify({"ok": False, "message": "승인 처리 중 오류가 발생했습니다."}), 400

    conn.commit()
    cur.close()
    conn.close()

    if atype == "agent":
        # 승인 완료 후 문자 발송 — 실패해도 승인은 이미 확정(예외 없음, (ok, msg) 반환)
        domain = request.host_url.rstrip("/")
        sms_body = (
            f"[홈앤스테이] 중개사 승인 완료. 로그인ID(이메일): {ap['email']} / "
            f"임시비밀번호: {temp_pw} / 로그인: {domain}/agent/login — "
            f"최초 로그인 후 반드시 비밀번호를 변경해주세요."
        )
        sms_sent, sms_msg = send_sms(ap["phone"], sms_body)
        resp = {"ok": True, "created_id": created_id, "sms_sent": sms_sent, "sms_message": sms_msg}
        if not sms_sent:
            # 평문 임시비번은 문자 발송 실패 시에만 반환(관리자가 수동 전달하도록)
            resp["temp_password"] = temp_pw
        return jsonify(resp)

    return jsonify({"ok": True, "created_id": created_id})


@app.route("/api/admin/applications/<int:app_id>/reject", methods=["POST"])
@require_admin
def admin_applications_reject(app_id):
    data = request.get_json(force=True, silent=True) or {}
    reason = (data.get("reason") or "").strip()
    if not reason:
        return jsonify({"ok": False, "message": "반려 사유(reason)는 필수입니다."}), 400
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT status FROM applications WHERE id=%s", [app_id])
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        return jsonify({"ok": False, "message": "존재하지 않는 신청입니다."}), 404
    if row["status"] != "submitted":
        cur.close()
        conn.close()
        return jsonify({"ok": False, "message": "이미 처리된 신청입니다."}), 400
    cur.execute(
        "UPDATE applications SET status='rejected', reject_reason=%s, reviewed_at=NOW() WHERE id=%s",
        [reason, app_id],
    )
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/admin/applications/export.xlsx")
@require_admin
def admin_applications_export():
    sort_expr, order, where_sql, params = _admin_app_filters()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(f"""
        SELECT id, applicant_type, office_or_company_name, owner_name, reg_number,
               category, phone, email, preferred_region, preferred_building, status, reject_reason,
               to_char(submitted_at, 'YYYY-MM-DD HH24:MI') AS submitted_at
        FROM applications
        WHERE {where_sql}
        ORDER BY {sort_expr} {order}, id ASC
    """, params)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    type_kr = {"agent": "중개사", "operator": "지원업체"}
    status_kr = {"submitted": "대기중", "approved": "승인됨", "rejected": "반려됨"}
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "신청"
    ws.append(["ID", "신청유형", "이름/업체명", "대표자", "등록번호", "업종",
               "연락처", "이메일", "희망지역", "희망건물", "상태", "반려사유", "신청일"])
    for r in rows:
        ws.append([
            r["id"], type_kr.get(r["applicant_type"], r["applicant_type"]),
            r["office_or_company_name"], r["owner_name"], r["reg_number"],
            r["category"], r["phone"], r["email"], r["preferred_region"],
            r["preferred_building"],
            status_kr.get(r["status"], r["status"]), r["reject_reason"], r["submitted_at"],
        ])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    resp = Response(
        buf.read(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp.headers["Content-Disposition"] = "attachment; filename=applications.xlsx"
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp


# ---- 수정요청 이력 (building_requests, 읽기 전용) ----
# submit_building()에서 건축물대장 재검증으로 이미 자동 승인/거절되므로 관리자 액션은 없다.
# 모니터링용으로 이력만 정렬/검색해서 보여준다.
ADMIN_BREQ_SORT = {
    "id": "id", "created_at": "created_at", "processed_at": "processed_at", "status": "status",
}


def _admin_breq_filters():
    q = (request.args.get("q") or "").strip()
    sort_key = (request.args.get("sort") or "id").strip()
    sort_expr = ADMIN_BREQ_SORT.get(sort_key, "id")
    order = "DESC" if (request.args.get("order") or "asc").strip().lower() == "desc" else "ASC"
    where, params = "1=1", []
    if q:
        where = "(road_address ILIKE %s OR building_name_hint ILIKE %s)"
        params = [f"%{q}%", f"%{q}%"]
    return sort_expr, order, where, params


@app.route("/api/admin/building-requests")
@require_admin
def admin_building_requests_list():
    sort_expr, order, where_sql, params = _admin_breq_filters()
    page, size, offset = _admin_paging()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(f"SELECT COUNT(*) c FROM building_requests WHERE {where_sql}", params)
    total = cur.fetchone()["c"]
    cur.execute(f"""
        SELECT id, request_type, road_address, building_name_hint, status,
               reject_reason, verified_lodging_type,
               to_char(created_at, 'YYYY-MM-DD HH24:MI') AS created_at,
               to_char(processed_at, 'YYYY-MM-DD HH24:MI') AS processed_at
        FROM building_requests
        WHERE {where_sql}
        ORDER BY {sort_expr} {order}, id ASC
        LIMIT %s OFFSET %s
    """, params + [size, offset])
    items = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return jsonify({"total": total, "page": page, "size": size, "items": items})


@app.route("/api/admin/stats")
@require_admin
def admin_stats():
    """관리자 통계 대시보드용 집계(매출 제외). 기존 데이터 집계 + 방문 기록.
    모든 항목을 한 번에 반환한다. 빈 구간(0인 달/날)도 채워서 그래프가 끊기지 않게 한다."""
    conn = get_conn()
    cur = conn.cursor()

    # 1) 실거래: 최근 12개월 월별 거래건수·거래금액(만원) 합계 — 0인 달도 채움
    cur.execute("""
        WITH months AS (
            SELECT to_char(gs, 'YYYY-MM') AS ym
            FROM generate_series(
                date_trunc('month', CURRENT_DATE) - INTERVAL '11 months',
                date_trunc('month', CURRENT_DATE),
                INTERVAL '1 month'
            ) AS gs
        )
        SELECT m.ym AS month,
               COUNT(t.id) AS count,
               COALESCE(SUM(t.price), 0) AS amount
        FROM months m
        LEFT JOIN transactions t ON substring(t.deal_date, 1, 7) = m.ym
        GROUP BY m.ym
        ORDER BY m.ym
    """)
    tx_monthly = [
        {"month": r["month"], "count": int(r["count"]), "amount": int(r["amount"])}
        for r in cur.fetchall()
    ]

    # 2) 용도별(생활/호텔/콘도) 건물 수 분포
    cur.execute("""
        SELECT COALESCE(NULLIF(lodging_type, ''), '미분류') AS lodging_type, COUNT(*) AS count
        FROM master_buildings
        GROUP BY COALESCE(NULLIF(lodging_type, ''), '미분류')
        ORDER BY count DESC
    """)
    building_by_type = [{"lodging_type": r["lodging_type"], "count": int(r["count"])} for r in cur.fetchall()]

    # 3) 시/도별 건물 수 상위 10 (master_buildings.sgg_text의 첫 토큰 = 시/도)
    cur.execute("""
        SELECT split_part(sgg_text, ' ', 1) AS sido, COUNT(*) AS count
        FROM master_buildings
        WHERE sgg_text IS NOT NULL AND sgg_text <> ''
        GROUP BY split_part(sgg_text, ' ', 1)
        ORDER BY count DESC
        LIMIT 10
    """)
    building_by_sido = [{"sido": r["sido"], "count": int(r["count"])} for r in cur.fetchall()]

    # 4) 회원 현황 — 대기중/반려됨은 applications 파이프라인, 승인됨은 실제 등록된 agents/operators 수
    def _member_stats(applicant_type, member_table):
        cur.execute(
            "SELECT COUNT(*) c FROM applications WHERE applicant_type=%s AND status='submitted'",
            [applicant_type],
        )
        pending = int(cur.fetchone()["c"])
        cur.execute(
            "SELECT COUNT(*) c FROM applications WHERE applicant_type=%s AND status='rejected'",
            [applicant_type],
        )
        rejected = int(cur.fetchone()["c"])
        cur.execute(f"SELECT COUNT(*) c FROM {member_table}")
        approved = int(cur.fetchone()["c"])
        return {"pending": pending, "approved": approved, "rejected": rejected}

    members = {
        "agent": _member_stats("agent", "agents"),
        "operator": _member_stats("operator", "operators"),
    }

    # 운영업체 업종별(6개 카테고리) 건수
    cur.execute("""
        SELECT COALESCE(NULLIF(category, ''), '미지정') AS category, COUNT(*) AS count
        FROM operators
        GROUP BY COALESCE(NULLIF(category, ''), '미지정')
        ORDER BY count DESC
    """)
    operator_by_category = [{"category": r["category"], "count": int(r["count"])} for r in cur.fetchall()]

    # 5) 방문: 최근 14일 일별 페이지뷰 — 0인 날도 채움
    cur.execute("""
        WITH days AS (
            SELECT generate_series(CURRENT_DATE - 13, CURRENT_DATE, INTERVAL '1 day')::date AS d
        )
        SELECT to_char(days.d, 'YYYY-MM-DD') AS day, COUNT(pv.id) AS count
        FROM days
        LEFT JOIN page_views pv ON pv.viewed_at::date = days.d
        GROUP BY days.d
        ORDER BY days.d
    """)
    views_daily = [{"day": r["day"], "count": int(r["count"])} for r in cur.fetchall()]

    # 경로별 조회수 상위 5 (오늘 기준)
    cur.execute("""
        SELECT path, COUNT(*) AS count
        FROM page_views
        WHERE viewed_at::date = CURRENT_DATE
        GROUP BY path
        ORDER BY count DESC
        LIMIT 5
    """)
    views_top_paths = [{"path": r["path"], "count": int(r["count"])} for r in cur.fetchall()]

    # 방문 데이터 수집 시작일 (없으면 오늘) — "언제부터 쌓였는지" 안내문구용
    cur.execute("SELECT to_char(MIN(viewed_at), 'YYYY-MM-DD') AS d FROM page_views")
    row = cur.fetchone()
    collect_start = row["d"] if row and row["d"] else datetime.now().strftime("%Y-%m-%d")

    cur.close()
    conn.close()

    return jsonify({
        "transactions": {"monthly": tx_monthly},
        "buildings": {"by_type": building_by_type, "by_sido": building_by_sido},
        "members": members,
        "operators": {"by_category": operator_by_category},
        "views": {"daily": views_daily, "top_paths": views_top_paths, "collect_start": collect_start},
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
