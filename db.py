  cur.execute(
        "ALTER TABLE notifications "
        "ADD COLUMN IF NOT EXISTS listing_request_id INTEGER REFERENCES listing_requests(id) ON DELETE CASCADE"
    )
    cur.execute(
        "ALTER TABLE notifications "
        "ADD COLUMN IF NOT EXISTS master_building_id INTEGER REFERENCES master_buildings(id) ON DELETE SET NULL"
    )
    # 헤더 벨: 안읽음 우선 + 최신순 조회용 인덱스
    cur.execute("CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, is_read, created_at DESC)")
    # 같은 거래로 같은 사용자에게 알림 중복 생성 방지.
    #   transaction_id 가 NULL(수동 생성)인 행은 Postgres 에서 NULL 끼리 서로 다르게 취급되어
    #   유니크 제약에 걸리지 않는다 → 전체 유니크 인덱스로 둬도 문제없음(부분 인덱스면 ON CONFLICT 불가).
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_notifications_user_tx "
        "ON notifications (user_id, transaction_id)"
    )
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_notifications_user_listing "
        "ON notifications (user_id, listing_request_id)"
    )

    # 신규 급매 알림의 이메일 시도 이력 — 인앱 알림과 독립적으로 기록하며,
    # 같은 회원·같은 매물에는 이메일을 다시 시도하지 않는다.
    cur.execute("""
    CREATE TABLE IF NOT EXISTS urgent_listing_alert_logs (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        listing_request_id INTEGER NOT NULL REFERENCES listing_requests(id) ON DELETE CASCADE,
        notification_id INTEGER REFERENCES notifications(id) ON DELETE SET NULL,
        email_state TEXT NOT NULL DEFAULT 'pending',
        email_attempted_at TIMESTAMP,
        email_sent_at TIMESTAMP,
        email_error TEXT,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        UNIQUE (user_id, listing_request_id)
    )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_urgent_listing_alert_logs_listing
        ON urgent_listing_alert_logs(listing_request_id)
    """)
    cur.execute(
        "ALTER TABLE urgent_listing_alert_logs ADD COLUMN IF NOT EXISTS tier TEXT"
    )

    # 신규 공개 건물전체 매물 알림 — 급매 알림과 같은 매물에는 둘 중 하나만 예약한다.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS new_listing_alert_logs (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            listing_request_id INTEGER NOT NULL REFERENCES listing_requests(id) ON DELETE CASCADE,
            notification_id INTEGER REFERENCES notifications(id) ON DELETE SET NULL,
            email_state TEXT NOT NULL DEFAULT 'pending',
            email_attempted_at TIMESTAMP,
            email_sent_at TIMESTAMP,
            email_error TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            UNIQUE (user_id, listing_request_id)
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_new_listing_alert_logs_listing
        ON new_listing_alert_logs(listing_request_id)
    """)

    # 숙박업 동기화의 이전 상태. 최초 전체 수집에서는 이 테이블만 채우고 알림은 보내지 않는다.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS lodging_registry_alert_snapshots (
            permit_number TEXT PRIMARY KEY,
            master_building_id INTEGER REFERENCES master_buildings(id) ON DELETE SET NULL,
            biz_status_name TEXT,
            biz_status_detail TEXT,
            room_count INTEGER,
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_lodging_alert_snapshots_building
        ON lodging_registry_alert_snapshots(master_building_id)
    """)

    # 건물별·KST 날짜별 신고변동 요약과 회원별 전달 상태를 분리한다.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS permit_change_alert_logs (
            id SERIAL PRIMARY KEY,
            master_building_id INTEGER NOT NULL REFERENCES master_buildings(id) ON DELETE CASCADE,
            change_date DATE NOT NULL,
            change_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
            delivery_queued_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            UNIQUE (master_building_id, change_date)
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_permit_change_alert_logs_pending
        ON permit_change_alert_logs(change_date, delivery_queued_at)
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS permit_change_alert_deliveries (
            id SERIAL PRIMARY KEY,
            permit_change_alert_log_id INTEGER NOT NULL REFERENCES permit_change_alert_logs(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            notification_id INTEGER REFERENCES notifications(id) ON DELETE SET NULL,
            email_state TEXT NOT NULL DEFAULT 'pending',
            email_attempted_at TIMESTAMP,
            email_sent_at TIMESTAMP,
            email_error TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            UNIQUE (permit_change_alert_log_id, user_id)
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_permit_change_alert_deliveries_user
        ON permit_change_alert_deliveries(user_id, created_at DESC)
    """)

    # 계약만기 알림 발송 이력 — 인앱/이메일 상태를 분리해 임계치별 중복을 막는다.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS room_expiry_alerts_sent (
            id SERIAL PRIMARY KEY,
            room_id INTEGER NOT NULL REFERENCES business_room_inventory(id) ON DELETE CASCADE,
            threshold TEXT NOT NULL,
            notification_id INTEGER REFERENCES notifications(id) ON DELETE SET NULL,
            in_app_sent_at TIMESTAMP,
            email_state TEXT NOT NULL DEFAULT 'pending',
            email_idempotency_key TEXT,
            email_attempted_at TIMESTAMP,
            email_sent_at TIMESTAMP,
            email_error TEXT,
            sent_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(room_id, threshold)
        )
    """)
    # 초기 버전의 RESTRICT FK/단일 sent_at 이력을 상태 분리 구조로 안전하게 보정한다.
    cur.execute("ALTER TABLE room_expiry_alerts_sent ADD COLUMN IF NOT EXISTS notification_id INTEGER")
    cur.execute("ALTER TABLE room_expiry_alerts_sent ADD COLUMN IF NOT EXISTS in_app_sent_at TIMESTAMP")
    cur.execute("ALTER TABLE room_expiry_alerts_sent ADD COLUMN IF NOT EXISTS email_state TEXT")
    cur.execute("ALTER TABLE room_expiry_alerts_sent ADD COLUMN IF NOT EXISTS email_idempotency_key TEXT")
    cur.execute("ALTER TABLE room_expiry_alerts_sent ADD COLUMN IF NOT EXISTS email_attempted_at TIMESTAMP")
    cur.execute("ALTER TABLE room_expiry_alerts_sent ADD COLUMN IF NOT EXISTS email_sent_at TIMESTAMP")
    cur.execute("ALTER TABLE room_expiry_alerts_sent ADD COLUMN IF NOT EXISTS email_error TEXT")
    cur.execute("""
        UPDATE room_expiry_alerts_sent
           SET in_app_sent_at = COALESCE(in_app_sent_at, sent_at),
               email_state = COALESCE(email_state, 'sent')
         WHERE in_app_sent_at IS NULL OR email_state IS NULL
    """)
    cur.execute("ALTER TABLE room_expiry_alerts_sent ALTER COLUMN email_state SET DEFAULT 'pending'")
    cur.execute("ALTER TABLE room_expiry_alerts_sent ALTER COLUMN email_state SET NOT NULL")
    cur.execute("ALTER TABLE room_expiry_alerts_sent DROP CONSTRAINT IF EXISTS room_expiry_alerts_sent_room_id_fkey")
    cur.execute("""
        ALTER TABLE room_expiry_alerts_sent
        ADD CONSTRAINT room_expiry_alerts_sent_room_id_fkey
        FOREIGN KEY (room_id) REFERENCES business_room_inventory(id) ON DELETE CASCADE
    """)
    cur.execute("ALTER TABLE room_expiry_alerts_sent DROP CONSTRAINT IF EXISTS room_expiry_alerts_sent_notification_id_fkey")
    cur.execute("""
        ALTER TABLE room_expiry_alerts_sent
        ADD CONSTRAINT room_expiry_alerts_sent_notification_id_fkey
        FOREIGN KEY (notification_id) REFERENCES notifications(id) ON DELETE SET NULL
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS ix_room_expiry_alerts_sent_room "
        "ON room_expiry_alerts_sent(room_id)"
    )
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_room_expiry_alert_email_key "
        "ON room_expiry_alerts_sent(email_idempotency_key) "
        "WHERE email_idempotency_key IS NOT NULL"
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
    cur.execute("ALTER TABLE notices ADD COLUMN IF NOT EXISTS attachment_key TEXT")
    cur.execute("ALTER TABLE notices ADD COLUMN IF NOT EXISTS category TEXT DEFAULT 'notice'")
    cur.execute("ALTER TABLE notices ADD COLUMN IF NOT EXISTS external_url TEXT")
    cur.execute("ALTER TABLE notices ADD COLUMN IF NOT EXISTS summary TEXT")
    cur.execute("UPDATE notices SET category='notice' WHERE category IS NULL")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS agency_links (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            logo_url TEXT,
            link_url TEXT NOT NULL UNIQUE,
            display_order INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS agency_links_link_url_uidx
        ON agency_links (link_url)
    """)
    cur.execute("""
        -- 기본 유관기관 3개 INSERT (최초 1회)
        INSERT INTO agency_links (name, link_url, display_order, is_active)
        VALUES
            ('고캠핑',
             'https://www.gocamping.or.kr',       1, TRUE),
            ('한국관광공사',
             'https://www.visitkorea.or.kr',      2, TRUE),
            ('관광기금융자',
             'https://www.knto.or.kr/loan',       3, TRUE)
        ON CONFLICT DO NOTHING
    """)

    # 약관/개인정보처리방침 — 관리자가 admin.html에서 직접 수정하는 DB 기반 법적 문서.
    # doc_type은 'terms'(이용약관) 또는 'privacy'(개인정보처리방침) 두 값만 사용한다.
    cur.execute("""
    CREATE TABLE IF NOT EXISTS legal_documents (
        id SERIAL PRIMARY KEY,
        doc_type TEXT UNIQUE NOT NULL,       -- 'terms' | 'privacy'
        content TEXT NOT NULL,               -- 본문 (줄바꿈 포함 plain text 또는 간단한 HTML)
        updated_at TIMESTAMP DEFAULT NOW()
    )
    """)

    # 사이트 팝업/상단배너 — 관리자가 admin.html "팝업관리"에서 등록,
    # 공개 API(/api/popups/active)가 조건에 맞는 1건을 골라 header.js가 표시한다.
    cur.execute("""
    CREATE TABLE IF NOT EXISTS site_popups (
        id SERIAL PRIMARY KEY,
        title TEXT NOT NULL,                     -- 관리용 제목 (사용자에게는 미노출)
        start_at TIMESTAMP,                      -- 게재 시작 (NULL이면 즉시)
        end_at TIMESTAMP,                        -- 게재 종료 (NULL이면 무기한)
        show_desktop BOOLEAN DEFAULT TRUE,       -- 데스크톱 노출
        show_mobile BOOLEAN DEFAULT TRUE,        -- 모바일 노출
        scope TEXT DEFAULT 'all',                -- 'all'(전체 페이지) | 'home_only'(홈만)
        audience TEXT DEFAULT 'all',             -- 'all' | 'logged_in'(로그인 회원만)
        display_type TEXT DEFAULT 'popup',       -- 'popup'(모달) | 'top_banner'(상단배너)
        image_ref TEXT,                          -- Object Storage 참조 키 (popups/…)
        link_url TEXT,                           -- 클릭 시 이동 URL (없으면 링크 없음)
        open_new_tab BOOLEAN DEFAULT TRUE,       -- 링크 새 창 열기
        width_px INTEGER DEFAULT 400,            -- 팝업 너비(px)
        close_mode TEXT DEFAULT 'close',         -- 'close'(닫기만) | 'hide_today'(오늘 하루 안 보기)
        is_active BOOLEAN DEFAULT TRUE,          -- 게재중/중지 토글
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    )
    """)

    # 앱 메타(키-값) — 관리 작업의 마지막 실행 기록 등 소소한 상태 저장용
    cur.execute("""
    CREATE TABLE IF NOT EXISTS app_meta (
        key TEXT PRIMARY KEY,               -- 예: 'geocode_last_run'
        value TEXT,                         -- 자유 형식(문자열/숫자)
        updated_at TIMESTAMP DEFAULT NOW()  -- 마지막 갱신 시각
    )
    """)

    # 중개사 의뢰 알림용 단축 링크 — 코드는 외부에 노출되므로 만료 시각을 함께 검증한다.
    cur.execute("""
    CREATE TABLE IF NOT EXISTS short_links (
        code VARCHAR(6) PRIMARY KEY,
        target_path TEXT NOT NULL,
        expires_at TIMESTAMP NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        CONSTRAINT short_links_target_path_check
            CHECK (target_path LIKE '/admin%' OR target_path LIKE '/agent/dashboard%')
    )
    """)
    # 이전 단축 링크 스키마는 관리자 경로만 허용했다. 기존 테이블에도 중개사
    # 대시보드 딥링크를 저장할 수 있게 제약을 명시적으로 교체한다.
    cur.execute("ALTER TABLE short_links DROP CONSTRAINT IF EXISTS short_links_target_path_check")
    cur.execute("""
        ALTER TABLE short_links
        ADD CONSTRAINT short_links_target_path_check
        CHECK (target_path LIKE '/admin%' OR target_path LIKE '/agent/dashboard%')
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_short_links_expires_at
        ON short_links(expires_at)
    """)

    # 주간 이메일 기능 소개 시리즈. episode는 ISO 주차를 1~8회로 순환해 선택하는
    # 운영용 회차이며, 관리자가 내용을 바꾼 뒤에는 초기 시드가 덮어쓰지 않는다.
    cur.execute("""
    CREATE TABLE IF NOT EXISTS weekly_feature_tips (
        id SERIAL PRIMARY KEY,
        episode INTEGER NOT NULL UNIQUE CHECK (episode BETWEEN 1 AND 8),
        title TEXT NOT NULL,
        body TEXT NOT NULL,
        cta_label TEXT NOT NULL DEFAULT '기능 자세히 보기',
        cta_url TEXT NOT NULL,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_weekly_feature_tips_active_episode
        ON weekly_feature_tips (is_active, episode)
    """)
    # ISO 주차는 1~8회차로 순환한다. 테이블을 최초 생성한 뒤 도입한 제약이라
    # 기존 환경에도 명시적으로 같은 범위를 적용한다.
    cur.execute("""
        ALTER TABLE weekly_feature_tips
        DROP CONSTRAINT IF EXISTS weekly_feature_tips_episode_check
    """)
    cur.execute("""
        ALTER TABLE weekly_feature_tips
        ADD CONSTRAINT weekly_feature_tips_episode_check
        CHECK (episode BETWEEN 1 AND 8)
    """)

    # 검색 성능을 위한 인덱스
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tx_deal_date ON transactions(deal_date DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tx_building_name ON transactions(building_name)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tx_address ON transactions(address)")
    # LATERAL 서브쿼리 최적화: 지도 마커 API가 건물마다 최근 실거래가를 조회할 때 사용
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tx_sgg_umd_jibun ON transactions(sgg_cd, umd_nm, jibun, deal_date DESC)")
    # 건물별 슬롯 조회(정원 충족 여부 확인)용 인덱스
    cur.execute("CREATE INDEX IF NOT EXISTS idx_slots_building ON slots(master_building_id)")
    # 건물별 매물 조회용 인덱스
    cur.execute("CREATE INDEX IF NOT EXISTS idx_listings_building ON listings(master_building_id)")
    # 통계(일별 방문 집계)용 인덱스
    cur.execute("CREATE INDEX IF NOT EXISTS idx_page_views_viewed_at ON page_views(viewed_at)")
    # 건물전체 매물 카드의 최근 5분 고유 열람자 집계용 인덱스
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_page_views_listing_recent "
        "ON page_views(listing_request_id, viewed_at DESC) "
        "WHERE listing_request_id IS NOT NULL"
    )
    # 공지사항 정렬(고정 우선 → 최신순)용 인덱스
    cur.execute("CREATE INDEX IF NOT EXISTS idx_notices_order ON notices(is_pinned DESC, created_at DESC)")
    # master_buildings 지번 복합 인덱스 — 지번 매칭 쿼리(transactions JOIN, nearby-stores 등) 최적화
    cur.execute("CREATE INDEX IF NOT EXISTS idx_mb_sgg_umd_jibun ON master_buildings(sgg_cd, umd_nm, jibun)")

    # OTA 등록확인 (운영확인) — 1단계: 관리자 직접 입력
    # booking_url_source: 'admin'|'owner'|'operator'|'user_report' (1단계는 admin만 사용)
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS booking_url TEXT")
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS booking_url_source TEXT")
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS booking_url_updated_at TIMESTAMP")
    # OTA 링크 만료일 — 3단계(운영업체 신청) 승인 시 NOW()+3개월, 관리자 직접입력은 NULL(무기한)
    cur.execute("ALTER TABLE master_buildings ADD COLUMN IF NOT EXISTS booking_url_expires_at TIMESTAMP")

    # OTA 링크 신청 큐 — 위탁운영업체가 담당 건물의 OTA 링크를 신청; 관리자 승인 후 반영
    cur.execute("""
    CREATE TABLE IF NOT EXISTS booking_url_requests (
        id SERIAL PRIMARY KEY,
        operator_id INTEGER NOT NULL REFERENCES operators(id) ON DELETE CASCADE,
        master_building_id INTEGER NOT NULL REFERENCES master_buildings(id) ON DELETE CASCADE,
        booking_url TEXT NOT NULL,
        status TEXT DEFAULT 'pending',   -- pending | approved | rejected | cancelled
        submitted_at TIMESTAMP DEFAULT NOW(),
        reviewed_at TIMESTAMP,
        reviewed_by INTEGER REFERENCES admin_users(id),
        admin_note TEXT
    )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_bur_operator
        ON booking_url_requests(operator_id, submitted_at DESC)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_bur_status
        ON booking_url_requests(status, submitted_at DESC)
    """)
    cur.execute("""
        ALTER TABLE booking_url_requests
        ADD COLUMN IF NOT EXISTS renewal_count INTEGER DEFAULT 0
    """)
    cur.execute("ALTER TABLE booking_url_requests ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP")

    # ── 사이트 오류신고 (플로팅 버튼 → 관리자 심사) ────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bug_reports (
            id           SERIAL PRIMARY KEY,
            user_id      INTEGER REFERENCES users(id),
            account_type TEXT,
            description  TEXT NOT NULL,
            page_url     TEXT,
            user_agent   TEXT,
            severity     TEXT DEFAULT 'annoying',
            contact      TEXT,
            screenshot_key TEXT,
            status       TEXT DEFAULT 'new',
            admin_note   TEXT,
            created_at   TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_bug_reports_status
        ON bug_reports(status, created_at DESC)
    """)

    # ── 상가정보 사전수집 캐시 (sync_stores.py → building_stores) ──────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS building_stores (
            id                 SERIAL PRIMARY KEY,
            master_building_id INTEGER NOT NULL REFERENCES master_buildings(id) ON DELETE CASCADE,
            store_name         TEXT,
            category           TEXT,
            floor              TEXT,
            ho_no              TEXT,
            inds_mcls_nm       TEXT,
            inds_scls_nm       TEXT,
            updated_at         TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_building_stores_building
        ON building_stores(master_building_id)
    """)

    # ── 전유부(호실별 전용면적) 온디맨드 캐시 ──────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS building_unit_areas (
            id                 SERIAL PRIMARY KEY,
            master_building_id INTEGER NOT NULL REFERENCES master_buildings(id) ON DELETE CASCADE,
            ho                 VARCHAR(20),
            area_sqm           NUMERIC,
            fetched_at         TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_unit_areas_building
        ON building_unit_areas(master_building_id)
    """)

    # 건물 상세 사진 — 수집원별 URL과 표시 순서를 보관한다.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS building_photos (
            id            SERIAL PRIMARY KEY,
            building_id   INTEGER NOT NULL REFERENCES master_buildings(id) ON DELETE CASCADE,
            photo_url     TEXT NOT NULL,
            source        TEXT NOT NULL,
            photo_type    TEXT,
            is_primary    BOOLEAN DEFAULT FALSE,
            display_order INTEGER DEFAULT 0,
            created_at    TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    cur.execute("""
        ALTER TABLE building_photos
        ADD COLUMN IF NOT EXISTS photo_hash TEXT,
        ADD COLUMN IF NOT EXISTS uploaded_by_user_id INTEGER,
        ADD COLUMN IF NOT EXISTS registrant_type TEXT,
        ADD COLUMN IF NOT EXISTS gps_lat DOUBLE PRECISION,
        ADD COLUMN IF NOT EXISTS gps_lng DOUBLE PRECISION,
        ADD COLUMN IF NOT EXISTS gps_verified BOOLEAN DEFAULT FALSE,
        ADD COLUMN IF NOT EXISTS exif_taken_at TIMESTAMPTZ
    """)
    cur.execute("""
        ALTER TABLE building_photos
        ADD COLUMN IF NOT EXISTS uploaded_by_agent_id INTEGER REFERENCES agents(id),
        ADD COLUMN IF NOT EXISTS listing_request_id INTEGER REFERENCES listing_requests(id),
        ADD COLUMN IF NOT EXISTS priority_rank SMALLINT DEFAULT 99
    """)
    cur.execute("""
        ALTER TABLE building_photos
        DROP CONSTRAINT IF EXISTS building_photos_listing_request_id_fkey
    """)
    cur.execute("""
        ALTER TABLE building_photos
        ADD CONSTRAINT building_photos_listing_request_id_fkey
        FOREIGN KEY (listing_request_id)
        REFERENCES listing_requests(id)
        ON DELETE CASCADE
    """)
    cur.execute("""
        UPDATE building_photos
           SET priority_rank = CASE
               WHEN registrant_type = 'admin' THEN 0
               WHEN registrant_type IN ('owner', 'building_owner', 'landlord', 'business') THEN 1
               WHEN registrant_type = 'agent_building' THEN 2
               WHEN registrant_type = 'agent_region' THEN 3
               WHEN source = 'tourapi' THEN 9
               WHEN source = 'streetview' THEN 10
               WHEN source = 'vworld' THEN 11
               ELSE 99
           END
         WHERE priority_rank IS NULL OR priority_rank = 99
    """)
    cur.execute("UPDATE building_photos SET is_primary=FALSE WHERE is_primary=TRUE")
    cur.execute("""
        WITH primary_candidates AS (
            SELECT DISTINCT ON (building_id) id
              FROM building_photos
             ORDER BY building_id, priority_rank ASC, created_at ASC, id ASC
        )
        UPDATE building_photos p
           SET is_primary=TRUE
          FROM primary_candidates candidate
         WHERE p.id=candidate.id
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_bphotos_building
        ON building_photos(building_id, display_order)
    """)
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_bphotos_building_url
        ON building_photos(building_id, photo_url)
    """)
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_bphotos_hash
        ON building_photos(building_id, photo_hash)
        WHERE photo_hash IS NOT NULL
    """)
    # 건물 사진 온디맨드 조회 기록. 사진이 없는 건물도 조회 결과를 캐시해
    # 상세페이지를 열 때마다 같은 외부 API를 반복 호출하지 않게 한다.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS building_photo_fetches (
            building_id     INTEGER NOT NULL REFERENCES master_buildings(id) ON DELETE CASCADE,
            source          TEXT NOT NULL,
            status          TEXT NOT NULL,
            last_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            error_message   TEXT,
            PRIMARY KEY (building_id, source)
        )
    """)
    cur.execute("""
        ALTER TABLE building_photo_fetches
        ADD COLUMN IF NOT EXISTS provider_ref TEXT
    """)
    cur.execute("""
        ALTER TABLE building_photo_fetches
        ADD COLUMN IF NOT EXISTS photo_available BOOLEAN
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_bphoto_fetches_attempt
        ON building_photo_fetches(source, status, last_attempt_at)
    """)

    conn.commit()
    cur.close()
    conn.close()

    _ensure_raw_key_unique_constraint()
    _ensure_admin_email_unique_constraint()
    _ensure_agents_unique_constraints()
    _ensure_operators_unique_constraints()
    _ensure_loan_consultants_unique_constraints()
    _ensure_mileage_missions_code_unique_constraint()
    _ensure_users_unique_constraints()
    _seed_mileage_missions()
    _seed_admin_user()
    _seed_legal_documents()
    _seed_weekly_feature_tips()
    _normalize_umd_nm_spaces()
    _ensure_transaction_stats_indexes()

    # 전체 DDL/시드가 무사히 끝났을 때만 버전을 기록 → 다음 부팅부터 빠른 경로로 건너뜀
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO app_meta (key, value, updated_at) VALUES ('schema_version', %s, NOW())
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
    """, (SCHEMA_VERSION,))
    conn.commit()
    cur.close()
    conn.close()
    print(f"스키마 버전 {SCHEMA_VERSION} 기록 완료 — 다음 부팅부터 DDL 건너뜀")


def _ensure_transaction_stats_indexes():
    """데이터랩 거래 통계용 인덱스를 서비스 중단 없이 보장한다."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        # CONCURRENTLY는 트랜잭션 블록 안에서 실행할 수 없으므로 별도 autocommit
        # 연결을 쓴다. 스키마 초기화 advisory lock은 중복 실행만 막는다.
        conn.autocommit = True
        cur.execute("""
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_transactions_deal_date
            ON transactions (deal_date DESC)
        """)
        cur.execute("""
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_transactions_building
            ON transactions (building_name, address)
        """)
    finally:
        cur.close()
        conn.close()


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


