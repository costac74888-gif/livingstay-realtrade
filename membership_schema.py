"""Manual-bank membership ledger; independent of business/partner roles."""


def ensure_membership_schema(cur):
    cur.execute("""
    CREATE TABLE IF NOT EXISTS membership_payments (
      id BIGSERIAL PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
      request_no TEXT NOT NULL UNIQUE, request_token TEXT NOT NULL,
      depositor_name TEXT NOT NULL, amount INTEGER NOT NULL DEFAULT 29000 CHECK(amount=29000),
      bank JSONB NOT NULL, status TEXT NOT NULL DEFAULT 'pending'
        CHECK(status = ANY(ARRAY['pending','approved','rejected','canceled','revoked'])),
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      approved_by INTEGER, admin_note TEXT NOT NULL DEFAULT '',
      UNIQUE(user_id,request_token)
    );
    CREATE UNIQUE INDEX IF NOT EXISTS membership_one_pending
      ON membership_payments(user_id) WHERE status='pending';
    CREATE INDEX IF NOT EXISTS membership_payment_queue ON membership_payments(status,created_at DESC);
    CREATE TABLE IF NOT EXISTS membership_periods (
      id BIGSERIAL PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
      payment_id BIGINT NOT NULL UNIQUE REFERENCES membership_payments(id),
      starts_at TIMESTAMPTZ NOT NULL, ends_at TIMESTAMPTZ NOT NULL,
      revoked_at TIMESTAMPTZ, CHECK(ends_at>starts_at)
    );
    CREATE INDEX IF NOT EXISTS membership_period_user ON membership_periods(user_id,ends_at);
    CREATE TABLE IF NOT EXISTS membership_checks (
      id BIGSERIAL PRIMARY KEY, period_id BIGINT NOT NULL UNIQUE REFERENCES membership_periods(id),
      user_id INTEGER NOT NULL REFERENCES users(id), request_no TEXT NOT NULL UNIQUE,
      request_token TEXT NOT NULL, building_id INTEGER, auction_id BIGINT,
      title TEXT NOT NULL, address TEXT NOT NULL, memo TEXT NOT NULL DEFAULT '',
      status TEXT NOT NULL DEFAULT 'received'
        CHECK(status = ANY(ARRAY['received','investigating','reported'])),
      business_report TEXT NOT NULL DEFAULT 'need_check'
        CHECK(business_report = ANY(ARRAY['need_check','ok','issue'])),
      operation_succession TEXT NOT NULL DEFAULT 'need_check'
        CHECK(operation_succession = ANY(ARRAY['need_check','ok','issue'])),
      fee_arrears TEXT NOT NULL DEFAULT 'need_check'
        CHECK(fee_arrears = ANY(ARRAY['need_check','ok','issue'])),
      report TEXT NOT NULL DEFAULT '', created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), UNIQUE(user_id,request_token),
      CHECK(building_id IS NOT NULL OR auction_id IS NOT NULL)
    );
    CREATE TABLE IF NOT EXISTS membership_history (
      id BIGSERIAL PRIMARY KEY, payment_id BIGINT REFERENCES membership_payments(id),
      check_id BIGINT REFERENCES membership_checks(id), actor TEXT NOT NULL,
      event TEXT NOT NULL, note TEXT NOT NULL DEFAULT '', created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """)