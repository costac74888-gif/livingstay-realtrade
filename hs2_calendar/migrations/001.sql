DO $$ BEGIN
 IF current_setting('hs2.fixture_cluster',true) IS DISTINCT FROM 'phase2-isolated' THEN
  RAISE EXCEPTION 'owned fixture only';
 END IF;
END $$;
CREATE TABLE hs2_dev.calendar_versions(
 id uuid PRIMARY KEY,
 application_id uuid NOT NULL REFERENCES hs2_dev.registration_applications(id),
 version integer NOT NULL CHECK(version>=1),
 source_revision integer NOT NULL CHECK(source_revision>=1),
 payload jsonb NOT NULL CHECK(jsonb_typeof(payload)='object'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(application_id,version)
);
CREATE TRIGGER calendar_version_immutable BEFORE UPDATE OR DELETE ON hs2_dev.calendar_versions
 FOR EACH ROW EXECUTE FUNCTION hs2_dev.immutable_record();
REVOKE ALL ON hs2_dev.calendar_versions FROM hs2_fixture_public,hs2_fixture_writer;