def _ensure_operators_unique_constraints():
    """
    operators.subdomain_slug에 DB 레벨 UNIQUE 제약을 안전하게 부여한다.
    (_ensure_agents_unique_constraints()와 같은 패턴)
    - 중복 값이 있으면 데이터를 지우지 않고 경고만 출력하고 건너뛴다.
    - 제약이 이미 있으면 skip, 없으면 add. (재실행 안전)
    - subdomain_slug는 NULL 허용(미승인 상태)이며, PostgreSQL UNIQUE는 NULL 다중 허용이라 문제 없음.
    """
    conn = get_conn()
    cur = conn.cursor()

    targets = [
        ("subdomain_slug", "operators_subdomain_slug_unique"),
    ]
    for column, constraint_name in targets:
        cur.execute(f"""
            SELECT {column} AS v, COUNT(*) AS c
            FROM operators
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
            WHERE tc.table_name = 'operators'
              AND tc.constraint_type = 'UNIQUE'
              AND kcu.column_name = %s
        """, (column,))
        exists = cur.fetchone()

        if exists:
            print(f"operators.{column} UNIQUE 제약 이미 존재({exists['constraint_name']})")
        elif dups:
            print(f"[경고] operators.{column} 중복 {len(dups)}건 발견 — 데이터 자동 삭제하지 않고 UNIQUE 제약 부여를 건너뜁니다. 수동 정리 후 재실행하세요.")
        else:
            cur.execute(f"ALTER TABLE operators ADD CONSTRAINT {constraint_name} UNIQUE ({column})")
            print(f"operators.{column} UNIQUE 제약 신규 적용 완료")

    conn.commit()
    cur.close()
    conn.close()


