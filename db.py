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
from werkzeug.security import generate_password_hash


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
    # 건축물대장 표제부(getBrTitleInfo) 백필값 — backfill_title_info.py가 채운다.
    # 값이 NULL이면 건물 상세 화면에서 "-"로 표시된다.
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS use_apr_day TEXT")        # 사용승인일(준공) YYYY-MM-DD
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS tot_pkng_cnt INTEGER")    # 총주차대수
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS grnd_flr_cnt INTEGER")    # 지상층수
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS ugrnd_flr_cnt INTEGER")   # 지하층수
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS tot_area DOUBLE PRECISION")  # 연면적(㎡)
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS plat_area DOUBLE PRECISION") # 대지면적(㎡)
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS hhld_cnt INTEGER")        # 세대수
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS strct_nm TEXT")           # 구조
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS title_backfilled_at TIMESTAMP")  # 표제부 백필 시각(재시도/커버리지 추적)

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

    # 관리자 수정 감사 로그 — 실거래(공공데이터 원본)처럼 함부로 고치면 안 되는 값을
    # 정정할 때 old/new 값과 사유(reason)를 필드 단위로 남긴다.
    cur.execute("""
    CREATE TABLE IF NOT EXISTS admin_edit_log (
        id SERIAL PRIMARY KEY,
        table_name TEXT NOT NULL,        -- 수정 대상 테이블명 (예: transactions)
        record_id INTEGER NOT NULL,      -- 수정된 행의 id
        field TEXT NOT NULL,             -- 수정된 컬럼명
        old_value TEXT,                  -- 수정 전 값 (문자열로 보관)
        new_value TEXT,                  -- 수정 후 값 (문자열로 보관)
        reason TEXT NOT NULL,            -- 관리자가 입력한 수정 사유 (필수)
        admin BOOLEAN DEFAULT TRUE,      -- 관리자 권한으로 수정했는지 여부
        edited_at TIMESTAMP DEFAULT NOW()
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS mileage_missions (
        id SERIAL PRIMARY KEY,
        code TEXT NOT NULL,              -- 예: photo_exterior, admin_consent (UNIQUE는 helper에서 안전하게 부여)
        title TEXT NOT NULL,             -- 예: 건물 외관 사진
        points INTEGER NOT NULL,
        tier TEXT DEFAULT 'basic',       -- basic | top | top2 (★, ★★ 구분)
        active BOOLEAN DEFAULT TRUE
    )
    """)
    # 기존에 이미 만들어진 DB에도 안전하게 컬럼 추가 (데이터 보존)
    cur.execute("ALTER TABLE mileage_missions ADD COLUMN IF NOT EXISTS tier TEXT DEFAULT 'basic'")
    cur.execute("ALTER TABLE mileage_missions ADD COLUMN IF NOT EXISTS active BOOLEAN DEFAULT TRUE")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS mileage_submissions (
        id SERIAL PRIMARY KEY,
        agent_id INTEGER NOT NULL REFERENCES agents(id),                 -- 중개사 (FK)
        mission_id INTEGER NOT NULL REFERENCES mileage_missions(id),     -- 미션 (FK)
        master_building_id INTEGER REFERENCES master_buildings(id),      -- 건물 (FK, NULL 허용)
        photo_urls TEXT,                 -- JSON 문자열로 여러 장 저장(우선 TEXT, 나중에 JSONB 검토)
        status TEXT DEFAULT 'pending',   -- pending | verified | rejected
        points_awarded INTEGER,
        submitted_at TIMESTAMP DEFAULT NOW(),
        reviewed_at TIMESTAMP,
        reviewed_by INTEGER REFERENCES admin_users(id)                   -- 검토한 관리자 (FK)
    )
    """)
    # 기존에 이미 만들어진 DB에도 안전하게 컬럼 추가 (데이터 보존)
    cur.execute("ALTER TABLE mileage_submissions ADD COLUMN IF NOT EXISTS master_building_id INTEGER REFERENCES master_buildings(id)")
    cur.execute("ALTER TABLE mileage_submissions ADD COLUMN IF NOT EXISTS photo_urls TEXT")
    cur.execute("ALTER TABLE mileage_submissions ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'pending'")
    cur.execute("ALTER TABLE mileage_submissions ADD COLUMN IF NOT EXISTS points_awarded INTEGER")
    cur.execute("ALTER TABLE mileage_submissions ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMP DEFAULT NOW()")
    cur.execute("ALTER TABLE mileage_submissions ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMP")
    cur.execute("ALTER TABLE mileage_submissions ADD COLUMN IF NOT EXISTS reviewed_by INTEGER REFERENCES admin_users(id)")

    # 방문 기록(페이지뷰) — 통계 대시보드용. 개인정보 최소수집: 원본 IP 대신 salt 해시만 저장.
    cur.execute("""
    CREATE TABLE IF NOT EXISTS page_views (
        id SERIAL PRIMARY KEY,
        path TEXT NOT NULL,                -- 조회한 사용자 페이지 경로 (/ , /building/<id> 등)
        ip_hash TEXT,                      -- sha256(방문자IP + 고정 salt) — 원본 IP는 저장 안 함
        user_agent TEXT,                   -- 브라우저 UA 문자열 (참고용)
        viewed_at TIMESTAMP DEFAULT NOW()
    )
    """)

    # 일반 회원 — 이메일/비밀번호 또는 카카오 소셜 로그인. (관리자 admin_users와는 별개 테이블)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        email TEXT,                        -- 로그인 아이디. UNIQUE는 _ensure_users_unique_constraints()에서 부여
        password_hash TEXT,                -- werkzeug 해시. 카카오 전용 가입자는 NULL(비밀번호 없음)
        name TEXT,                         -- 표시용 이름/닉네임
        provider TEXT DEFAULT 'email',     -- 'email' | 'kakao'
        kakao_id TEXT,                     -- 카카오 회원번호. UNIQUE는 helper에서 부여(NULL 허용)
        created_at TIMESTAMP DEFAULT NOW(),
        last_login_at TIMESTAMP,           -- 마지막 로그인 시각 (로그인 시 갱신)
        status TEXT DEFAULT 'active'       -- 'active' | 'withdrawn'(회원탈퇴 소프트삭제)
    )
    """)
    # 기존에 이미 만들어진 DB에도 안전하게 컬럼 추가 (데이터 보존)
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT")
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS name TEXT")
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS provider TEXT DEFAULT 'email'")
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS kakao_id TEXT")
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW()")
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMP")
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'active'")

    # 로그인 회원의 관심단지 — 프론트 localStorage favKey(building_name|address)와 동일 규칙으로 저장.
    #   - building_name: 매칭 성공 시 건물명. 미매칭 거래는 NULL(프론트 favKey의 "null"과 대응).
    #   - (user_id, building_name, address) 조합은 유일(중복 저장 방지). NULL 비교 이슈를 피하려고
    #     COALESCE(building_name,'') 를 쓰는 표현식 UNIQUE 인덱스로 부여한다.
    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_favorites (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        building_name TEXT,                -- 매칭 성공 시 건물명, 미매칭이면 NULL
        address TEXT NOT NULL,             -- 법정동+지번 조합 표시용 주소 (transactions.address와 동일)
        created_at TIMESTAMP DEFAULT NOW()
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_user_favorites_user ON user_favorites(user_id)")
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_user_favorites "
        "ON user_favorites (user_id, COALESCE(building_name, ''), address)"
    )

    # 실거래 알림 구독 — user_favorites 와 구조는 같지만 별도 테이블(관심저장과 독립적으로
    # 켜고 끌 수 있어야 함). 새 실거래가 들어오면 sync_batch 가 이 구독을 조회해 notifications 를 만든다.
    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_alert_subscriptions (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        building_name TEXT,                -- 매칭 성공 시 건물명, 미매칭이면 NULL
        address TEXT NOT NULL,             -- transactions.address 와 동일 규칙(법정동+지번)
        created_at TIMESTAMP DEFAULT NOW()
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_user_alert_subs_user ON user_alert_subscriptions(user_id)")
    # 새 실거래 매칭 조회용(주소+건물명) 인덱스
    cur.execute("CREATE INDEX IF NOT EXISTS idx_user_alert_subs_match ON user_alert_subscriptions(address)")
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_user_alert_subs "
        "ON user_alert_subscriptions (user_id, COALESCE(building_name, ''), address)"
    )

    # 알림함 — 새 실거래 발생 시 구독자별로 1건씩 쌓인다. 헤더 벨 아이콘이 읽어간다.
    #   transaction_id: 어떤 실거래로 만든 알림인지(같은 거래로 같은 사용자에게 중복 생성 방지).
    cur.execute("""
    CREATE TABLE IF NOT EXISTS notifications (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        title TEXT NOT NULL,
        body TEXT,
        building_name TEXT,
        address TEXT,
        transaction_id INTEGER,            -- 원본 실거래 id (수동 생성 알림이면 NULL)
        is_read BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT NOW()
    )
    """)
    # 헤더 벨: 안읽음 우선 + 최신순 조회용 인덱스
    cur.execute("CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, is_read, created_at DESC)")
    # 같은 거래로 같은 사용자에게 알림 중복 생성 방지.
    #   transaction_id 가 NULL(수동 생성)인 행은 Postgres 에서 NULL 끼리 서로 다르게 취급되어
    #   유니크 제약에 걸리지 않는다 → 전체 유니크 인덱스로 둬도 문제없음(부분 인덱스면 ON CONFLICT 불가).
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_notifications_user_tx "
        "ON notifications (user_id, transaction_id)"
    )

    # 지자체(시군구)별 생활숙박시설 담당부서·연락처 (엑셀 원본 그대로 적재)
    # region_name_raw 는 가공하지 않은 엑셀 '지자체' 값 그대로 보존한다("진주시(중복)" 포함).
    # 매칭은 address_utils.match_authority_contact() 가 이 원본을 정규화해서 수행한다.
    cur.execute("""
    CREATE TABLE IF NOT EXISTS lodging_authority_contacts (
        id SERIAL PRIMARY KEY,
        region_name_raw TEXT NOT NULL,     -- 엑셀 '지자체' 원본 그대로
        dept TEXT,                         -- 담당부서
        phone TEXT,                        -- 전화번호
        created_at TIMESTAMP DEFAULT NOW()
    )
    """)

    # 공지사항 — 관리자가 등록하고 공개 페이지(/notices)가 읽는다.
    cur.execute("""
    CREATE TABLE IF NOT EXISTS notices (
        id SERIAL PRIMARY KEY,
        title TEXT NOT NULL,
        body TEXT NOT NULL,
        is_pinned BOOLEAN DEFAULT FALSE,     -- 상단 고정 여부 (고정글이 최신글보다 먼저 노출)
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    )
    """)
    # 기존에 이미 만들어진 DB에도 안전하게 컬럼 추가 (데이터 보존)
    cur.execute("ALTER TABLE notices ADD COLUMN IF NOT EXISTS is_pinned BOOLEAN DEFAULT FALSE")
    cur.execute("ALTER TABLE notices ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW()")
    cur.execute("ALTER TABLE notices ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW()")

    # 검색 성능을 위한 인덱스
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tx_deal_date ON transactions(deal_date DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tx_building_name ON transactions(building_name)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tx_address ON transactions(address)")
    # 건물별 슬롯 조회(정원 충족 여부 확인)용 인덱스
    cur.execute("CREATE INDEX IF NOT EXISTS idx_slots_building ON slots(master_building_id)")
    # 건물별 매물 조회용 인덱스
    cur.execute("CREATE INDEX IF NOT EXISTS idx_listings_building ON listings(master_building_id)")
    # 통계(일별 방문 집계)용 인덱스
    cur.execute("CREATE INDEX IF NOT EXISTS idx_page_views_viewed_at ON page_views(viewed_at)")
    # 공지사항 정렬(고정 우선 → 최신순)용 인덱스
    cur.execute("CREATE INDEX IF NOT EXISTS idx_notices_order ON notices(is_pinned DESC, created_at DESC)")

    conn.commit()
    cur.close()
    conn.close()

    _ensure_raw_key_unique_constraint()
    _ensure_admin_email_unique_constraint()
    _ensure_agents_unique_constraints()
    _ensure_mileage_missions_code_unique_constraint()
    _ensure_users_unique_constraints()
    _seed_mileage_missions()
    _seed_admin_user()


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


def _ensure_users_unique_constraints():
    """
    users.email, users.kakao_id에 DB 레벨 UNIQUE 제약을 안전하게 부여한다.
    (_ensure_agents_unique_constraints()와 같은 패턴)
    - 중복 값이 있으면 회원 계정을 함부로 지우지 않고(사용자 데이터 보호) 경고만 출력하고 건너뛴다.
    - 제약이 이미 있으면 skip, 없으면 add. (재실행 안전)
    - email은 대소문자 무시 중복 확인(LOWER). kakao_id는 NULL 허용이며 PostgreSQL UNIQUE는 NULL 다중 허용이라 문제 없음.
      (이메일 가입자는 kakao_id가 NULL이라 서로 충돌하지 않음)
    """
    conn = get_conn()
    cur = conn.cursor()

    targets = [
        ("email", "LOWER(email)", "users_email_unique", "email"),
        ("kakao_id", "kakao_id", "users_kakao_id_unique", "kakao_id"),
    ]
    for label, dup_expr, constraint_name, column in targets:
        cur.execute(f"""
            SELECT {dup_expr} AS v, COUNT(*) AS c
            FROM users
            WHERE {column} IS NOT NULL
            GROUP BY {dup_expr}
            HAVING COUNT(*) > 1
        """)
        dups = cur.fetchall()

        cur.execute("""
            SELECT tc.constraint_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
            WHERE tc.table_name = 'users'
              AND tc.constraint_type = 'UNIQUE'
              AND kcu.column_name = %s
        """, (column,))
        exists = cur.fetchone()

        if exists:
            print(f"users.{label} UNIQUE 제약 이미 존재({exists['constraint_name']})")
        elif dups:
            print(f"[경고] users.{label} 중복 {len(dups)}건 발견 — 계정 자동 삭제하지 않고 UNIQUE 제약 부여를 건너뜁니다. 수동 정리 후 재실행하세요.")
        else:
            cur.execute(f"ALTER TABLE users ADD CONSTRAINT {constraint_name} UNIQUE ({column})")
            print(f"users.{label} UNIQUE 제약 신규 적용 완료")

    conn.commit()
    cur.close()
    conn.close()


def _ensure_mileage_missions_code_unique_constraint():
    """
    mileage_missions.code에 DB 레벨 UNIQUE 제약을 안전하게 부여한다.
    (_ensure_agents_unique_constraints()와 같은 패턴)
    - 중복 code가 있으면 정책 데이터를 함부로 지우지 않고 경고만 출력하고 건너뛴다.
    - 제약이 이미 있으면 skip, 없으면 add. (재실행 안전)
    - 이 제약은 _seed_mileage_missions()의 ON CONFLICT (code) 동작에 필요하므로 시드보다 먼저 실행된다.
    """
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT code, COUNT(*) AS c
        FROM mileage_missions
        WHERE code IS NOT NULL
        GROUP BY code
        HAVING COUNT(*) > 1
    """)
    dups = cur.fetchall()

    cur.execute("""
        SELECT tc.constraint_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
        WHERE tc.table_name = 'mileage_missions'
          AND tc.constraint_type = 'UNIQUE'
          AND kcu.column_name = 'code'
    """)
    exists = cur.fetchone()

    if exists:
        print(f"mileage_missions.code UNIQUE 제약 이미 존재({exists['constraint_name']})")
    elif dups:
        print(f"[경고] mileage_missions.code 중복 {len(dups)}건 발견 — 데이터 자동 삭제하지 않고 UNIQUE 제약 부여를 건너뜁니다. 수동 정리 후 재실행하세요.")
    else:
        cur.execute("ALTER TABLE mileage_missions ADD CONSTRAINT mileage_missions_code_unique UNIQUE (code)")
        print("mileage_missions.code UNIQUE 제약 신규 적용 완료")

    conn.commit()
    cur.close()
    conn.close()


def _seed_mileage_missions():
    """
    미션 정의(정책 테이블) 초기 데이터를 삽입한다.
    - code 기준 ON CONFLICT DO NOTHING이라 이미 있으면 중복 삽입되지 않는다 (재실행 안전).
    - ON CONFLICT (code)는 code UNIQUE 제약이 있어야 동작한다. 보통은
      _ensure_mileage_missions_code_unique_constraint()에서 미리 걸리지만,
      레거시 중복 데이터 때문에 제약 부여가 건너뛰어졌을 수 있으므로 여기서도
      제약 존재를 먼저 확인하고, 없으면 시드를 안전하게 건너뛴다(에러로 init_db 중단 방지).
    """
    missions = [
        ("photo_exterior", "건물 외관 사진", 20, "basic"),
        ("photo_building_id", "건축물 표시(문패·집합건축물대장 확인용)", 20, "basic"),
        ("gps_tag", "GPS 좌표 태깅", 10, "basic"),
        ("operation_type_check", "운영 형태 확인", 15, "basic"),
        ("management_office_info", "관리사무소·법인 안내판", 10, "basic"),
        ("surroundings_memo", "주변 환경 메모", 5, "basic"),
        ("admin_consent", "건물 관리자 개인정보 이용동의 수집", 150, "top"),
        ("biz_license_confirm", "숙박업 영업신고증 확인", 220, "top2"),
    ]
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT 1
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
        WHERE tc.table_name = 'mileage_missions'
          AND tc.constraint_type = 'UNIQUE'
          AND kcu.column_name = 'code'
    """)
    if not cur.fetchone():
        print("[경고] mileage_missions.code UNIQUE 제약이 없어 시드를 건너뜁니다. code 중복 정리 후 재실행하세요.")
        cur.close()
        conn.close()
        return

    cur.executemany("""
        INSERT INTO mileage_missions (code, title, points, tier)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (code) DO NOTHING
    """, missions)
    inserted = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()
    print(f"mileage_missions 시드 완료 (신규 {inserted}건 삽입, 총 {len(missions)}건 정의)")


