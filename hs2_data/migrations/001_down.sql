-- Fixture rollback, no CASCADE and no legacy table/sequence writes.
DO $$ BEGIN
  IF current_setting('hs2.fixture_cluster', true) IS DISTINCT FROM 'phase2-isolated' THEN
    RAISE EXCEPTION 'isolated fixture marker required';
  END IF;
END $$;
DROP VIEW hs2_dev.limited_stay_listings;
DROP TABLE hs2_dev.price_snapshots;
DROP TABLE hs2_dev.tariff_versions;
ALTER TABLE hs2_dev.stay_listings DROP CONSTRAINT stay_listings_classification_id_id_fkey;
DROP TABLE hs2_dev.classification_decisions;
DROP TABLE hs2_dev.stay_listings;
DROP TABLE hs2_dev.grant_units;
DROP TABLE hs2_dev.registration_grants;
DROP TABLE hs2_dev.inventory_members;
DROP TABLE hs2_dev.inventory_pools;
DROP TABLE hs2_dev.master_links;
DROP TABLE hs2_dev.registered_buildings;
DROP TABLE hs2_dev.candidate_identifiers;
DROP TABLE hs2_dev.candidates;
DROP FUNCTION hs2_dev.immutable_record();
DROP FUNCTION hs2_dev.snapshot_guard();
DROP FUNCTION hs2_dev.listing_guard();
DROP FUNCTION hs2_dev.inventory_cycle_guard();
DROP FUNCTION hs2_dev.identity_guard();
DROP TABLE hs2_dev.migration_receipts;
DROP SCHEMA hs2_dev;