def _ensure_loan_consultants_unique_constraints():
    """
    loan_consultants.license_number, loan_consultants.subdomain_slug, loan_consultants.email에
    DB 레벨 UNIQUE 제약을 안전하게 부여한다. (_ensure_agents_unique_constraints()와 같은 패턴)
    - 중복 값이 있으면 데이터를 지우지 않고 경고만 출력하고 건너뛴다.
    - 제약이 이미 있으면 skip, 없으면 add. (재실행 안전)
    - email은 대소문자 무시(LOWER)로 중복 확인.
    """
    conn = get_conn()
    cur = conn.cursor()

    targets = [
        ("license_number", "license_number", "loan_consultants_license_number_unique"),
        ("subdomain_slug", "subdomain_slug", "loan_consultants_subdomain_slug_unique"),
        ("email", "LOWER(email)", "loan_consultants_email_unique"),
    ]
    for column, dup_expr, constraint_name in targets:
        cur.execute(f"""
            SELECT {dup_expr} AS v, COUNT(*) AS c
            FROM loan_consultants
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
            WHERE tc.table_name = 'loan_consultants'
              AND tc.constraint_type = 'UNIQUE'
              AND kcu.column_name = %s
        """, (column,))
        exists = cur.fetchone()

        if exists:
            print(f"loan_consultants.{column} UNIQUE 제약 이미 존재({exists['constraint_name']})")
        elif dups:
            print(f"[경고] loan_consultants.{column} 중복 {len(dups)}건 발견 — 데이터 자동 삭제하지 않고 UNIQUE 제약 부여를 건너뜁니다. 수동 정리 후 재실행하세요.")
        else:
            cur.execute(f"ALTER TABLE loan_consultants ADD CONSTRAINT {constraint_name} UNIQUE ({column})")
            print(f"loan_consultants.{column} UNIQUE 제약 신규 적용 완료")

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


