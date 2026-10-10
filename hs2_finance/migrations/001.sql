CREATE TABLE hs2_dev.financial_contracts(
 id uuid PRIMARY KEY,
 booking_id uuid NOT NULL UNIQUE REFERENCES hs2_dev.bookings(id),
 user_id bigint NOT NULL REFERENCES hs2_fixture_legacy.users(id),
 request_id uuid NOT NULL,
 terms jsonb NOT NULL,
 sandbox boolean NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(user_id,request_id)
);
CREATE TABLE hs2_dev.financial_events(
 id uuid PRIMARY KEY,
 contract_id uuid NOT NULL REFERENCES hs2_dev.financial_contracts(id),
 kind text NOT NULL CHECK(kind IN('capture','late_capture','refund_review','deposit_review','payout_review')),
 reference text,
 request_hash text NOT NULL,
 amount_krw bigint NOT NULL CHECK(amount_krw>0),
 at timestamptz NOT NULL DEFAULT clock_timestamp(),
 payload jsonb NOT NULL DEFAULT '{}'::jsonb,
 UNIQUE(reference)
);
CREATE UNIQUE INDEX one_financial_capture ON hs2_dev.financial_events(contract_id)
 WHERE kind IN('capture','late_capture');
CREATE UNIQUE INDEX one_financial_review ON hs2_dev.financial_events(contract_id,kind)
 WHERE kind IN('refund_review','deposit_review','payout_review');
CREATE TABLE hs2_dev.paid_booking_cancellations(
 booking_id uuid PRIMARY KEY REFERENCES hs2_dev.bookings(id),
 contract_id uuid NOT NULL UNIQUE REFERENCES hs2_dev.financial_contracts(id),
 actor_user_id bigint NOT NULL REFERENCES hs2_fixture_legacy.users(id),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TRIGGER immutable_financial_contracts BEFORE UPDATE OR DELETE ON hs2_dev.financial_contracts
 FOR EACH ROW EXECUTE FUNCTION hs2_dev.reject_quote_receipt_mutation();
CREATE TRIGGER immutable_financial_events BEFORE UPDATE OR DELETE ON hs2_dev.financial_events
 FOR EACH ROW EXECUTE FUNCTION hs2_dev.reject_quote_receipt_mutation();
CREATE TRIGGER immutable_paid_cancellations BEFORE UPDATE OR DELETE ON hs2_dev.paid_booking_cancellations
 FOR EACH ROW EXECUTE FUNCTION hs2_dev.reject_quote_receipt_mutation();
