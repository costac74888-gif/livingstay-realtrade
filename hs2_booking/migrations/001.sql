CREATE TABLE hs2_dev.bookings(
 id uuid PRIMARY KEY,
 user_id bigint NOT NULL REFERENCES hs2_fixture_legacy.users(id),
 application_id uuid NOT NULL REFERENCES hs2_dev.registration_applications(id),
 receipt_id uuid NOT NULL UNIQUE REFERENCES hs2_dev.consumer_quote_receipts(id),
 snapshot_id uuid NOT NULL REFERENCES hs2_dev.price_snapshots(id),
 request_id uuid NOT NULL,
 request_hash text NOT NULL,
 status text NOT NULL CHECK(status IN('pending_operator','awaiting_payment','confirmed','rejected','cancelled','expired')),
 revision integer NOT NULL DEFAULT 1 CHECK(revision>0),
 check_in date NOT NULL,check_out date NOT NULL CHECK(check_out>check_in),
 deadline timestamptz,
 payment_reference text UNIQUE,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(user_id,request_id),
 CHECK((status IN('pending_operator','awaiting_payment'))=(deadline IS NOT NULL)),
 CHECK((status='confirmed')=(payment_reference IS NOT NULL))
);
CREATE TABLE hs2_dev.booking_slots(
 booking_id uuid NOT NULL REFERENCES hs2_dev.bookings(id),
 pool_id uuid NOT NULL REFERENCES hs2_dev.inventory_pools(id),
 PRIMARY KEY(booking_id,pool_id)
);
CREATE INDEX booking_active_periods ON hs2_dev.bookings(check_in,check_out)
WHERE status IN('pending_operator','awaiting_payment','confirmed');
CREATE TABLE hs2_dev.booking_events(
 id bigserial PRIMARY KEY,
 booking_id uuid NOT NULL REFERENCES hs2_dev.bookings(id),
 actor_user_id bigint REFERENCES hs2_fixture_legacy.users(id),
 kind text NOT NULL,
 at timestamptz NOT NULL DEFAULT clock_timestamp(),
 payload jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE OR REPLACE FUNCTION hs2_dev.protect_booking_price_identity() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF ROW(OLD.user_id,OLD.application_id,OLD.receipt_id,OLD.snapshot_id,OLD.request_id,OLD.request_hash,OLD.check_in,OLD.check_out,OLD.created_at)
 IS DISTINCT FROM ROW(NEW.user_id,NEW.application_id,NEW.receipt_id,NEW.snapshot_id,NEW.request_id,NEW.request_hash,NEW.check_in,NEW.check_out,NEW.created_at)
 THEN RAISE EXCEPTION 'immutable booking price and identity'; END IF;
 IF OLD.status IN('confirmed','rejected','cancelled','expired') AND NEW IS DISTINCT FROM OLD
 THEN RAISE EXCEPTION 'terminal booking state'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER immutable_booking_identity BEFORE UPDATE ON hs2_dev.bookings
FOR EACH ROW EXECUTE FUNCTION hs2_dev.protect_booking_price_identity();
CREATE TRIGGER immutable_booking_events BEFORE UPDATE OR DELETE ON hs2_dev.booking_events
FOR EACH ROW EXECUTE FUNCTION hs2_dev.reject_quote_receipt_mutation();