_LEGAL_TERMS_SEED = """<h2>제1조 (목적)</h2>
<p>이 약관은 빌드리머스(이하 "회사")가 제공하는 생활숙박시설·분양형호텔·콘도 실거래가 조회 서비스(이하 "서비스")의 이용과 관련하여 회사와 이용자 간의 권리, 의무 및 책임사항을 규정함을 목적으로 합니다.</p>

<h2>제2조 (정의)</h2>
<ul>
<li>"서비스"란 회사가 제공하는 전국 생활숙박시설 등의 실거래가 정보 조회 및 관련 부가 서비스를 말합니다.</li>
<li>"이용자"란 이 약관에 따라 회사가 제공하는 서비스를 이용하는 회원 및 비회원을 말합니다.</li>
<li>"회원"이란 회사에 개인정보를 제공하여 회원등록을 한 자로서, 서비스를 지속적으로 이용할 수 있는 자를 말합니다.</li>
</ul>

<h2>제2조의2 (파트너 회원)</h2>
<p>"파트너 회원"이란 회사가 정한 승인 절차를 거쳐 중개사, 운영지원업체, 대출상담사로 등록된 회원을 말합니다. 파트너 회원에게는 일반 회원과 다른 별도의 이용조건이 적용될 수 있습니다.</p>

<h2>제3조 (약관의 효력 및 변경)</h2>
<p>이 약관은 서비스 화면에 게시하거나 기타의 방법으로 이용자에게 공지함으로써 효력이 발생합니다. 회사는 관련 법령을 위배하지 않는 범위에서 이 약관을 변경할 수 있으며, 변경된 약관은 공지와 동시에 효력이 발생합니다.</p>

<h2>제4조 (서비스의 제공)</h2>
<p>회사는 국토교통부 실거래가 공개시스템 등 공공데이터를 기반으로 실거래가 정보를 제공합니다. 제공되는 정보는 참고용이며, 실제 거래 시점의 가격 및 조건과 다를 수 있습니다. 회사는 정보의 정확성·완전성을 보장하지 않으며, 이를 근거로 한 이용자의 판단과 그 결과에 대해 책임지지 않습니다.</p>

<h2>제4조의2 (파트너 서비스 및 정보 연결)</h2>
<p>① 회사는 이용자와 파트너 회원 간의 정보 연결(매물의뢰 자동배정 등)을 제공할 뿐, 회사 스스로 부동산 중개행위, 위탁운영 계약, 대출 중개·모집 행위를 직접 수행하지 않습니다.</p>
<p>② 회사는 파트너 회원의 자격 서류(사업자등록증, 중개사무소 등록증, 대출모집인 등록번호 등)를 확인 절차를 거쳐 승인하나, 이는 서류상 확인 절차일 뿐 파트너 회원의 실제 자격 유지, 서비스 품질, 상담·거래 결과를 보증하는 것이 아닙니다.</p>
<p>③ 이용자와 파트너 회원 간에 체결되는 계약(중개계약, 위탁운영계약, 대출상담 등)은 이용자와 파트너 회원 간의 직접 계약이며, 회사는 그 계약의 당사자가 아닙니다.</p>

<h2>제5조 (이용자의 의무)</h2>
<ul>
<li>이용자는 서비스를 이용함에 있어 관련 법령 및 이 약관의 규정을 준수하여야 합니다.</li>
<li>이용자는 서비스에서 제공하는 정보를 회사의 사전 동의 없이 영리 목적으로 복제·배포·가공하여서는 안 됩니다.</li>
<li>이용자는 서비스의 안정적 운영을 방해하는 행위를 하여서는 안 됩니다.</li>
</ul>

<h2>제5조의2 (파트너 회원의 의무)</h2>
<p>① 파트너 회원은 신청 시 제출한 정보 및 서류가 진실함을 보증하며, 허위 서류 제출이 확인되는 경우 회사는 사전 통지 없이 승인을 취소하고 서비스 이용을 제한할 수 있습니다.</p>
<p>② 파트너 회원은 관계 법령(공인중개사법, 금융소비자보호법 등)을 준수하여야 하며, 이를 위반하여 발생한 손해에 대해서는 파트너 회원 본인이 책임을 집니다.</p>

<h2>제6조 (면책조항)</h2>
<p>회사는 천재지변, 공공데이터 제공기관의 사정, 기타 불가항력으로 인하여 서비스를 제공할 수 없는 경우 그 책임이 면제됩니다. 회사는 이용자가 서비스에 게재한 정보·자료의 신뢰도, 정확성 등에 대하여 책임지지 않습니다.</p>
<p>회사는 파트너 회원이 제공하는 정보, 상담 내용, 서비스 품질 및 이용자와 파트너 회원 간 거래 결과에 대하여 책임을 지지 않습니다. 대출상담 관련 정보는 참고용이며, 과도한 채무는 개인의 신용에 악영향을 줄 수 있습니다.</p>

<h2>제6조의2 (유료 서비스)</h2>
<p>회사는 파트너 회원을 대상으로 우선노출 등 유료 서비스를 제공할 수 있으며, 그 이용조건, 결제, 환불에 관한 사항은 별도로 정하는 바에 따릅니다.</p>

<h2>제7조 (분쟁의 해결)</h2>
<p>이 약관과 관련하여 회사와 이용자 간에 발생한 분쟁에 대하여는 대한민국 법을 준거법으로 하며, 분쟁으로 인한 소송은 관할 법원에 제기합니다.</p>

<h2>부칙</h2>
<p>이 약관은 2026년부터 시행합니다.</p>
<p>서비스 제공자: 빌드리머스 · 대표 조혜성</p>"""


