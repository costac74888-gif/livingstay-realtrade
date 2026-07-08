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
        units INTEGER,                -- 호수(세대수) — 정보용, 필터 기준 아님
        biz_units INTEGER,            -- 영업신고호수
        source TEXT DEFAULT 'original' -- 'original'(첨부 마스터파일) | 'api_discovered'(전국 발굴 배치)
    )
    """)
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'original'")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id SERIAL PRIMARY KEY,
        building_name TEXT,           -- 매칭 성공 시 마스터파일 건물명 (NULL이면 미매칭)
        address TEXT NOT NULL,        -- 법정동 + 지번 조합 표시용 주소
        si_do TEXT,                   -- 시/도 (계층 검색용, 마스터의 sgg_text에서 분리)
        sgg_nm TEXT,                  -- 시/군/구 (계층 검색용)
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

    # 기존에 이미 만들어진 DB(컬럼 없이 생성됐던 경우)에도 안전하게 컬럼 추가 (데이터 보존)
    cur.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS si_do TEXT")
    cur.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS sgg_nm TEXT")

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

    _ensure_raw_key_unique_constraint()


def _ensure_raw_key_unique_constraint():
    """
    raw_key에 DB 레벨 UNIQUE 제약을 안전하게 부여한다.
    CREATE TABLE IF NOT EXISTS로 예전에 이미 만들어진 테이블은 스키마에 UNIQUE가 적혀 있어도
    실제 테이블엔 반영 안 됐을 수 있어(IF NOT EXISTS는 이름만 봄) 별도로 확인/적용한다.
    1) 남아있는 중복 raw_key를 먼저 정리(가장 최근 id만 남김)
    2) 제약이 이미 있으면 건너뛰고, 없으면 추가
    """
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        DELETE FROM transactions a USING transactions b
        WHERE a.raw_key = b.raw_key AND a.id < b.id
    """)
    deleted = cur.rowcount

    cur.execute("""
        SELECT tc.constraint_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
        WHERE tc.table_name = 'transactions'
          AND tc.constraint_type = 'UNIQUE'
          AND kcu.column_name = 'raw_key'
    """)
    exists = cur.fetchone()

    if not exists:
        cur.execute("""
            ALTER TABLE transactions
            ADD CONSTRAINT transactions_raw_key_unique UNIQUE (raw_key)
        """)
        print(f"raw_key UNIQUE 제약 신규 적용 완료 (중복 {deleted}건 사전 정리)")
    else:
        print(f"raw_key UNIQUE 제약 이미 존재({exists['constraint_name']}) — 중복 {deleted}건만 정리")

    conn.commit()
    cur.close()
    conn.close()


if __name__ == "__main__":
    init_db()
    print("DB 초기화 완료 (PostgreSQL)")