def _seed_admin_user():
    """
    최초 관리자 계정 1건을 시드한다 (email='ADMIN' / password='ADMIN').
    - admin_users에 행이 하나라도 있으면 아무것도 하지 않는다(기존 계정 절대 덮어쓰기 금지).
    - 완전히 비어 있을 때만 딱 1건 생성한다 (재실행 안전).
    - 초기 비밀번호는 반드시 로그인 후 '비밀번호 변경'으로 교체하도록 안내한다.
    """
    conn = get_conn()
    cur = conn.cursor()
    try:
        # WHERE NOT EXISTS로 "테이블이 완전히 비었을 때만" 원자적으로 1건 삽입한다.
        # (동시 초기화 시에도 경쟁 상태 없이 안전 — 이미 행이 있으면 0건 삽입)
        cur.execute(
            """INSERT INTO admin_users (email, password_hash, name, role)
               SELECT %s, %s, %s, %s
               WHERE NOT EXISTS (SELECT 1 FROM admin_users)""",
            ("ADMIN", generate_password_hash("ADMIN"), "관리자", "super_admin"),
        )
        conn.commit()
        if cur.rowcount:
            print("admin_users 초기 계정 시드 완료 (email='ADMIN' / 초기 비밀번호 'ADMIN' — 로그인 후 반드시 변경하세요)")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    init_db()
    print("DB 초기화 완료 (PostgreSQL)")

