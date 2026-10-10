"""Actual PostgreSQL constraints/permissions/rollback on synthetic local data ONLY."""
import contextlib
from datetime import date, timedelta
import json
from pathlib import Path
import socket
import subprocess
import unittest
from uuid import uuid4

import psycopg2
from hs2_data.repository import (
    FixtureRepository, MIGRATIONS, connect_fixture, migrate, save_fixture_snapshot,
)
from hs2_design.domain import Classification, ContractError, StayKind
from hs2_design.pricing import Terms, lodging_date_snapshot


def uid(n):
    return f"00000000-0000-4000-8000-{n:012d}"


class PostgreSQLDataContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with connect_fixture() as conn, conn.cursor() as cur:
            cur.execute("""
                CREATE SCHEMA hs2_fixture_legacy;
                CREATE TABLE hs2_fixture_legacy.master_buildings(
                  id bigserial PRIMARY KEY, identity_key text NOT NULL, lodging_type text NOT NULL,
                  lat numeric, lng numeric);
                CREATE TABLE hs2_fixture_legacy.users(id bigserial PRIMARY KEY, active boolean NOT NULL);
                INSERT INTO hs2_fixture_legacy.master_buildings VALUES(42,'registry:one','legacy-lodging',37.5,127.0);
                SELECT setval('hs2_fixture_legacy.master_buildings_id_seq',9000,true);
                INSERT INTO hs2_fixture_legacy.users VALUES(101,true),(102,true),(103,false);
                CREATE ROLE hs2_fixture_writer NOLOGIN;
                CREATE ROLE hs2_fixture_public NOLOGIN;
                GRANT USAGE ON SCHEMA hs2_fixture_legacy TO hs2_fixture_writer;
                GRANT SELECT ON ALL TABLES IN SCHEMA hs2_fixture_legacy TO hs2_fixture_writer;
            """)
            migrate(conn)

    def setUp(self):
        self.conn = connect_fixture()
        self.before = self.legacy_image()

    def tearDown(self):
        self.conn.rollback()
        self.assertEqual(self.legacy_image(), self.before)
        self.conn.close()

    def sql(self, query, args=(), fetch=False):
        with self.conn.cursor() as cur:
            cur.execute(query, args)
            return cur.fetchall() if fetch else None

    def legacy_image(self):
        return (self.sql("SELECT * FROM hs2_fixture_legacy.master_buildings ORDER BY id", fetch=True),
                self.sql("SELECT last_value,is_called FROM hs2_fixture_legacy.master_buildings_id_seq", fetch=True),
                self.sql("SELECT * FROM hs2_fixture_legacy.users ORDER BY id", fetch=True))

    @contextlib.contextmanager
    def rejected(self, exception=psycopg2.Error):
        self.sql("SAVEPOINT rejection")
        try:
            with self.assertRaises(exception):
                yield
        finally:
            self.sql("ROLLBACK TO SAVEPOINT rejection")
            self.sql("RELEASE SAVEPOINT rejection")

    def candidate(self, n=1, identity="registry:one", confirmed=True, use="주택"):
        self.sql("""INSERT INTO hs2_dev.candidates
            (id,identity_key,identity_confirmed,building_use,road_address,evidence_version)
            VALUES(%s,%s,%s,%s,'fixture address','fixture:v1')""", (uid(n), identity, confirmed, use))
        return uid(n)

    def graph(self):
        self.candidate()
        self.sql("INSERT INTO hs2_dev.registered_buildings VALUES(%s,%s)", (uid(2), uid(1)))
        self.sql("INSERT INTO hs2_dev.inventory_pools VALUES(%s,%s,'unit:one')", (uid(3), uid(2)))
        self.sql("INSERT INTO hs2_dev.registration_grants VALUES(%s,%s,101,'owner','fixture-rights',true)", (uid(4), uid(2)))
        self.sql("INSERT INTO hs2_dev.grant_units VALUES(%s,%s,%s)", (uid(4), uid(3), uid(2)))
        return FixtureRepository(self.conn, 101)

    def draft(self, repo, n=5, pool=3, grant=4):
        repo.create_draft(listing_id=uid(n), public_id=uid(n+100), building_id=uid(2),
                          pool_id=uid(pool), grant_id=uid(grant))
        return uid(n)

    def decision(self, listing=5, n=6, kind="lodging", version="fixture:v1"):
        self.sql("INSERT INTO hs2_dev.classification_decisions VALUES(%s,%s,%s,'fixture-permit',%s,'주택','Airbnb')",
                 (uid(n), uid(listing), kind, version))
        return uid(n)

    def writer(self):
        self.sql("SET LOCAL ROLE hs2_fixture_writer")

    def snapshot(self):
        repo=self.graph()
        self.draft(repo)
        self.decision()
        self.sql("INSERT INTO hs2_dev.tariff_versions VALUES(%s,%s,'rates:v1','{\"fixture\":true}')", (uid(7), uid(5)))
        start=date(2026,10,10)
        return lodging_date_snapshot(
            Classification(uid(5), StayKind.LODGING, "fixture-permit", "fixture:v1"),
            start, start+timedelta(days=1), {start:100000},
            tariff_version="rates:v1", terms=Terms("fixture:terms:v1","Asia/Seoul",True), adjustments=())

    def test_real_postgres_and_original_network_process_guard(self):
        self.assertIn("PostgreSQL", self.sql("SELECT version()", fetch=True)[0][0])
        self.assertEqual(self.sql("SHOW listen_addresses", fetch=True)[0][0],"")
        for call in (lambda:psycopg2.connect("dbname=production"),
                     lambda:psycopg2.connect(host="remote",dbname="postgres"),
                     lambda:socket.create_connection(("example.com",443)),
                     lambda:subprocess.Popen(["psql"])):
            with self.assertRaises(RuntimeError): call()

    def test_all_uses_can_be_candidates_without_lodging_master(self):
        for n,use in enumerate(("원룸","아파트","상가","창고","캠핑","기타","복합"),10):
            self.candidate(n, None, False, use)
        self.assertEqual(self.sql("SELECT count(*) FROM hs2_dev.candidates",fetch=True)[0][0],7)
        self.assertEqual(self.sql("SELECT count(*) FROM hs2_dev.master_links",fetch=True)[0][0],0)

    def test_non_lodging_registration_needs_no_master_link(self):
        self.graph()
        self.assertEqual(self.sql("SELECT count(*) FROM hs2_dev.registered_buildings",fetch=True)[0][0],1)
        self.assertEqual(self.sql("SELECT count(*) FROM hs2_dev.master_links",fetch=True)[0][0],0)

    def test_legacy_ids_classification_coordinates_sequence_never_rewritten(self):
        self.graph()
        self.sql("INSERT INTO hs2_dev.master_links VALUES(%s,42,'registry:one','fixture:v1')",(uid(1),))
        self.assertEqual(self.legacy_image(), self.before)
        self.writer()
        for sql in ("UPDATE hs2_fixture_legacy.master_buildings SET lodging_type='general'",
                    "DELETE FROM hs2_fixture_legacy.master_buildings",
                    "INSERT INTO hs2_fixture_legacy.master_buildings(identity_key,lodging_type) VALUES('new','hotel')",
                    "SELECT nextval('hs2_fixture_legacy.master_buildings_id_seq')"):
            with self.rejected(): self.sql(sql)

    def test_master_id_exists_but_identity_mismatch_is_rejected(self):
        self.candidate(identity="registry:other")
        with self.rejected():
            self.sql("INSERT INTO hs2_dev.master_links VALUES(%s,42,'registry:other','fixture:v1')",(uid(1),))

    def test_ambiguous_duplicate_legacy_identity_is_rejected(self):
        self.candidate()
        self.sql("INSERT INTO hs2_fixture_legacy.master_buildings VALUES(43,'registry:one','legacy-other',NULL,NULL)")
        with self.rejected():
            self.sql("INSERT INTO hs2_dev.master_links VALUES(%s,42,'registry:one','fixture:v1')",(uid(1),))

    def test_missing_legacy_or_unconfirmed_candidate_is_rejected(self):
        self.candidate(confirmed=False)
        with self.rejected():
            self.sql("INSERT INTO hs2_dev.master_links VALUES(%s,42,'registry:one','fixture:v1')",(uid(1),))
        with self.rejected():
            self.sql("INSERT INTO hs2_dev.master_links VALUES(%s,999,'registry:one','fixture:v1')",(uid(1),))

    def test_candidate_identity_unique_but_same_address_distinct_buildings_allowed(self):
        self.candidate()
        with self.rejected(): self.candidate(10)
        self.candidate(10,"registry:two")

    def test_source_identifiers_have_verified_uniqueness(self):
        self.candidate();self.candidate(10,"registry:two")
        self.sql("INSERT INTO hs2_dev.candidate_identifiers VALUES(%s,%s,'registry','external:1','v1',true)",(uid(11),uid(1)))
        with self.rejected():
            self.sql("INSERT INTO hs2_dev.candidate_identifiers VALUES(%s,%s,'registry','external:1','v1',true)",(uid(12),uid(10)))

    def test_registration_requires_confirmed_identity_and_one_physical_candidate(self):
        self.candidate(confirmed=False)
        with self.rejected(): self.sql("INSERT INTO hs2_dev.registered_buildings VALUES(%s,%s)",(uid(2),uid(1)))
        self.sql("UPDATE hs2_dev.candidates SET identity_confirmed=true")
        self.sql("INSERT INTO hs2_dev.registered_buildings VALUES(%s,%s)",(uid(2),uid(1)))
        with self.rejected(): self.sql("INSERT INTO hs2_dev.registered_buildings VALUES(%s,%s)",(uid(10),uid(1)))

    def test_referenced_identity_is_immutable(self):
        self.graph()
        with self.rejected(): self.sql("UPDATE hs2_dev.candidates SET identity_key='wrong'")
        with self.rejected(): self.sql("UPDATE hs2_dev.candidates SET identity_confirmed=false")
        self.candidate(10,"registry:two")
        with self.rejected():self.sql("UPDATE hs2_dev.registered_buildings SET candidate_id=%s",(uid(10),))

    def test_dangling_and_deleting_referenced_records_are_rejected(self):
        self.graph()
        with self.rejected(): self.sql("DELETE FROM hs2_dev.candidates")
        with self.rejected(): self.sql("DELETE FROM hs2_dev.registered_buildings")
        with self.rejected(): self.sql("INSERT INTO hs2_dev.registered_buildings VALUES(%s,%s)",(uid(11),uid(999)))

    def test_same_pool_multiple_listings_not_independent_stock(self):
        repo=self.graph();self.writer();self.draft(repo);self.draft(repo,10)
        self.assertEqual(self.sql("SELECT count(DISTINCT pool_id),count(*) FROM hs2_dev.stay_listings",fetch=True)[0],(1,2))

    def test_inventory_unique_and_cannot_cross_buildings(self):
        self.graph();self.candidate(10,"registry:two")
        self.sql("INSERT INTO hs2_dev.registered_buildings VALUES(%s,%s)",(uid(11),uid(10)))
        with self.rejected(): self.sql("INSERT INTO hs2_dev.inventory_pools VALUES(%s,%s,'unit:one')",(uid(12),uid(2)))
        self.sql("INSERT INTO hs2_dev.inventory_pools VALUES(%s,%s,'unit:two')",(uid(12),uid(11)))
        with self.rejected(): self.sql("INSERT INTO hs2_dev.inventory_members VALUES(%s,%s,%s)",(uid(2),uid(3),uid(12)))

    def test_inventory_group_cycle_is_rejected(self):
        self.graph()
        self.sql("INSERT INTO hs2_dev.inventory_pools VALUES(%s,%s,'unit:two')",(uid(12),uid(2)))
        self.sql("INSERT INTO hs2_dev.inventory_members VALUES(%s,%s,%s)",(uid(2),uid(3),uid(12)))
        with self.rejected(): self.sql("INSERT INTO hs2_dev.inventory_members VALUES(%s,%s,%s)",(uid(2),uid(12),uid(3)))
        with self.rejected(): self.sql("UPDATE hs2_dev.inventory_members SET parent_id=%s,child_id=%s",(uid(12),uid(3)))

    def test_grant_does_not_implicitly_authorize_other_units(self):
        repo=self.graph()
        self.sql("INSERT INTO hs2_dev.inventory_pools VALUES(%s,%s,'unit:two')",(uid(12),uid(2)))
        self.writer()
        with self.rejected(): self.draft(repo,pool=12)

    def test_other_user_or_other_building_grant_is_rejected(self):
        self.graph();self.writer()
        repo=FixtureRepository(self.conn,102)
        with self.rejected(): self.draft(repo)

    def test_unapproved_revoked_or_inactive_rights_rejected(self):
        repo=self.graph()
        self.sql("UPDATE hs2_dev.registration_grants SET approved=false")
        self.writer()
        with self.rejected(): self.draft(repo)
        self.sql("RESET ROLE")
        self.sql("UPDATE hs2_dev.registration_grants SET approved=true")
        self.sql("UPDATE hs2_fixture_legacy.users SET active=false WHERE id=101")
        self.writer()
        with self.rejected(): self.draft(repo)

    def test_writer_cannot_self_approve_or_change_evidence(self):
        self.graph();self.writer()
        with self.rejected(): self.sql("UPDATE hs2_dev.registration_grants SET approved=true")
        with self.rejected(): self.sql("INSERT INTO hs2_dev.classification_decisions VALUES(%s,%s,'lodging','fake','v1','','')",(uid(6),uid(5)))

    def test_unresolved_classification_cannot_publish(self):
        repo=self.graph();self.draft(repo);self.decision(kind="unresolved");self.writer()
        with self.rejected(): repo.change_status(uid(5),"published",uid(6))

    def test_classification_subject_and_evidence_are_enforced(self):
        repo=self.graph();self.draft(repo);self.draft(repo,10);self.decision(listing=10)
        with self.rejected(): repo.change_status(uid(5),"published",uid(6))
        with self.rejected():
            self.sql("INSERT INTO hs2_dev.classification_decisions VALUES(%s,%s,'lodging','','v1','주택','Airbnb')",(uid(7),uid(5)))

    def test_limited_public_role_sees_allowlist_only_not_location_joins(self):
        repo=self.graph();self.draft(repo);self.decision();repo.change_status(uid(5),"published",uid(6))
        self.sql("SET LOCAL ROLE hs2_fixture_public")
        rows=repo.limited_listings()
        self.assertEqual(rows,[dict(public_id=uid(105),stay_kind="lodging",location_precision="withheld")])
        for table in ("candidates","master_links","stay_listings","classification_decisions"):
            with self.rejected(): self.sql("SELECT * FROM hs2_dev."+table)
        with self.rejected(): self.sql("SELECT * FROM hs2_fixture_legacy.master_buildings")

    def test_full_disclosure_and_private_public_id_are_rejected(self):
        repo=self.graph();self.draft(repo)
        with self.rejected(): self.sql("UPDATE hs2_dev.stay_listings SET disclosure_scope='full'")
        with self.rejected():
            repo.create_draft(listing_id=uid(10), public_id=uid(1), building_id=uid(2),pool_id=uid(3),grant_id=uid(4))

    def test_other_user_cannot_edit_or_transfer_listing(self):
        repo=self.graph();self.draft(repo);self.writer()
        other=FixtureRepository(self.conn,102)
        with self.assertRaises(ContractError): other.change_status(uid(5),"withdrawn")
        with self.rejected(): self.sql("UPDATE hs2_dev.stay_listings SET creator_user_id=102")

    def test_withdrawal_preserves_history_and_is_terminal(self):
        repo=self.graph();self.draft(repo);self.decision();self.writer()
        repo.change_status(uid(5),"withdrawn")
        with self.rejected(): repo.change_status(uid(5),"published",uid(6))
        self.assertEqual(self.sql("SELECT count(*) FROM hs2_dev.stay_listings",fetch=True)[0][0],1)
        self.assertEqual(self.sql("SELECT count(*) FROM hs2_dev.classification_decisions",fetch=True)[0][0],1)

    def test_price_snapshot_persists_and_is_immutable_without_real_booking(self):
        snapshot=self.snapshot()
        save_fixture_snapshot(self.conn,uid(8),snapshot)
        for table in ("price_snapshots","tariff_versions","classification_decisions"):
            with self.rejected(): self.sql("DELETE FROM hs2_dev."+table)
            with self.rejected(): self.sql("UPDATE hs2_dev."+table+" SET id=id")
        self.sql("INSERT INTO hs2_dev.tariff_versions VALUES(%s,%s,'rates:v2','{\"price\":999000}')",(uid(9),uid(5)))
        self.assertEqual(self.sql("SELECT total_krw,tariff_version FROM hs2_dev.price_snapshots",fetch=True)[0],(100000,"rates:v1"))

    def test_snapshot_wrong_total_gap_or_evidence_is_rejected(self):
        snapshot=self.snapshot();save_fixture_snapshot(self.conn,uid(8),snapshot)
        payload=self.sql("SELECT payload FROM hs2_dev.price_snapshots",fetch=True)[0][0]
        for change in ("total","lines","evidence","null"):
            bad=json.loads(json.dumps(payload))
            if change=="total":bad["total_krw"]=999999
            elif change=="lines":bad["lines"]=[]
            elif change=="evidence":bad["classification_evidence"]="forged"
            else:bad["total_krw"]=None
            with self.rejected():
                self.sql("""INSERT INTO hs2_dev.price_snapshots
                    SELECT %s,listing_id,check_in,check_out,kind,currency,tariff_version,
                           terms_version,classification_evidence,classification_version,total_krw,%s::jsonb
                    FROM hs2_dev.price_snapshots WHERE id=%s""",(str(uuid4()),json.dumps(bad),uid(8)))

    def test_migration_is_idempotent_and_wrong_receipt_is_blocked(self):
        self.assertEqual(migrate(self.conn),"ALREADY_APPLIED")
        self.sql("UPDATE hs2_dev.migration_receipts SET sha256='wrong'")
        with self.assertRaises(ContractError): migrate(self.conn)

    def test_down_and_reapply_preserve_legacy_and_sequence(self):
        self.graph()
        self.assertEqual(migrate(self.conn,"down"),"REVERTED")
        self.assertEqual(self.legacy_image(),self.before)
        self.assertEqual(migrate(self.conn,"down"),"ALREADY_REVERTED")
        self.assertEqual(migrate(self.conn),"APPLIED")
        self.assertEqual(self.legacy_image(),self.before)

    def test_unexpected_objects_stop_rollback_without_cascade(self):
        self.sql("CREATE TABLE hs2_dev.unreviewed(id integer)")
        with self.rejected(): migrate(self.conn,"down")
        self.assertIsNotNone(self.sql("SELECT to_regclass('hs2_dev.candidates')",fetch=True)[0][0])

    def test_failed_migration_rolls_back_atomically(self):
        migrate(self.conn,"down")
        with self.rejected():
            self.sql("SET LOCAL hs2.fixture_cluster='phase2-isolated'")
            self.sql((MIGRATIONS/"001_up.sql").read_text()+";SELECT 1/0")
        self.assertIsNone(self.sql("SELECT to_regnamespace('hs2_dev')",fetch=True)[0][0])
        migrate(self.conn)

    def test_sql_migration_requires_explicit_fixture_marker(self):
        migrate(self.conn,"down")
        self.sql("SET LOCAL hs2.fixture_cluster='not-approved'")
        with self.rejected(): self.sql((MIGRATIONS/"001_up.sql").read_text())
        self.assertIsNone(self.sql("SELECT to_regnamespace('hs2_dev')",fetch=True)[0][0])
        migrate(self.conn)


if __name__ == "__main__":
    unittest.main()
