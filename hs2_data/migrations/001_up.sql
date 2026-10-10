-- Development fixture migration ONLY. Not an operational migration.
DO $$ BEGIN
  IF current_setting('hs2.fixture_cluster', true) IS DISTINCT FROM 'phase2-isolated' THEN
    RAISE EXCEPTION 'isolated fixture marker required';
  END IF;
END $$;
CREATE SCHEMA hs2_dev;
CREATE TABLE hs2_dev.migration_receipts(version integer PRIMARY KEY, sha256 text NOT NULL);
CREATE TABLE hs2_dev.candidates(
  id uuid PRIMARY KEY,
  identity_key text,
  identity_confirmed boolean NOT NULL DEFAULT false,
  building_use text NOT NULL,
  road_address text NOT NULL,
  lat numeric, lng numeric,
  evidence_version text NOT NULL CHECK(length(evidence_version)>0),
  CHECK(NOT identity_confirmed OR length(identity_key)>0 AND identity_key IS NOT NULL),
  CHECK(lat IS NULL OR lat BETWEEN -90 AND 90),
  CHECK(lng IS NULL OR lng BETWEEN -180 AND 180)
);
CREATE UNIQUE INDEX candidate_confirmed_identity ON hs2_dev.candidates(identity_key) WHERE identity_confirmed;
CREATE TABLE hs2_dev.candidate_identifiers(
  id uuid PRIMARY KEY,
  candidate_id uuid NOT NULL REFERENCES hs2_dev.candidates(id) ON DELETE RESTRICT,
  source text NOT NULL CHECK(length(source)>0),
  external_key text NOT NULL CHECK(length(external_key)>0),
  evidence_version text NOT NULL CHECK(length(evidence_version)>0),
  verified boolean NOT NULL DEFAULT false
);
CREATE UNIQUE INDEX confirmed_source_identifier ON hs2_dev.candidate_identifiers(source,external_key) WHERE verified;
CREATE TABLE hs2_dev.registered_buildings(
  id uuid PRIMARY KEY,
  candidate_id uuid NOT NULL UNIQUE REFERENCES hs2_dev.candidates(id) ON DELETE RESTRICT
);
CREATE TABLE hs2_dev.master_links(
  candidate_id uuid PRIMARY KEY REFERENCES hs2_dev.candidates(id) ON DELETE RESTRICT,
  master_id bigint NOT NULL UNIQUE REFERENCES hs2_fixture_legacy.master_buildings(id) ON DELETE RESTRICT,
  identity_key text NOT NULL,
  evidence_version text NOT NULL CHECK(length(evidence_version)>0)
);
CREATE FUNCTION hs2_dev.identity_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_TABLE_NAME='registered_buildings' THEN
    IF TG_OP='UPDATE' AND OLD.candidate_id<>NEW.candidate_id THEN
      RAISE EXCEPTION 'registered physical identity cannot be transferred';
    END IF;
    IF NOT EXISTS(SELECT 1 FROM hs2_dev.candidates WHERE id=NEW.candidate_id AND identity_confirmed) THEN
      RAISE EXCEPTION 'confirmed physical candidate required';
    END IF;
  ELSIF TG_TABLE_NAME='master_links' THEN
    IF NOT EXISTS(SELECT 1 FROM hs2_dev.candidates WHERE id=NEW.candidate_id
         AND identity_confirmed AND identity_key=NEW.identity_key)
       OR NOT EXISTS(SELECT 1 FROM hs2_fixture_legacy.master_buildings
         WHERE id=NEW.master_id AND identity_key=NEW.identity_key)
       OR (SELECT count(*) FROM hs2_fixture_legacy.master_buildings
         WHERE identity_key=NEW.identity_key)<>1 THEN
      RAISE EXCEPTION 'legacy link must be exact and unique';
    END IF;
  ELSE
    IF (NEW.identity_key IS DISTINCT FROM OLD.identity_key OR
        NEW.identity_confirmed IS DISTINCT FROM OLD.identity_confirmed)
       AND (EXISTS(SELECT 1 FROM hs2_dev.registered_buildings WHERE candidate_id=OLD.id)
            OR EXISTS(SELECT 1 FROM hs2_dev.master_links WHERE candidate_id=OLD.id)) THEN
      RAISE EXCEPTION 'referenced physical identity is immutable';
    END IF;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER registration_identity BEFORE INSERT OR UPDATE ON hs2_dev.registered_buildings
 FOR EACH ROW EXECUTE FUNCTION hs2_dev.identity_guard();