_LEGAL_PRIVACY_SEED = """<h2>1. 개인정보의 처리 목적</h2>
<p>빌드리머스(이하 "회사")는 다음의 목적을 위하여 개인정보를 처리합니다. 처리한 개인정보는 다음의 목적 이외의 용도로는 이용되지 않으며, 이용 목적이 변경되는 경우에는 별도의 동의를 받는 등 필요한 조치를 이행합니다.</p>
<ul>
<li>회원 가입 및 관리</li>
<li>서비스 제공 및 문의 응대</li>
<li>관심 단지 알림 등 이용자 맞춤형 서비스 제공</li>
</ul>

<h2>2. 처리하는 개인정보 항목</h2>
<ul>
<li>필수항목: 이메일, 이름, 비밀번호(암호화하여 저장)</li>
<li>소셜 로그인 이용 시: 카카오 계정 식별자 및 프로필 정보</li>
<li>자동 수집 항목: 접속 IP, 쿠키, 서비스 이용 기록</li>
</ul>
<p>파트너 회원(중개사·운영지원업체·대출상담사) 가입 시</p>
<ul>
<li>필수항목: 대표자명, 연락처, 이메일, 사업자등록번호(또는 중개사무소 등록번호, 대출모집인 등록번호)</li>
<li>선택항목: 여권용 사진(중개사), 자격증·등록증 등 첨부서류</li>
</ul>

<h2>3. 개인정보의 처리 및 보유 기간</h2>
<p>회사는 법령에 따른 개인정보 보유·이용기간 또는 정보주체로부터 개인정보를 수집 시에 동의받은 보유·이용기간 내에서 개인정보를 처리·보유합니다.</p>
<ul>
<li>회원 정보: 회원 탈퇴 시까지 (부정이용 방지를 위해 탈퇴 후 최대 30일간 보관 후 파기)</li>
<li>파트너 신청 서류: 반려 시 즉시 파기, 승인 시 파트너 자격 유지 기간 동안 보관 후 파기</li>
<li>전자상거래 등에서의 소비자보호에 관한 법률에 따른 계약 또는 청약철회 등에 관한 기록: 5년</li>
<li>통신비밀보호법에 따른 로그인 기록: 3개월</li>
</ul>

<h2>4. 개인정보의 제3자 제공</h2>
<p>회사는 정보주체의 개인정보를 제1조에서 명시한 범위 내에서만 처리하며, 정보주체의 동의, 법률의 특별한 규정 등 개인정보 보호법에 해당하는 경우에만 개인정보를 제3자에게 제공합니다.</p>

<h2>4의2. 개인정보 처리업무의 위탁</h2>
<p>회사는 원활한 서비스 제공을 위하여 다음과 같이 개인정보 처리업무를 위탁하고 있습니다.</p>
<table>
<thead><tr><th>수탁업체</th><th>위탁업무 내용</th></tr></thead>
<tbody>
<tr><td>(주)알리고</td><td>SMS 발송</td></tr>
<tr><td>Resend</td><td>이메일 발송</td></tr>
<tr><td>카카오</td><td>소셜 로그인</td></tr>
<tr><td>Replit(Object Storage)</td><td>첨부서류 파일 저장</td></tr>
</tbody>
</table>
<p>회사는 위탁계약 체결 시 개인정보보호법 제26조에 따라 개인정보가 안전하게 관리될 수 있도록 필요한 사항을 규정하고 있습니다.</p>

<h2>5. 개인정보의 파기 절차 및 방법</h2>
<p>회사는 개인정보 보유기간의 경과, 처리목적 달성 등 개인정보가 불필요하게 되었을 때에는 지체 없이 해당 개인정보를 파기합니다. 전자적 파일 형태의 정보는 복구 불가능한 방법으로 삭제합니다.</p>

<h2>6. 정보주체의 권리·의무 및 행사 방법</h2>
<p>정보주체는 회사에 대해 언제든지 개인정보 열람·정정·삭제·처리정지 요구 등의 권리를 행사할 수 있습니다. 개인정보 열람·정정·삭제·처리정지 요구는 아래로 접수해주시기 바랍니다.</p>
<ul>
<li>접수처(이메일): costac74888@gmail.com</li>
</ul>

<h2>7. 개인정보의 안전성 확보 조치</h2>
<p>회사는 개인정보의 안전성 확보를 위해 비밀번호 암호화, 접근권한 관리, 접속기록의 보관 등 관리적·기술적 보호조치를 시행하고 있습니다.</p>

<h2>8. 개인정보 보호책임자</h2>
<ul>
<li>개인정보 보호책임자: 조혜성 (빌드리머스 대표)</li>
</ul>

<h2>부칙</h2>
<p>이 개인정보처리방침은 2026년부터 시행합니다.</p>"""


