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
        source TEXT DEFAULT 'original', -- 'original' | 'api_discovered' | 'verify_rescued' | 'sync_verified' | 'user_submitted'
        verified_at TIMESTAMP,         -- is_living_stay로 실검증된 시각 (NULL이면 미검증 → 재분류 대상)
        lodging_type TEXT,             -- '생활' | '호텔' | '콘도' (reclassify가 채움, NULL이면 미분류)
        lodging_type_detail TEXT       -- 건축물대장 원문 용도 표기 (분류 근거, 화면 배지 툴팁용)
    )
    """)
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'original'")
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS verified_at TIMESTAMP")
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS lodging_type TEXT")
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS lodging_type_detail TEXT")
    # 지도 표시용 좌표 (geocode_buildings.py 가 카카오 주소검색으로 채움, NULL 허용)
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS lat DOUBLE PRECISION")
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS lng DOUBLE PRECISION")
    # 정원제 슬롯 최대 정원 (건물당 중개사 노출 좌석 수, 기본 3석)
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS slot_capacity INTEGER DEFAULT 3")

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
        floor TEXT,                   -- 층 (RTMS 응답의 floor 필드, 정보용)
        lodging_type TEXT,            -- '생활' | '호텔' | '콘도' (매칭된 건물 기준, reclassify가 채움)
        lodging_type_detail TEXT,     -- 건축물대장 원문 용도 표기 (배지 툴팁용)
        match_source TEXT,            -- 'master' | 'buildinghub' | 'unmatched'
        raw_key TEXT UNIQUE,          -- 중복 적재 방지용 (sgg_cd+umd_nm+jibun+deal_date+price)
        created_at TIMESTAMP DEFAULT NOW()
    )
    """)

    # 기존에 이미 만들어진 DB(컬럼 없이 생성됐던 경우)에도 안전하게 컬럼 추가 (데이터 보존)
    cur.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS si_do TEXT")
    cur.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS sgg_nm TEXT")
    cur.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS floor TEXT")
    cur.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS lodging_type TEXT")
    cur.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS lodging_type_detail TEXT")

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

    cur.execute("""
    CREATE TABLE IF NOT EXISTS building_requests (
        id SERIAL PRIMARY KEY,
        road_address TEXT NOT NULL,        -- 사용자가 입력한 도로명주소
        building_name_hint TEXT,           -- 사용자가 적어준 건물명 (참고용)
        requester_note TEXT,               -- 사용자 메모
        status TEXT DEFAULT 'pending',     -- pending | verified | rejected
        reject_reason TEXT,                -- 생숙 아님 / 조회실패 등 사유
        master_building_id INTEGER,        -- 검증 통과 시 편입된 master_buildings.id
        created_at TIMESTAMP DEFAULT NOW(),
        processed_at TIMESTAMP
    )
    """)
    # 용도 정정 요청(correction)까지 지원하도록 컬럼 확장 (기존 DB에도 안전하게 추가)
    cur.execute("ALTER TABLE building_requests ADD COLUMN IF NOT EXISTS request_type TEXT DEFAULT 'new'")   # 'new'(신규 추가) | 'correction'(용도 정정)
    cur.execute("ALTER TABLE building_requests ADD COLUMN IF NOT EXISTS target_sgg_cd TEXT")                # 정정 대상 건물 식별용
    cur.execute("ALTER TABLE building_requests ADD COLUMN IF NOT EXISTS target_umd_nm TEXT")
    cur.execute("ALTER TABLE building_requests ADD COLUMN IF NOT EXISTS target_jibun TEXT")
    cur.execute("ALTER TABLE building_requests ADD COLUMN IF NOT EXISTS suggested_lodging_type TEXT")       # 사용자가 제안한 값 (참고용, 신뢰 안 함)
    cur.execute("ALTER TABLE building_requests ADD COLUMN IF NOT EXISTS verified_lodging_type TEXT")        # 우리가 재검증해 확정한 값
    cur.execute("ALTER TABLE building_requests ADD COLUMN IF NOT EXISTS changed BOOLEAN DEFAULT FALSE")     # 정정 요청 시 실제로 값이 바뀌었는지
    cur.execute("ALTER TABLE building_requests ALTER COLUMN road_address DROP NOT NULL")                    # 정정 요청은 도로명주소가 없으므로

    cur.execute("""
    CREATE TABLE IF NOT EXISTS admin_users (
        id SERIAL PRIMARY KEY,
        email TEXT NOT NULL,               -- 로그인 아이디 (UNIQUE 제약은 _ensure_admin_email_unique_constraint()에서 안전하게 부여)
        password_hash TEXT NOT NULL,       -- werkzeug generate_password_hash() 결과 (절대 평문 저장 금지)
        name TEXT,                         -- 표시용 이름
        role TEXT DEFAULT 'operator',      -- 'super_admin' | 'operator'
        created_at TIMESTAMP DEFAULT NOW(),
        last_login_at TIMESTAMP            -- 마지막 로그인 시각 (로그인 API가 채움)
    )
    """)
    # 기존에 이미 만들어진 DB에도 안전하게 컬럼 추가 (데이터 보존)
    cur.execute("ALTER TABLE admin_users ADD COLUMN IF NOT EXISTS name TEXT")
    cur.execute("ALTER TABLE admin_users ADD COLUMN IF NOT EXISTS role TEXT DEFAULT 'operator'")
    cur.execute("ALTER TABLE admin_users ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW()")
    cur.execute("ALTER TABLE admin_users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMP")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS agents (
        id SERIAL PRIMARY KEY,
        office_name TEXT NOT NULL,          -- 중개사무소명
        owner_name TEXT NOT NULL,           -- 대표자명
        reg_number TEXT NOT NULL,           -- 중개사무소 등록번호 (UNIQUE는 _ensure_agents_unique_constraints()에서 안전하게 부여)
        biz_reg_number TEXT,                -- 사업자등록번호
        phone TEXT,
        email TEXT NOT NULL,
        status TEXT DEFAULT 'pending',      -- pending | approved | rejected | suspended
        subdomain_slug TEXT,                -- 승인 시 발급되는 개별페이지 경로 (UNIQUE는 helper에서 부여)
        intro_text TEXT,                    -- 자기소개(선택)
        created_at TIMESTAMP DEFAULT NOW(),
        approved_at TIMESTAMP,
        approved_by INTEGER REFERENCES admin_users(id)   -- 승인한 관리자 (admin_users.id 참조 FK)
    )
    """)
    # 기존에 이미 만들어진 DB에도 안전하게 컬럼 추가 (데이터 보존)
    cur.execute("ALTER TABLE agents ADD COLUMN IF NOT EXISTS biz_reg_number TEXT")
    cur.execute("ALTER TABLE agents ADD COLUMN IF NOT EXISTS phone TEXT")
    cur.execute("ALTER TABLE agents ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'pending'")
    cur.execute("ALTER TABLE agents ADD COLUMN IF NOT EXISTS subdomain_slug TEXT")
    cur.execute("ALTER TABLE agents ADD COLUMN IF NOT EXISTS intro_text TEXT")
    cur.execute("ALTER TABLE agents ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW()")
    cur.execute("ALTER TABLE agents ADD COLUMN IF NOT EXISTS approved_at TIMESTAMP")
    cur.execute("ALTER TABLE agents ADD COLUMN IF NOT EXISTS approved_by INTEGER REFERENCES admin_users(id)")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS operators (
        id SERIAL PRIMARY KEY,
        company_name TEXT NOT NULL,         -- 업체명
        owner_name TEXT NOT NULL,           -- 대표자명
        category TEXT NOT NULL,             -- 위탁운영 | 청소 | 세탁 | 용품 | 대출상담사 | 인테리어
        biz_reg_number TEXT,                -- 사업자등록번호
        phone TEXT,
        email TEXT NOT NULL,
        website_url TEXT,
        status TEXT DEFAULT 'pending',      -- pending | approved | rejected | suspended
        created_at TIMESTAMP DEFAULT NOW(),
        approved_at TIMESTAMP,
        approved_by INTEGER REFERENCES admin_users(id)   -- 승인한 관리자 (admin_users.id 참조 FK)
    )
    """)
    # 기존에 이미 만들어진 DB에도 안전하게 컬럼 추가 (데이터 보존)
    cur.execute("ALTER TABLE operators ADD COLUMN IF NOT EXISTS biz_reg_number TEXT")
    cur.execute("ALTER TABLE operators ADD COLUMN IF NOT EXISTS phone TEXT")
    cur.execute("ALTER TABLE operators ADD COLUMN IF NOT EXISTS website_url TEXT")
    cur.execute("ALTER TABLE operators ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'pending'")
    cur.execute("ALTER TABLE operators ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW()")
    cur.execute("ALTER TABLE operators ADD COLUMN IF NOT EXISTS approved_at TIMESTAMP")
    cur.execute("ALTER TABLE operators ADD COLUMN IF NOT EXISTS approved_by INTEGER REFERENCES admin_users(id)")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS applications (
        id SERIAL PRIMARY KEY,
        applicant_type TEXT NOT NULL,            -- 'agent' | 'operator'
        office_or_company_name TEXT NOT NULL,    -- 중개사무소명 또는 업체명 공용
        owner_name TEXT NOT NULL,
        reg_number TEXT,                         -- 중개사무소 등록번호 (agent만 해당)
        biz_reg_number TEXT,                     -- 사업자등록번호 (공용)
        category TEXT,                           -- 업종 (operator만: 위탁운영/청소/세탁/용품/대출상담사/인테리어)
        phone TEXT NOT NULL,
        email TEXT NOT NULL,
        website_url TEXT,
        preferred_region TEXT,                   -- 희망 지역(선택)
        preferred_building TEXT,                 -- 희망 건물(선택)
        intro_text TEXT,                         -- 자기소개(선택, agent 주로)
        doc_license_url TEXT,                    -- 공인중개사 자격증 사본 (agent)
        doc_office_reg_url TEXT,                 -- 중개사무소 등록증 사본 (agent)
        doc_biz_reg_url TEXT,                    -- 사업자등록증 사본 (공용)
        doc_business_card_url TEXT,              -- 명함 (operator)
        doc_biz_license_url TEXT,                -- 영업허가증 (operator, 업종별 조건부)
        status TEXT DEFAULT 'submitted',         -- submitted | reviewing | approved | rejected
        reject_reason TEXT,
        linked_agent_id INTEGER REFERENCES agents(id),        -- 승인 시 반영된 agents.id (FK)
        linked_operator_id INTEGER REFERENCES operators(id),  -- 승인 시 반영된 operators.id (FK)
        reviewed_by INTEGER REFERENCES admin_users(id),       -- 검토한 관리자 (admin_users.id FK)
        submitted_at TIMESTAMP DEFAULT NOW(),
        reviewed_at TIMESTAMP
    )
    """)
    # 기존에 이미 만들어진 DB에도 안전하게 컬럼 추가 (데이터 보존)
    cur.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS reg_number TEXT")
    cur.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS biz_reg_number TEXT")
    cur.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS category TEXT")
    cur.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS website_url TEXT")
    cur.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS preferred_region TEXT")
    cur.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS preferred_building TEXT")
    cur.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS intro_text TEXT")
    cur.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS doc_license_url TEXT")
    cur.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS doc_office_reg_url TEXT")
    cur.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS doc_biz_reg_url TEXT")
    cur.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS doc_business_card_url TEXT")
    cur.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS doc_biz_license_url TEXT")
    cur.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'submitted'")
    cur.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS reject_reason TEXT")
    cur.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS linked_agent_id INTEGER REFERENCES agents(id)")
    cur.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS linked_operator_id INTEGER REFERENCES operators(id)")
    cur.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS reviewed_by INTEGER REFERENCES admin_users(id)")
    cur.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMP DEFAULT NOW()")
    cur.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMP")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS slots (
        id SERIAL PRIMARY KEY,
        master_building_id INTEGER NOT NULL REFERENCES master_buildings(id),  -- 건물 (FK)
        agent_id INTEGER NOT NULL REFERENCES agents(id),                      -- 중개사 (FK)
        status TEXT DEFAULT 'active',        -- active | waiting | expired
        queue_position INTEGER,              -- status='waiting'일 때 대기 순번, active면 NULL
        monthly_fee INTEGER,                 -- 월 회비(원 단위)
        started_at TIMESTAMP,
        expires_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT NOW()
    )
    """)
    # 기존에 이미 만들어진 DB에도 안전하게 컬럼 추가 (데이터 보존)
    cur.execute("ALTER TABLE slots ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'active'")
    cur.execute("ALTER TABLE slots ADD COLUMN IF NOT EXISTS queue_position INTEGER")
    cur.execute("ALTER TABLE slots ADD COLUMN IF NOT EXISTS monthly_fee INTEGER")
    cur.execute("ALTER TABLE slots ADD COLUMN IF NOT EXISTS started_at TIMESTAMP")
    cur.execute("ALTER TABLE slots ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP")
    cur.execute("ALTER TABLE slots ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW()")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS listings (
        id SERIAL PRIMARY KEY,
        master_building_id INTEGER NOT NULL REFERENCES master_buildings(id),  -- 건물 (FK)
        agent_id INTEGER REFERENCES agents(id),   -- 중개사 (FK, NULL 허용 — 소유주 직접 등록 대비)
        deal_type TEXT NOT NULL,                  -- 매매 | 전세 | 월세
        price INTEGER,                            -- 매매가 또는 보증금(만원 단위)
        monthly_rent INTEGER,                     -- 월세인 경우 월 임대료(만원 단위), 그 외 NULL
        floor TEXT,
        area REAL,                                -- 전용면적(㎡)
        status TEXT DEFAULT 'active',             -- active | completed | hidden
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    )
    """)
    # 기존에 이미 만들어진 DB에도 안전하게 컬럼 추가 (데이터 보존)
    cur.execute("ALTER TABLE listings ADD COLUMN IF NOT EXISTS agent_id INTEGER REFERENCES agents(id)")
    cur.execute("ALTER TABLE listings ADD COLUMN IF NOT EXISTS price INTEGER")
    cur.execute("ALTER TABLE listings ADD COLUMN IF NOT EXISTS monthly_rent INTEGER")
    cur.execute("ALTER TABLE listings ADD COLUMN IF NOT EXISTS floor TEXT")
    cur.execute("ALTER TABLE listings ADD COLUMN IF NOT EXISTS area REAL")
    cur.execute("ALTER TABLE listings ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'active'")
    cur.execute("ALTER TABLE listings ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW()")
    cur.execute("ALTER TABLE listings ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW()")

    # 검색 성능을 위한 인덱스
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tx_deal_date ON transactions(deal_date DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tx_building_name ON transactions(building_name)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tx_address ON transactions(address)")
    # 건물별 슬롯 조회(정원 충족 여부 확인)용 인덱스
    cur.execute("CREATE INDEX IF NOT EXISTS idx_slots_building ON slots(master_building_id)")

    conn.commit()
    cur.close()
    conn.close()

    _ensure_raw_key_unique_constraint()
    _ensure_admin_email_unique_constraint()
    _ensure_agents_unique_constraints()


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


def _ensure_admin_email_unique_constraint():
    """
    admin_users.email에 DB 레벨 UNIQUE 제약을 안전하게 부여한다.
    (_ensure_raw_key_unique_constraint()와 같은 패턴)
    CREATE TABLE IF NOT EXISTS로 예전에 UNIQUE 없이 만들어진 테이블에도 확실히 반영되게 한다.
    1) 중복 email이 있는지 먼저 확인 — 있으면 계정을 함부로 지우지 않고(사용자 데이터 보호)
       경고만 출력하고 제약 부여를 건너뛴다 (raw_key와 달리 자동 삭제하지 않음).
    2) 제약이 이미 있으면 건너뛰고, 없으면 추가.
    """
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT LOWER(email) AS email_l, COUNT(*) AS c
        FROM admin_users
        GROUP BY LOWER(email)
        HAVING COUNT(*) > 1
    """)
    dups = cur.fetchall()

    cur.execute("""
        SELECT tc.constraint_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
        WHERE tc.table_name = 'admin_users'
          AND tc.constraint_type = 'UNIQUE'
          AND kcu.column_name = 'email'
    """)
    exists = cur.fetchone()

    if exists:
        print(f"admin_users.email UNIQUE 제약 이미 존재({exists['constraint_name']})")
    elif dups:
        print(f"[경고] admin_users.email 중복 {len(dups)}건 발견 — 계정 자동 삭제하지 않고 UNIQUE 제약 부여를 건너뜁니다. 수동 정리 후 재실행하세요.")
    else:
        cur.execute("""
            ALTER TABLE admin_users
            ADD CONSTRAINT admin_users_email_unique UNIQUE (email)
        """)
        print("admin_users.email UNIQUE 제약 신규 적용 완료")

    conn.commit()
    cur.close()
    conn.close()