CREATE TRIGGER master_identity BEFORE INSERT OR UPDATE ON hs2_dev.master_links
 FOR EACH ROW EXECUTE FUNCTION hs2_dev.identity_guard();
CREATE TRIGGER candidate_identity BEFORE UPDATE ON hs2_dev.candidates
 FOR EACH ROW EXECUTE FUNCTION hs2_dev.identity_guard();
CREATE TABLE hs2_dev.inventory_pools(
  id uuid PRIMARY KEY,
  registered_building_id uuid NOT NULL REFERENCES hs2_dev.registered_buildings(id) ON DELETE RESTRICT,
  unit_key text NOT NULL CHECK(length(unit_key)>0),
  UNIQUE(id,registered_building_id),
  UNIQUE(registered_building_id,unit_key)
);
CREATE TABLE hs2_dev.inventory_members(
  registered_building_id uuid NOT NULL,
  parent_id uuid NOT NULL,
  child_id uuid NOT NULL,
  PRIMARY KEY(parent_id,child_id),
  CHECK(parent_id<>child_id),
  FOREIGN KEY(parent_id,registered_building_id) REFERENCES hs2_dev.inventory_pools(id,registered_building_id) ON DELETE RESTRICT,
  FOREIGN KEY(child_id,registered_building_id) REFERENCES hs2_dev.inventory_pools(id,registered_building_id) ON DELETE RESTRICT
);
CREATE FUNCTION hs2_dev.inventory_cycle_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  -- Serialize graph edits per building; prevents concurrently-created cycles.
  PERFORM 1 FROM hs2_dev.registered_buildings WHERE id=NEW.registered_building_id FOR UPDATE;
  IF EXISTS(WITH RECURSIVE reach(id) AS (
      SELECT NEW.child_id UNION SELECT m.child_id FROM hs2_dev.inventory_members m JOIN reach r ON m.parent_id=r.id
    ) SELECT 1 FROM reach WHERE id=NEW.parent_id) THEN
    RAISE EXCEPTION 'inventory cycle forbidden';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER inventory_cycle BEFORE INSERT ON hs2_dev.inventory_members
 FOR EACH ROW EXECUTE FUNCTION hs2_dev.inventory_cycle_guard();