# 2026-07-21 개정 전(초판) 시드 원문의 md5 — 관리자 수정 없이 초판 그대로인 행만
# 새 개정판으로 자동 교체하기 위한 지문. (관리자가 admin.html에서 한 글자라도
# 수정했다면 md5가 달라져 자동 교체 대상에서 제외된다.)
_LEGAL_PREV_SEED_MD5 = {
    "terms": "000c485737128061a5568d218862fe41",
    "privacy": "2f411e7ef0bdce3d74acecf3de1ffe0f",
}


def _seed_legal_documents():
    """
    이용약관/개인정보처리방침 초기 본문을 시드한다.
    - doc_type 기준 ON CONFLICT DO NOTHING이라 이미 있으면 덮어쓰지 않는다(관리자 수정 내용 보존).
    - 단, 기존 행이 '이전 시드 원문 그대로'(관리자 무수정)인 경우에만
      새 개정판으로 자동 교체한다 (프로덕션 등 다른 환경에 개정 내용 전파용).
    """
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.executemany("""
            INSERT INTO legal_documents (doc_type, content)
            VALUES (%s, %s)
            ON CONFLICT (doc_type) DO NOTHING
        """, [("terms", _LEGAL_TERMS_SEED), ("privacy", _LEGAL_PRIVACY_SEED)])
        inserted = cur.rowcount
        upgraded = 0
        for doc_type, new_content in (("terms", _LEGAL_TERMS_SEED), ("privacy", _LEGAL_PRIVACY_SEED)):
            prev_md5 = _LEGAL_PREV_SEED_MD5.get(doc_type)
            if not prev_md5:
                continue
            cur.execute("""
                UPDATE legal_documents
                SET content = %s, updated_at = NOW()
                WHERE doc_type = %s AND md5(content) = %s
            """, (new_content, doc_type, prev_md5))
            upgraded += cur.rowcount
        conn.commit()
        if inserted or upgraded:
            print(f"legal_documents 시드 완료 (신규 {inserted}건, 개정 자동교체 {upgraded}건)")
    finally:
        cur.close()
        conn.close()