def _ensure_agents_unique_constraints():
    """
    agents.reg_number, agents.subdomain_slug에 DB 레벨 UNIQUE 제약을 안전하게 부여한다.
    (_ensure_admin_email_unique_constraint()와 같은 패턴)
    - 중복 값이 있으면 계정/신청 데이터를 함부로 지우지 않고 경고만 출력하고 건너뛴다.
    - 제약이 이미 있으면 skip, 없으면 add. (재실행 안전)
    - subdomain_slug는 NULL 허용(미승인 상태)이며, PostgreSQL UNIQUE는 NULL 다중 허용이라 문제 없음.
    """
    conn = get_conn()
    cur = conn.cursor()

    targets = [
        ("reg_number", "agents_reg_number_unique"),
        ("subdomain_slug", "agents_subdomain_slug_unique"),
    ]
    for column, constraint_name in targets:
        cur.execute(f"""
            SELECT {column} AS v, COUNT(*) AS c
            FROM agents
            WHERE {column} IS NOT NULL
            GROUP BY {column}
            HAVING COUNT(*) > 1
        """)
        dups = cur.fetchall()

        cur.execute("""
            SELECT tc.constraint_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
            WHERE tc.table_name = 'agents'
              AND tc.constraint_type = 'UNIQUE'
              AND kcu.column_name = %s
        """, (column,))
        exists = cur.fetchone()

        if exists:
            print(f"agents.{column} UNIQUE 제약 이미 존재({exists['constraint_name']})")
        elif dups:
            print(f"[경고] agents.{column} 중복 {len(dups)}건 발견 — 데이터 자동 삭제하지 않고 UNIQUE 제약 부여를 건너뜁니다. 수동 정리 후 재실행하세요.")
        else:
            cur.execute(f"ALTER TABLE agents ADD CONSTRAINT {constraint_name} UNIQUE ({column})")
            print(f"agents.{column} UNIQUE 제약 신규 적용 완료")

    conn.commit()
    cur.close()
    conn.close()


if __name__ == "__main__":
    init_db()
    print("DB 초기화 완료 (PostgreSQL)")