CREATE TABLE hs2_dev.registration_grants(
  id uuid PRIMARY KEY,
  registered_building_id uuid NOT NULL REFERENCES hs2_dev.registered_buildings(id) ON DELETE RESTRICT,
  user_id bigint NOT NULL REFERENCES hs2_fixture_legacy.users(id) ON DELETE RESTRICT,
  role text NOT NULL CHECK(role IN ('owner','operator','agent')),
  rights_evidence text NOT NULL CHECK(length(rights_evidence)>0),
  approved boolean NOT NULL DEFAULT false,
  UNIQUE(registered_building_id,user_id,role),
  UNIQUE(id,registered_building_id,user_id),
  UNIQUE(id,registered_building_id)
);
CREATE TABLE hs2_dev.grant_units(
  grant_id uuid NOT NULL,
  pool_id uuid NOT NULL,
  registered_building_id uuid NOT NULL,
  PRIMARY KEY(grant_id,pool_id,registered_building_id),
  FOREIGN KEY(grant_id,registered_building_id) REFERENCES hs2_dev.registration_grants(id,registered_building_id) ON DELETE RESTRICT,
  FOREIGN KEY(pool_id,registered_building_id) REFERENCES hs2_dev.inventory_pools(id,registered_building_id) ON DELETE RESTRICT
);
CREATE TABLE hs2_dev.stay_listings(
  id uuid PRIMARY KEY,
  public_id uuid NOT NULL UNIQUE,
  registered_building_id uuid NOT NULL,
  creator_user_id bigint NOT NULL,
  pool_id uuid NOT NULL,
  grant_id uuid NOT NULL,
  disclosure_scope text NOT NULL DEFAULT 'limited' CHECK(disclosure_scope='limited'),
  status text NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','published','withdrawn')),
  classification_id uuid,
  CHECK(public_id<>id AND substring(public_id::text,15,1)='4'
        AND substring(public_id::text,20,1) IN ('8','9','a','b')),
  FOREIGN KEY(grant_id,registered_building_id,creator_user_id)
    REFERENCES hs2_dev.registration_grants(id,registered_building_id,user_id) ON DELETE RESTRICT,
  FOREIGN KEY(grant_id,pool_id,registered_building_id)
    REFERENCES hs2_dev.grant_units(grant_id,pool_id,registered_building_id) ON DELETE RESTRICT
);
CREATE TABLE hs2_dev.classification_decisions(
  id uuid PRIMARY KEY,
  listing_id uuid NOT NULL REFERENCES hs2_dev.stay_listings(id) ON DELETE RESTRICT,
  kind text NOT NULL CHECK(kind IN ('lodging','non_lodging','unresolved')),
  evidence_id text NOT NULL,
  decision_version text NOT NULL CHECK(length(decision_version)>0),
  building_use text NOT NULL,
  channel text NOT NULL,
  CHECK(kind='unresolved' OR length(evidence_id)>0),
  UNIQUE(id,listing_id),
  UNIQUE(listing_id,decision_version,evidence_id,kind)
);
ALTER TABLE hs2_dev.stay_listings ADD FOREIGN KEY(classification_id,id)
 REFERENCES hs2_dev.classification_decisions(id,listing_id) ON DELETE RESTRICT;
CREATE FUNCTION hs2_dev.listing_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.creator_user_id::text IS DISTINCT FROM current_setting('hs2.actor_user', true) THEN
    RAISE EXCEPTION 'actor mismatch';
  END IF;
  IF NOT EXISTS(SELECT 1 FROM hs2_dev.registration_grants g JOIN hs2_fixture_legacy.users u ON u.id=g.user_id
       WHERE g.id=NEW.grant_id AND g.approved AND u.active) THEN
    RAISE EXCEPTION 'approved active scoped rights required';
  END IF;
  IF NEW.public_id IN (SELECT id FROM hs2_dev.candidates UNION SELECT id FROM hs2_dev.registered_buildings
                        UNION SELECT id FROM hs2_dev.inventory_pools) THEN
    RAISE EXCEPTION 'private identifier cannot be public';
  END IF;
  IF TG_OP='UPDATE' THEN
    IF OLD.creator_user_id<>NEW.creator_user_id OR OLD.registered_building_id<>NEW.registered_building_id
       OR OLD.pool_id<>NEW.pool_id OR OLD.grant_id<>NEW.grant_id OR OLD.public_id<>NEW.public_id THEN
      RAISE EXCEPTION 'listing identity and authority cannot be transferred';
    END IF;
    IF OLD.status='withdrawn' AND NEW.status<>'withdrawn' THEN
      RAISE EXCEPTION 'withdrawal is terminal';
    END IF;
  END IF;
  IF NEW.status='published' AND NOT EXISTS(SELECT 1 FROM hs2_dev.classification_decisions
       WHERE id=NEW.classification_id AND listing_id=NEW.id AND kind<>'unresolved') THEN
    RAISE EXCEPTION 'classification review required';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER listing_rights BEFORE INSERT OR UPDATE ON hs2_dev.stay_listings
 FOR EACH ROW EXECUTE FUNCTION hs2_dev.listing_guard();
