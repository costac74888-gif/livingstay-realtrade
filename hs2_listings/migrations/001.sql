DO $$ BEGIN
 IF current_setting('hs2.fixture_cluster',true) IS DISTINCT FROM 'phase2-isolated' THEN
  RAISE EXCEPTION 'owned fixture only';
 END IF;
END $$;
CREATE TABLE hs2_dev.registration_applications(
 id uuid PRIMARY KEY,
 user_id bigint NOT NULL REFERENCES hs2_fixture_legacy.users(id),
 context_id text NOT NULL,
 candidate_id uuid NOT NULL REFERENCES hs2_dev.candidates(id),
 revision integer NOT NULL CHECK(revision>=1),
 status text NOT NULL CHECK(status IN ('draft','submitted','approved','rejected','withdrawn')),
 payload jsonb NOT NULL CHECK(jsonb_typeof(payload)='object'),
 listing_id uuid REFERENCES hs2_dev.stay_listings(id),
 public_id uuid UNIQUE,
 reviewed_revision integer,
 reviewer_id bigint,
 review_note text,
 approved_until timestamptz,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 CHECK(status<>'approved' OR (reviewed_revision=revision AND reviewer_id>0 AND approved_until IS NOT NULL AND listing_id IS NOT NULL))
);
CREATE TABLE hs2_dev.registration_photos(
 id uuid PRIMARY KEY,
 user_id bigint NOT NULL REFERENCES hs2_fixture_legacy.users(id),
 context_id text NOT NULL,
 mime text NOT NULL CHECK(mime IN ('image/png','image/jpeg','image/webp')),
 content bytea NOT NULL CHECK(octet_length(content) BETWEEN 24 AND 524288)
);
CREATE TABLE hs2_dev.registration_events(
 sequence bigserial PRIMARY KEY,
 application_id uuid NOT NULL REFERENCES hs2_dev.registration_applications(id),
 revision integer NOT NULL,
 actor_id bigint NOT NULL,
 actor_kind text NOT NULL CHECK(actor_kind IN ('member','admin')),
 event text NOT NULL,
 at timestamptz NOT NULL DEFAULT clock_timestamp()
);
REVOKE ALL ON hs2_dev.registration_applications,hs2_dev.registration_photos,hs2_dev.registration_events
 FROM hs2_fixture_public,hs2_fixture_writer;
CREATE INDEX registration_owner ON hs2_dev.registration_applications(user_id,context_id,updated_at DESC);
