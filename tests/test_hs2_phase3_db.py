"""Actual Phase 2 PostgreSQL reference writes, never a live DB/DSN."""
from copy import deepcopy
import unittest
from hs2_data.repository import connect_fixture,migrate
from hs2_registration.fixtures import address_response,title_response,coordinate_response,ROAD
from hs2_registration.providers import ReadPorts
from hs2_registration.service import RegistrationService
from hs2_registration.store import PostgresReferenceStore


class PostgreSQLRegistrationContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with connect_fixture() as conn,conn.cursor() as c:
            c.execute("""CREATE SCHEMA hs2_fixture_legacy;
              CREATE TABLE hs2_fixture_legacy.master_buildings(id bigserial PRIMARY KEY,identity_key text NOT NULL,
                  lodging_type text NOT NULL,lat numeric,lng numeric);
              CREATE TABLE hs2_fixture_legacy.users(id bigserial PRIMARY KEY,active boolean NOT NULL);
              INSERT INTO hs2_fixture_legacy.master_buildings VALUES(42,'registry:one','legacy-lodging',37.5,127);
              SELECT setval('hs2_fixture_legacy.master_buildings_id_seq',9000,true);
              INSERT INTO hs2_fixture_legacy.users VALUES(101,true);
              CREATE ROLE hs2_fixture_writer NOLOGIN;CREATE ROLE hs2_fixture_public NOLOGIN;""")
            migrate(conn)
            c.execute("""CREATE ROLE hs2_fixture_registrar NOLOGIN;
             GRANT USAGE ON SCHEMA hs2_dev,hs2_fixture_legacy TO hs2_fixture_registrar;
             GRANT SELECT ON hs2_dev.candidates,hs2_dev.master_links,hs2_fixture_legacy.master_buildings TO hs2_fixture_registrar;
             GRANT INSERT ON hs2_dev.candidates,hs2_dev.master_links TO hs2_fixture_registrar;""")

    def setUp(self):
        self.conn=connect_fixture();self.store=PostgresReferenceStore(self.conn)
        self.before=self.legacy_image()
        self.building={"identity_key":"registry:one","road_address":ROAD,"building_use":"상가","evidence_version":"hub:fixture"}
        self.coords={"lat":37.5,"lng":127.0,"evidence_version":"kakao:fixture"}

    def tearDown(self):
        self.conn.rollback();self.assertEqual(self.before,self.legacy_image());self.conn.close()

    def sql(self,q,args=()):
        with self.conn.cursor() as c:c.execute(q,args);return c.fetchall() if c.description else []

    def legacy_image(self):
        return (self.sql("SELECT * FROM hs2_fixture_legacy.master_buildings ORDER BY id"),
                self.sql("SELECT last_value,is_called FROM hs2_fixture_legacy.master_buildings_id_seq"),
                self.sql("SELECT * FROM hs2_fixture_legacy.users"))

    def test_actual_service_to_postgres_existing_link(self):
        service=RegistrationService(ReadPorts(lambda _:address_response(),lambda _:title_response("상가"),
            lambda _:coordinate_response(),self.store.legacy),self.store)
        s=service.start(101,"검증로");k=s["workflow_id"]
        s=service.select_address(101,k,s["addresses"][0]["address_key"])
        s=service.select_building(101,k,s["buildings"][0]["building_key"])
        self.assertEqual(service.coordinates(101,k)["status"],"READY_FOR_REFERENCE")
        self.assertEqual(service.confirm(101,k)["status"],"REFERENCE_CONFIRMED")
        self.assertEqual(self.sql("SELECT master_id FROM hs2_dev.master_links"),[(42,)])
        self.assertEqual(self.legacy_image(),self.before)

    def test_general_building_uses_separate_reference_no_master_insert(self):
        b={**self.building,"identity_key":"registry:warehouse","building_use":"창고"}
        ref=self.store.save(b,self.coords,None)
        self.assertEqual(self.sql("SELECT count(*) FROM hs2_dev.master_links"),[(0,)])
        self.assertEqual(self.sql("SELECT building_use FROM hs2_dev.candidates WHERE id=%s",(str(ref),)),[("창고",)])
        self.assertEqual(self.legacy_image(),self.before)

    def test_all_uses_persist_without_lodging_filter(self):
        for i,use in enumerate(("아파트","원룸","숙박","캠핑","농어촌민박","상가","창고","기타","복합")):
            self.store.save({**self.building,"identity_key":f"registry:use:{i}","building_use":use},self.coords,None)
        self.assertEqual(self.sql("SELECT count(*) FROM hs2_dev.candidates"),[(9,)])
        self.assertEqual(self.legacy_image(),self.before)

    def test_duplicate_confirmation_returns_same_reference(self):
        a=self.store.save(self.building,self.coords,42);b=self.store.save(self.building,self.coords,42)
        self.assertEqual(a,b);self.assertEqual(self.sql("SELECT count(*) FROM hs2_dev.candidates"),[(1,)])
        self.assertEqual(self.sql("SELECT count(*) FROM hs2_dev.master_links"),[(1,)])

    def test_identity_conflict_does_not_overwrite_existing_reference(self):
        self.store.save(self.building,self.coords,42)
        for change in ({"road_address":"다른 주소"},{"building_use":"창고"}):
            with self.assertRaises(Exception):self.store.save({**self.building,**change},self.coords,42)
        self.assertEqual(self.sql("SELECT road_address,building_use FROM hs2_dev.candidates"),[(ROAD,"상가")])

    def test_coordinate_conflict_is_not_silently_updated(self):
        self.store.save(self.building,self.coords,42)
        with self.assertRaises(Exception):self.store.save(self.building,{**self.coords,"lat":38},42)
        self.assertEqual(float(self.sql("SELECT lat FROM hs2_dev.candidates")[0][0]),37.5)

    def test_bad_master_link_rolls_back_entire_candidate_insert(self):
        with self.assertRaises(Exception):self.store.save(self.building,self.coords,999)
        self.assertEqual(self.sql("SELECT count(*) FROM hs2_dev.candidates"),[(0,)])
        self.assertEqual(self.sql("SELECT count(*) FROM hs2_dev.master_links"),[(0,)])
        self.assertEqual(self.legacy_image(),self.before)

    def test_wrong_physical_identity_never_links_by_existing_id(self):
        with self.assertRaises(Exception):self.store.save({**self.building,"identity_key":"registry:other"},self.coords,42)
        self.assertEqual(self.sql("SELECT count(*) FROM hs2_dev.candidates"),[(0,)])

    def test_ambiguous_legacy_source_cannot_write_link(self):
        self.sql("INSERT INTO hs2_fixture_legacy.master_buildings VALUES(43,'registry:one','legacy-other',NULL,NULL)")
        with self.assertRaises(Exception):self.store.save(self.building,self.coords,42)
        self.assertEqual(self.sql("SELECT count(*) FROM hs2_dev.candidates"),[(0,)])

    def test_reference_save_never_grants_rights_creates_listing_or_registration(self):
        self.store.save(self.building,self.coords,42)
        for table in ("registered_buildings","registration_grants","grant_units","stay_listings","inventory_pools","price_snapshots"):
            self.assertEqual(self.sql("SELECT count(*) FROM hs2_dev."+table),[(0,)])

    def test_fixture_registrar_can_save_but_cannot_write_legacy(self):
        self.sql("SET LOCAL ROLE hs2_fixture_registrar")
        self.store.save(self.building,self.coords,42)
        for statement in ("UPDATE hs2_fixture_legacy.master_buildings SET lodging_type='new'",
                          "DELETE FROM hs2_fixture_legacy.master_buildings",
                          "SELECT nextval('hs2_fixture_legacy.master_buildings_id_seq')",
                          "UPDATE hs2_dev.candidates SET road_address='new'"):
            self.sql("SAVEPOINT deny")
            with self.assertRaises(Exception):self.sql(statement)
            self.sql("ROLLBACK TO SAVEPOINT deny")
        self.sql("RESET ROLE");self.assertEqual(self.legacy_image(),self.before)

    def test_limited_public_cannot_join_new_candidate_location(self):
        self.store.save(self.building,self.coords,42);self.sql("SET LOCAL ROLE hs2_fixture_public")
        self.sql("SAVEPOINT deny")
        with self.assertRaises(Exception):self.sql("SELECT lat,lng FROM hs2_dev.candidates")
        self.sql("ROLLBACK TO SAVEPOINT deny")
        self.assertEqual(self.sql("SELECT * FROM hs2_dev.limited_stay_listings"),[])

    def test_migration_recovery_removes_only_fixture_reference_layer(self):
        self.store.save(self.building,self.coords,42)
        self.assertEqual(migrate(self.conn,"down"),"REVERTED")
        self.assertEqual(self.legacy_image(),self.before)
        self.assertEqual(migrate(self.conn),"APPLIED")
        self.assertEqual(self.sql("SELECT count(*) FROM hs2_dev.candidates"),[(0,)])
