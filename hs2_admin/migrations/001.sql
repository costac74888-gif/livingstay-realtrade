CREATE TABLE hs2_dev.admin_records(
 id uuid PRIMARY KEY,
 kind text NOT NULL CHECK(kind IN('faq','policy','promotion','report','review')),
 revision integer NOT NULL CHECK(revision>0),
 status text NOT NULL CHECK(status IN('draft','approved','archived')),
 payload jsonb NOT NULL,
 admin_id bigint NOT NULL CHECK(admin_id>0),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE hs2_dev.admin_record_events(
 id bigserial PRIMARY KEY,
 record_id uuid NOT NULL REFERENCES hs2_dev.admin_records(id),
 revision integer NOT NULL,
 admin_id bigint NOT NULL,
 action text NOT NULL,
 note text NOT NULL,
 at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TRIGGER immutable_admin_record_events BEFORE UPDATE OR DELETE ON hs2_dev.admin_record_events
 FOR EACH ROW EXECUTE FUNCTION hs2_dev.reject_quote_receipt_mutation();
