CREATE TABLE hs2_dev.consumer_quote_receipts(
 id uuid PRIMARY KEY,
 user_id bigint NOT NULL REFERENCES hs2_fixture_legacy.users(id),
 public_id uuid NOT NULL,
 snapshot_id uuid NOT NULL UNIQUE REFERENCES hs2_dev.price_snapshots(id),
 request_id uuid NOT NULL,
 request_hash text NOT NULL,
 source_version text NOT NULL,
 application_revision integer NOT NULL,
 guests integer NOT NULL CHECK(guests BETWEEN 1 AND 100),
 public_quote jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 expires_at timestamptz NOT NULL DEFAULT clock_timestamp()+interval '10 minutes',
 UNIQUE(user_id,request_id),
 CHECK(expires_at>created_at)
);
CREATE OR REPLACE FUNCTION hs2_dev.reject_quote_receipt_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'immutable consumer quote receipt'; END $$;
CREATE TRIGGER quote_receipt_immutable BEFORE UPDATE OR DELETE ON hs2_dev.consumer_quote_receipts
FOR EACH ROW EXECUTE FUNCTION hs2_dev.reject_quote_receipt_mutation();
