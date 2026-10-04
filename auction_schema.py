"""신규 공매 테이블만 생성한다. 기존 마스터의 키·내용을 변경하지 않는다."""


def ensure_auction_schema(cur):
    cur.execute("""
    CREATE TABLE IF NOT EXISTS auction_items (
      id SERIAL PRIMARY KEY, source TEXT NOT NULL DEFAULT 'onbid',
      source_item_id TEXT NOT NULL, pbct_cdtn_no TEXT NOT NULL DEFAULT '',
      sale_kind TEXT, usage_name TEXT, lodging_category TEXT,
      title TEXT, unit_label TEXT, address_road TEXT, address_jibun TEXT,
      area_m2 REAL, appraisal_price BIGINT, min_bid_price BIGINT, min_bid_ratio REAL,
      round_no INTEGER, failed_count INTEGER DEFAULT 0,
      bid_start_at TIMESTAMPTZ, bid_end_at TIMESTAMPTZ,
      status TEXT NOT NULL DEFAULT 'closed', status_changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      disposal_method TEXT, notice_org TEXT, notice_no TEXT, detail_url TEXT,
      lat DOUBLE PRECISION, lng DOUBLE PRECISION,
      master_building_id INTEGER REFERENCES master_buildings(id) ON DELETE SET NULL,
      raw JSONB NOT NULL DEFAULT '{}'::jsonb, detail_fingerprint TEXT,
      first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      UNIQUE(source,source_item_id,pbct_cdtn_no)
    );
    CREATE TABLE IF NOT EXISTS auction_rounds (
      id SERIAL PRIMARY KEY, auction_item_id INTEGER NOT NULL REFERENCES auction_items(id) ON DELETE CASCADE,
      round_no INTEGER NOT NULL, bid_start_at TIMESTAMPTZ, bid_end_at TIMESTAMPTZ,
      min_bid_price BIGINT, result TEXT, result_at TIMESTAMPTZ,
      source_round_key TEXT NOT NULL DEFAULT ''
    );
    ALTER TABLE auction_rounds ADD COLUMN IF NOT EXISTS source_round_key TEXT NOT NULL DEFAULT '';
    ALTER TABLE auction_rounds ADD COLUMN IF NOT EXISTS result_at TIMESTAMPTZ;
    ALTER TABLE auction_rounds DROP CONSTRAINT IF EXISTS auction_rounds_auction_item_id_round_no_key;
    UPDATE auction_rounds SET source_round_key='legacy:'||id WHERE source_round_key='';
    CREATE UNIQUE INDEX IF NOT EXISTS idx_auction_round_source ON auction_rounds(auction_item_id,source_round_key);
    CREATE TABLE IF NOT EXISTS auction_photos (
      id SERIAL PRIMARY KEY, auction_item_id INTEGER NOT NULL REFERENCES auction_items(id) ON DELETE CASCADE,
      url TEXT NOT NULL, sort_order INTEGER NOT NULL DEFAULT 0,
      UNIQUE(auction_item_id,url)
    );
    CREATE INDEX IF NOT EXISTS idx_auction_status_deadline ON auction_items(status,bid_end_at);
    CREATE INDEX IF NOT EXISTS idx_auction_coords ON auction_items(lat,lng);
    CREATE INDEX IF NOT EXISTS idx_auction_building ON auction_items(master_building_id);
    CREATE INDEX IF NOT EXISTS idx_auction_category ON auction_items(lodging_category);
    CREATE INDEX IF NOT EXISTS idx_auction_property ON auction_items(source,source_item_id);
    CREATE TABLE IF NOT EXISTS auction_watches (
      user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      master_building_id INTEGER NOT NULL REFERENCES master_buildings(id) ON DELETE CASCADE,
      enabled BOOLEAN NOT NULL DEFAULT TRUE, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      PRIMARY KEY(user_id,master_building_id)
    );
    """)