_WEEKLY_FEATURE_TIP_SEEDS = [
    (
        1,
        "실거래가 무료조회",
        "로그인 없이 건물명만 입력하면 국토부 실거래가 바로 확인",
        "지금 바로 써보기 →",
        "/",
    ),
    (
        2,
        "관심단지 등록하면 실거래 알림이 와요",
        "매주 이메일로 자동 알림",
        "지금 바로 써보기 →",
        "/",
    ),
    (
        3,
        "데이터랩 숙박통계",
        "전국 생숙 건물수·호실수·신고율 한눈에",
        "지금 바로 써보기 →",
        "/?datalab=lodging",
    ),
    (
        4,
        "매물내놓기 제한공개",
        "영업 중인 사실 보호하며 조용히 매각 시작",
        "지금 바로 써보기 →",
        "/guide#disclosure-guide",
    ),
    (
        5,
        "방재고 관리",
        "객실별 상태·보증금·월세·채널·만기일 한 곳에서",
        "지금 바로 써보기 →",
        "/guide#business-guide",
    ),
    (
        6,
        "거래 체크리스트 14개 항목",
        "건물전체 매물 거래 전 필수 확인",
        "지금 바로 써보기 →",
        "/guide",
    ),
    (
        7,
        "보류 기능",
        "철회 없이 매물을 잠시 중단하는 방법",
        "지금 바로 써보기 →",
        "/mypage",
    ),
    (
        8,
        "영업신고현황",
        "시도별 생숙 신고율을 데이터랩에서 확인",
        "지금 바로 써보기 →",
        "/?datalab=consign",
    ),
]


