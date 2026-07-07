# -*- coding: utf-8 -*-
"""
db.py — SQLite 초기화 및 공용 DB 함수

테이블 구성
------------------------------------------------------------
master_buildings : 첨부 마스터파일(전국 생숙 현황) 원본을 그대로 적재
                    → 건물명 확정의 "정답지" 역할
transactions     : 배치 수집으로 쌓이는 실거래 (매매) 데이터
                    → 게시판/검색 화면이 읽는 테이블
sync_log         : 배치 실행 이력 (언제, 몇 건, 성공/실패)
"""

# -*- coding: utf-8 -*-
"""
db.py — PostgreSQL(Replit 제공 DB) 초기화 및 공용 DB 함수

Replit에서 왼쪽 메뉴 "Database" 탭 → "Create a database" (Postgres) 를 누르면
DATABASE_URL 환경변수(Secret)가 자동으로 주입됩니다. 이 파일은 그 환경변수를 읽어서 접속합니다.

테이블 구성
------------------------------------------------------------
master_buildings : 첨부 마스터파일(전국 생숙 현황) 원본을 그대로 적재
                    → 건물명 확정의 "정답지" 역할
transactions     : 배치 수집으로 쌓이는 실거래 (매매) 데이터
                    → 게시판/검색 화면이 읽는 테이블
sync_log         : 배치 실행 이력 (언제, 몇 건, 성공/실패)
"""

import os
import psycopg2
import psycopg2.extras


def get_conn():
    """
    DATABASE_URL 환경변수(Replit Secrets에 자동 등록됨)로 접속.
    RealDictCursor를 써서 기존 sqlite3.Row처럼 row["컬럼명"]으로 접근 가능하게 함.
    """
    database_url = os.environ["DATABASE_URL"]  # Replit Database 탭에서 Postgres 생성 시 자동 주입
    conn = psycopg2.connect(database_url, cursor_factory=psycopg2.extras.RealDictCursor)
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS master_buildings (
        id SERIAL PRIMARY KEY,
        building_name TEXT NOT NULL,
        road_address TEXT NOT NULL,
        jibun_address TEXT,           -- 도로명→지번 변환 결과 (배치가 채움)
        sgg_text TEXT,                -- "경기도 가평군" 형태
        sgg_cd TEXT,                  -- 법정동코드 앞5자리 (배치가 채움)
        umd_nm TEXT,                  -- 법정동명 (배치가 채움, 매칭 키)
        jibun TEXT,                   -- 지번 (배치가 채움, 매칭 키)
        units INTEGER,                -- 호수(세대수)
        biz_units INTEGER             -- 영업신고호수
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id SERIAL PRIMARY KEY,
        building_name TEXT,           -- 매칭 성공 시 마스터파일 건물명 (NULL이면 미매칭)
        address TEXT NOT NULL,        -- 법정동 + 지번 조합 표시용 주소
        area REAL,                    -- 건물면적(㎡)
        price INTEGER,                -- 거래금액(만원)
        deal_date TEXT,               -- 계약년월일 YYYY-MM-DD
        deal_type TEXT,               -- 중개거래 / 직거래
        sgg_cd TEXT,
        umd_nm TEXT,
        jibun TEXT,
        match_source TEXT,            -- 'master' | 'buildinghub' | 'unmatched'
        raw_key TEXT UNIQUE,          -- 중복 적재 방지용 (sgg_cd+umd_nm+jibun+deal_date+price)
        created_at TIMESTAMP DEFAULT NOW()
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS sync_log (
        id SERIAL PRIMARY KEY,
        started_at TIMESTAMP,
        finished_at TIMESTAMP,
        regions_processed INTEGER,
        rows_inserted INTEGER,
        rows_matched_master INTEGER,
        rows_matched_buildinghub INTEGER,
        rows_unmatched INTEGER,
        status TEXT,
        note TEXT
    )
    """)

    # 검색 성능을 위한 인덱스
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tx_deal_date ON transactions(deal_date DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tx_building_name ON transactions(building_name)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tx_address ON transactions(address)")

    conn.commit()
    cur.close()
    conn.close()


if __name__ == "__main__":
    init_db()
    print("DB 초기화 완료 (PostgreSQL)")

