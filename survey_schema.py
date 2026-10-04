"""공매 2차의 추가 스키마. 기존 원장·마스터·관리자 수정 설정은 보존한다."""
from psycopg2.extras import Json
from survey_defaults import DEFAULT_SETTINGS, SURVEY_TERMS_SEED


def ensure_survey_schema(cur):
    cur.execute("""
    ALTER TABLE auction_items ADD COLUMN IF NOT EXISTS check_business_report TEXT NOT NULL DEFAULT 'need_check';
    ALTER TABLE auction_items ADD COLUMN IF NOT EXISTS check_operation_succession TEXT NOT NULL DEFAULT 'need_check';
    ALTER TABLE auction_items ADD COLUMN IF NOT EXISTS check_fee_arrears TEXT NOT NULL DEFAULT 'need_check';
    CREATE TABLE IF NOT EXISTS survey_requests (
      id BIGSERIAL PRIMARY KEY, request_no TEXT UNIQUE NOT NULL,
      auction_item_id INTEGER NOT NULL REFERENCES auction_items(id),
      building_id INTEGER REFERENCES master_buildings(id) ON DELETE SET NULL,
      survey_type TEXT NOT NULL, base_fee BIGINT NOT NULL, visit_fee BIGINT NOT NULL,
      total_fee BIGINT NOT NULL,
      applicant_name TEXT NOT NULL, phone TEXT NOT NULL, email TEXT, memo TEXT NOT NULL DEFAULT '',
      depositor_name TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'received',
      status_updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      agreed_terms_at TIMESTAMPTZ NOT NULL, agreed_refund_at TIMESTAMPTZ NOT NULL,
      agreed_privacy_at TIMESTAMPTZ NOT NULL, payment_deadline TIMESTAMPTZ NOT NULL,
      settings_snapshot JSONB NOT NULL, terms_snapshot TEXT NOT NULL,
      auction_title TEXT NOT NULL, auction_address TEXT NOT NULL,
      admin_memo TEXT NOT NULL DEFAULT '', request_token_hash TEXT UNIQUE,
      submission_hash TEXT NOT NULL,
      CHECK (base_fee >= 0 AND visit_fee >= 0 AND total_fee = base_fee + visit_fee),
      CHECK (survey_type = ANY(ARRAY['basic','visit'])),
      CHECK (status = ANY(ARRAY['received','paid','investigating','reported','canceled','refunded']))
    );
    CREATE INDEX IF NOT EXISTS idx_survey_requests_status_deadline ON survey_requests(status,payment_deadline);
    CREATE INDEX IF NOT EXISTS idx_survey_requests_created ON survey_requests(created_at DESC,id DESC);
    CREATE TABLE IF NOT EXISTS survey_request_history (
      id BIGSERIAL PRIMARY KEY, request_id BIGINT NOT NULL REFERENCES survey_requests(id) ON DELETE CASCADE,
      from_status TEXT, to_status TEXT NOT NULL, note TEXT NOT NULL DEFAULT '',
      changed_by TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_survey_history_request ON survey_request_history(request_id,id);
    CREATE TABLE IF NOT EXISTS survey_settings_history (
      id BIGSERIAL PRIMARY KEY, changed_by TEXT NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      before JSONB NOT NULL, after JSONB NOT NULL
    );
    """)
    # Existing databases may have a publisher-generated event enum constraint.
    # Extend its allowlist while preserving all prior notification categories.
    cur.execute("""
    ALTER TABLE admin_event_subscriptions
      DROP CONSTRAINT IF EXISTS admin_event_subscriptions_event_type_check;
    ALTER TABLE admin_event_subscriptions ADD CONSTRAINT admin_event_subscriptions_event_type_check
      CHECK(event_type = ANY(ARRAY['new_signup','direct_listing','broker_listing_request','buy_request',
        'partner_agent','partner_operator','partner_loan_consultant','partner_lodging_operator',
        'ota_booking_link_request','survey_request']));
    """)
    for column in ("check_business_report", "check_operation_succession", "check_fee_arrears"):
        name = "auction_items_" + column + "_check"
        cur.execute(f"""DO $$ BEGIN
          IF NOT EXISTS(SELECT 1 FROM pg_constraint WHERE conrelid='auction_items'::regclass AND conname='{name}') THEN
            ALTER TABLE auction_items ADD CONSTRAINT {name}
              CHECK({column} = ANY(ARRAY['need_check','ok','issue']));
          END IF;
        END $$""")
    cur.execute("INSERT INTO app_meta(key,value) VALUES('survey_settings',%s) ON CONFLICT(key) DO NOTHING",
                [Json(DEFAULT_SETTINGS)])
    cur.execute("INSERT INTO legal_documents(doc_type,content) VALUES('survey_terms',%s) ON CONFLICT(doc_type) DO NOTHING",
                [SURVEY_TERMS_SEED])
    cur.execute("""INSERT INTO admin_event_subscriptions(admin_user_id,event_type,in_app_enabled,email_enabled)
      SELECT id,'survey_request',TRUE,FALSE FROM admin_users
      ON CONFLICT(admin_user_id,event_type) DO NOTHING""")