def _seed_weekly_feature_tips():
    """초기 8회차 기능 팁만 채우고, 운영 중 수정된 회차는 그대로 둔다."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.executemany("""
            INSERT INTO weekly_feature_tips
                (episode, title, body, cta_label, cta_url)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (episode) DO NOTHING
        """, _WEEKLY_FEATURE_TIP_SEEDS)
        inserted = cur.rowcount
        conn.commit()
        if inserted:
            print(f"weekly_feature_tips 시드 완료 ({inserted}건)")
    finally:
        cur.close()
        conn.close()


def _normalize_umd_nm_spaces():
    """transactions·master_buildings 양쪽의 umd_nm에서 공백을 제거해 정규화한다.

    address_utils.normalize_umd_nm 과 동일한 규칙(공백 제거)을 DB 행에 직접 적용.
    멱등 — 이미 정규화된 행은 WHERE umd_nm LIKE '% %' 조건에 걸리지 않아 건드리지 않음.
    SCHEMA_VERSION 갱신 직전에 한 번만 실행되므로 신규 배포·운영 DB 모두 자동 적용된다.
    """
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE transactions SET umd_nm = REPLACE(umd_nm, ' ', '') WHERE umd_nm LIKE '% %'")
        tx_cnt = cur.rowcount
        cur.execute("UPDATE master_buildings SET umd_nm = REPLACE(umd_nm, ' ', '') WHERE umd_nm LIKE '% %'")
        mb_cnt = cur.rowcount
        conn.commit()
        if tx_cnt or mb_cnt:
            print(f"umd_nm 공백 정규화: transactions {tx_cnt}건, master_buildings {mb_cnt}건 수정")
    finally:
        cur.close()
        conn.close()


class BackgroundConnectionUnavailable(PoolError):
    """사용자 요청용 연결을 남기기 위해 백그라운드 대여를 미룰 때 사용한다."""

def _release_background_slot(slot):
    if slot is None:
        return
    try:
        slot.release()
    except ValueError:
        # 방어적으로 이중 반환을 무시한다. 실제 연결 lease의 idempotency와 맞춘다.
        _logger.warning("백그라운드 DB 연결 슬롯 이중 반환을 무시합니다.")

def background_connection_limit():
    """현재 풀에서 통계 등 저우선순위 작업에 허용할 최대 동시 대여 수."""
    with _connection_pool_lock:
        if _background_connection_slots is not None:
            return _background_connection_slot_limit

    minconn = _pool_size_from_env("DB_POOL_MINCONN", _POOL_MIN_CONNECTIONS)
    maxconn = _pool_size_from_env("DB_POOL_MAXCONN", _POOL_MAX_CONNECTIONS)
    maxconn = max(minconn, maxconn)
    return min(
        _background_pool_size_from_env(),
        max(0, maxconn - _POOL_RESERVED_FOR_REQUESTS),
    )

@contextmanager
def background_connection_priority():
    """현재 스레드의 DB 대여를 비차단 백그라운드 우선순위로 표시한다."""
    previous = getattr(_connection_priority, "background", False)
    _connection_priority.background = True
    try:
        yield
    finally:
        _connection_priority.background = previous


if __name__ == "__main__":
    init_db()
    print("DB 초기화 완료 (PostgreSQL)")