CREATE TABLE hs2_dev.tariff_versions(
  id uuid PRIMARY KEY,
  listing_id uuid NOT NULL REFERENCES hs2_dev.stay_listings(id) ON DELETE RESTRICT,
  version text NOT NULL CHECK(length(version)>0),
  payload jsonb NOT NULL CHECK(jsonb_typeof(payload)='object'),
  UNIQUE(listing_id,version)
);
CREATE TABLE hs2_dev.price_snapshots(
  id uuid PRIMARY KEY,
  listing_id uuid NOT NULL REFERENCES hs2_dev.stay_listings(id) ON DELETE RESTRICT,
  check_in date NOT NULL, check_out date NOT NULL,
  kind text NOT NULL CHECK(kind IN ('lodging','non_lodging')),
  currency text NOT NULL CHECK(currency='KRW'),
  tariff_version text NOT NULL,
  terms_version text NOT NULL CHECK(length(terms_version)>0),
  classification_evidence text NOT NULL,
  classification_version text NOT NULL,
  total_krw bigint NOT NULL CHECK(total_krw>0),
  payload jsonb NOT NULL CHECK(jsonb_typeof(payload)='object'),
  FOREIGN KEY(listing_id,tariff_version) REFERENCES hs2_dev.tariff_versions(listing_id,version) ON DELETE RESTRICT,
  FOREIGN KEY(listing_id,classification_version,classification_evidence,kind)
    REFERENCES hs2_dev.classification_decisions(listing_id,decision_version,evidence_id,kind) ON DELETE RESTRICT,
  CHECK(check_out-check_in >= CASE WHEN kind='lodging' THEN 1 ELSE 7 END),
  CHECK(payload->>'listing_id'=listing_id::text AND payload->>'currency'=currency
    AND (payload->>'total_krw')::bigint=total_krw AND payload->>'kind'=kind
    AND payload->>'check_in'=check_in::text AND payload->>'check_out'=check_out::text
    AND payload->>'tariff_version'=tariff_version AND payload->>'terms_version'=terms_version),
  CHECK(payload ?& ARRAY['listing_id','currency','total_krw','kind','check_in','check_out',
                         'tariff_version','terms_version','lines','adjustments'])
);
CREATE FUNCTION hs2_dev.immutable_record() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'append-only record'; END $$;
CREATE TRIGGER decisions_immutable BEFORE UPDATE OR DELETE ON hs2_dev.classification_decisions
 FOR EACH ROW EXECUTE FUNCTION hs2_dev.immutable_record();
CREATE TRIGGER tariffs_immutable BEFORE UPDATE OR DELETE ON hs2_dev.tariff_versions
 FOR EACH ROW EXECUTE FUNCTION hs2_dev.immutable_record();
CREATE TRIGGER snapshots_immutable BEFORE UPDATE OR DELETE ON hs2_dev.price_snapshots
 FOR EACH ROW EXECUTE FUNCTION hs2_dev.immutable_record();
CREATE TRIGGER inventory_edges_immutable BEFORE UPDATE ON hs2_dev.inventory_members
 FOR EACH ROW EXECUTE FUNCTION hs2_dev.immutable_record();
CREATE FUNCTION hs2_dev.snapshot_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE item jsonb; pos date:=NEW.check_in; finish date; total numeric:=0;
        names text[]:=ARRAY[]::text[]; label text;
