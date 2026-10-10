import ast
import unittest
from pathlib import Path
from psycopg2.extras import RealDictCursor
from hs2_data.repository import connect_fixture
from hs2_design.domain import ContractError
from hs2_supermap.contracts import parse
from hs2_supermap.fixtures import create_fixture_app, WHO, APPROX
from hs2_supermap.api import create_blueprint
from flask import Flask


class SQLSuperMap(unittest.TestCase):
    def setUp(self):
        # Current owned cluster only; no live connection/import of app.py.
        with connect_fixture() as conn, conn.cursor() as c:
            c.execute("""TRUNCATE hs2_dev.calendar_versions,hs2_dev.registration_events,
                hs2_dev.registration_applications,hs2_dev.registration_photos,
                hs2_dev.price_snapshots,hs2_dev.tariff_versions,hs2_dev.classification_decisions,
                hs2_dev.stay_listings,hs2_dev.grant_units,hs2_dev.registration_grants,
                hs2_dev.inventory_members,hs2_dev.inventory_pools,hs2_dev.registered_buildings CASCADE""")
        self.app=create_fixture_app(False,populate=True)
        self.repo=self.app.fixture_supermap
        self.client=self.app.test_client()

    @classmethod
    def setUpClass(cls):
        from hs2_calendar.fixtures import create_fixture_app
        create_fixture_app()

    def test_actual_registered_attributes_and_selected_total_filter(self):
        results=self.repo.search(parse(dict(layers="stay,sale,business,auction")))
        self.assertEqual(results["counts"],dict(stay=2,sale=2,business=2,auction=2))
        self.assertEqual(len(results["markers"]),4)
        result=self.repo.search(parse(dict(check_in="2027-01-01",check_out="2027-01-15",
            rooms="0",min_area="21",guests="2",options="wifi,parking",instant="1",discount="1",
            min_total="600000",max_total="600000")))
        self.assertEqual(len(result["items"]),1)
        self.assertEqual(result["items"][0]["stay_kind"],"non_lodging")
        self.assertEqual(result["items"][0]["quote"]["total_krw"],600000)

    def test_empty_layers_and_independent_native_counts_no_statistics_write(self):
        none=self.repo.search(parse(dict(layers="")))
        self.assertEqual(none["items"],[])
        self.assertEqual(none["counts"],{})
        for layer in ("stay","sale","business","auction"):
            row=self.repo.search(parse(dict(layers=layer)))
            self.assertEqual(set(row["counts"]),{layer})
            self.assertFalse(row["native_statistics_changed"])
        with connect_fixture() as conn,conn.cursor() as c:
            c.execute("SELECT count(*) FROM hs2_fixture_legacy.master_buildings")
            self.assertEqual(c.fetchone()[0],0)

    def test_all_points_overlap_pixel_slots_not_coordinate_edits(self):
        out=self.repo.search(parse(dict(layers="stay,sale,business,auction")))
        self.assertTrue(all(m["point"]["lat"]==37.5 and m["point"]["lng"]==127.1 for m in out["markers"]))
        self.assertEqual(len({tuple(m["offset"]) for m in out["markers"]}),4)
        self.assertTrue(all(m["count"]==2 for m in out["markers"]))
        self.assertEqual(next(m for m in out["markers"] if m["layer"]=="auction")["marker_shape"],"square")

    def test_same_id_detail_layer_identity_and_off_never_direct_private_lookup(self):
        values=parse(dict(layers="stay,sale,business,auction"))
        sale=self.repo.detail("sale","42",values)["item"]
        auction=self.repo.detail("auction","42",values)["item"]
        self.assertEqual(sale["layer"],"sale")
        self.assertEqual(auction["layer"],"auction")
        with self.assertRaises(ContractError):self.repo.detail("sale","42",parse({}))
        with self.assertRaises(ContractError):self.repo.detail("auction","private",values)

    def test_inadequate_privacy_population_hidden_marker_keeps_safe_list(self):
        self.repo.public_geometry=lambda _: {**APPROX,"aggregate_count":1,"lat":37.512345}
        result=self.repo.search(parse({}))
        self.assertEqual(len(result["items"]),2)
        self.assertEqual(result["markers"],[])
        self.assertEqual(result["withheld_count"],2)
        self.assertTrue(all(r["location_precision"]=="withheld" for r in result["items"]))

    def test_public_api_strips_private_identity_photos_and_native_coords(self):
        out=self.client.get("/hs2/search/api/results?layers=stay,sale,business,auction")
        self.assertEqual(out.status_code,200)
        text=out.get_data(as_text=True)
        for secret in ("NEVER_PUBLIC","999999","37.512345","127.123456","candidate_id","context_id","user_id","reviewer_id","space_label"):
            self.assertNotIn(secret,text)
        for application in self.app.fixture_repo.list(WHO):
            self.assertNotIn(application["id"],text)
            self.assertNotIn(application["candidate_id"],text)

    def test_bounds_filter_and_public_location_lookup_not_private_name(self):
        result=self.repo.search(parse(dict(bounds="34,125,35,126")))
        self.assertEqual(result["items"],[])
        self.assertEqual(len(self.repo.search(parse(dict(q="강남")))["items"]),2)
        self.assertEqual(self.repo.search(parse(dict(q="NEVER_PUBLIC_NAME")))["items"],[])

    def test_withdrawal_and_during_geometry_read_publication_recheck(self):
        row=self.app.fixture_repo.list(WHO)[0]
        self.app.fixture_repo.change(WHO,row["id"],row["revision"],"withdraw")
        self.assertEqual(self.repo.search(parse({}))["counts"]["stay"],1)
        row=self.app.fixture_repo.list(WHO)[0]
        row=next(r for r in self.app.fixture_repo.list(WHO) if r["status"]=="approved")
        once=[]
        def geometry(key):
            if not once:
                self.app.fixture_repo.change(WHO,row["id"],row["revision"],"withdraw");once.append(True)
            return dict(APPROX)
        self.repo.public_geometry=geometry
        self.assertEqual(self.repo.search(parse({}))["items"],[])

    def test_revoked_context_and_price_missing_no_zero_or_native_layer_loss(self):
        self.app.fixture_approved.remove((101,WHO["context_id"]))
        out=self.repo.search(parse(dict(layers="stay,sale,business,auction")))
        self.assertEqual(out["counts"]["stay"],0)
        self.assertEqual(out["counts"]["auction"],2)
        self.app.fixture_approved.add((101,WHO["context_id"]))
        self.app.fixture_calendar.inventory_is_available=lambda *_:False
        out=self.repo.search(parse(dict(check_in="2027-01-01",check_out="2027-01-03")))
        self.assertEqual(out["items"],[])

    def test_original_privacy_sql_real_population_and_redactor_preserved(self):
        source=(Path(__file__).resolve().parents[1]/"app.py").read_text()
        names={"_limited_whole_listing_approx_location","_apply_limited_whole_listing_privacy"}
        nodes=[n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name in names]
        self.assertEqual(len(nodes),2)
        namespace={};exec(compile(ast.Module(body=nodes,type_ignores=[]),"actual-original-privacy","exec"),namespace)
        with connect_fixture() as conn,conn.cursor(cursor_factory=RealDictCursor) as c:
            c.execute("""CREATE TEMP TABLE master_buildings(sgg_text text,umd_nm text,lat double precision,lng double precision);
                INSERT INTO master_buildings SELECT '서울 강남','테스트동',37.51234+i*0.001,127.12345+i*0.001 FROM generate_series(1,4)i""")
            listing=dict(sgg_text="서울 강남",umd_nm="테스트동",transaction_target="whole")
            aggregate=namespace["_limited_whole_listing_approx_location"]
            self.assertIsNone(aggregate(c,listing))
            c.execute("INSERT INTO master_buildings VALUES('서울 강남','테스트동',37.518,127.129)")
            geo=aggregate(c,listing)
            self.assertEqual(geo["approx_location_label"],"동 중심 근처")
            self.assertEqual(geo["approx_lat"],round(geo["approx_lat"],3))
            raw={**listing,"building_id":999999,"lat":37.512345,"lng":127.123456,
                 "photo_url":"NEVER_PUBLIC_PHOTO","building_info_overrides":{"area_m2":999},
                 "verified_phone":"NEVER_PUBLIC_PHONE"}
            safe=namespace["_apply_limited_whole_listing_privacy"](raw,geo)
            for field in ("building_id","lat","lng","photo_url","building_info_overrides","verified_phone"):
                self.assertNotIn(field,safe)

    def test_native_source_failure_and_sdk_budget_errors_are_not_empty_success(self):
        self.repo.legacy_layers["sale"]=lambda _: dict(items=[],truncated="fake")
        with self.assertRaises(ContractError):self.repo.search(parse(dict(layers="sale")))
        app=Flask("budget-test")
        app.register_blueprint(create_blueprint(self.repo,map_config=lambda:dict(sdk_url="/hs2/supermap-fixture-sdk.js"),allow_request=lambda:False))
        self.assertEqual(app.test_client().get("/hs2/search/api/results").status_code,429)
        out=self.client.get("/hs2/search/api/results?layers=sale")
        self.assertNotEqual(out.status_code,200)

    def test_sdk_config_private_extras_never_serialized_and_malformed_url_denied(self):
        for url,expected in (("/hs2/supermap-fixture-sdk.js",200),("https://private.invalid/api?serviceKey=NEVER_PUBLIC",400)):
            app=Flask("sdk-"+str(expected))
            app.register_blueprint(create_blueprint(self.repo,map_config=lambda url=url:dict(sdk_url=url,REST_KEY="NEVER_PUBLIC_SECRET"),allow_request=lambda:True))
            response=app.test_client().get("/hs2/search/api/results")
            self.assertEqual(response.status_code,expected)
            self.assertNotIn("NEVER_PUBLIC",response.get_data(as_text=True))