BEGIN
  IF NEW.payload->>'listing_id' IS DISTINCT FROM NEW.listing_id::text
     OR NEW.payload->>'currency' IS DISTINCT FROM NEW.currency
     OR NEW.payload->>'kind' IS DISTINCT FROM NEW.kind
     OR NEW.payload->>'check_in' IS DISTINCT FROM NEW.check_in::text
     OR NEW.payload->>'check_out' IS DISTINCT FROM NEW.check_out::text
     OR NEW.payload->>'tariff_version' IS DISTINCT FROM NEW.tariff_version
     OR NEW.payload->>'terms_version' IS DISTINCT FROM NEW.terms_version
     OR jsonb_typeof(NEW.payload->'total_krw') IS DISTINCT FROM 'number'
     OR (NEW.payload->>'total_krw') !~ '^[0-9]+$'
     OR (NEW.payload->>'total_krw')::numeric IS DISTINCT FROM NEW.total_krw::numeric THEN
    RAISE EXCEPTION 'snapshot metadata mismatch';
  END IF;
  IF jsonb_typeof(NEW.payload->'lines') IS DISTINCT FROM 'array'
     OR jsonb_array_length(NEW.payload->'lines')=0
     OR jsonb_typeof(NEW.payload->'adjustments') IS DISTINCT FROM 'array' THEN
    RAISE EXCEPTION 'explicit snapshot lines and adjustments required';
  END IF;
  FOR item IN SELECT value FROM jsonb_array_elements(NEW.payload->'lines') LOOP
    IF item->>'start' IS NULL OR item->>'end' IS NULL OR item->>'unit' IS NULL
       OR jsonb_typeof(item->'amount_krw') IS DISTINCT FROM 'number'
       OR (item->>'amount_krw') !~ '^[0-9]+$'
       OR (item->>'amount_krw')::numeric NOT BETWEEN 1 AND 9223372036854775807
       OR (item->>'start')::date<>pos THEN
      RAISE EXCEPTION 'invalid snapshot price coverage';
    END IF;
    finish:=(item->>'end')::date;
    IF (NEW.kind='lodging' AND (item->>'unit'<>'night' OR finish-pos<>1))
       OR (NEW.kind='non_lodging' AND NOT
          ((item->>'unit'='week' AND finish-pos=7) OR (item->>'unit'='month' AND finish-pos>=7))) THEN
      RAISE EXCEPTION 'invalid snapshot price unit';
    END IF;
    pos:=finish; total:=total+(item->>'amount_krw')::numeric;
  END LOOP;
  FOR item IN SELECT value FROM jsonb_array_elements(NEW.payload->'adjustments') LOOP
    IF jsonb_typeof(item) IS DISTINCT FROM 'array' OR jsonb_array_length(item)<>2
       OR jsonb_typeof(item->0) IS DISTINCT FROM 'string' OR length(item->>0)=0
       OR jsonb_typeof(item->1) IS DISTINCT FROM 'number' OR (item->>1) !~ '^-?[0-9]+$'
       OR abs((item->>1)::numeric)>9223372036854775807 THEN
      RAISE EXCEPTION 'invalid snapshot adjustment';
    END IF;
    label:=item->>0;
    IF label=ANY(names) THEN RAISE EXCEPTION 'duplicate adjustment'; END IF;
    names:=array_append(names,label); total:=total+(item->>1)::numeric;
  END LOOP;
  IF pos<>NEW.check_out OR total<>NEW.total_krw
     OR NEW.payload->>'classification_evidence' IS DISTINCT FROM NEW.classification_evidence
     OR NEW.payload->>'classification_version' IS DISTINCT FROM NEW.classification_version THEN
    RAISE EXCEPTION 'snapshot total or evidence mismatch';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER snapshot_components BEFORE INSERT ON hs2_dev.price_snapshots
 FOR EACH ROW EXECUTE FUNCTION hs2_dev.snapshot_guard();
CREATE VIEW hs2_dev.limited_stay_listings AS
 SELECT l.public_id, COALESCE(d.kind,'unresolved') AS stay_kind,
        'withheld'::text AS location_precision
 FROM hs2_dev.stay_listings l LEFT JOIN hs2_dev.classification_decisions d ON d.id=l.classification_id
 WHERE l.disclosure_scope='limited' AND l.status='published';
GRANT USAGE ON SCHEMA hs2_dev TO hs2_fixture_writer, hs2_fixture_public;
GRANT SELECT ON ALL TABLES IN SCHEMA hs2_dev TO hs2_fixture_writer;
GRANT INSERT,UPDATE ON hs2_dev.stay_listings TO hs2_fixture_writer;
GRANT SELECT ON hs2_dev.limited_stay_listings TO hs2_fixture_public;
