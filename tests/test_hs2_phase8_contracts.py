import unittest
from copy import deepcopy
from hs2_design.domain import ContractError
from hs2_supermap.contracts import parse, point, visible_stay, visible_legacy, slots
from hs2_supermap.native_adapters import NativePublicAdapters

P = dict(public_id="00000000-0000-4000-8000-000000000001",stay_kind="lodging")
A = dict(payload=dict(public_summary=True,rooms=0,area_m2="21.50",guests=2,
                     min_stay=1,options=["wifi","parking"],instant=True,discount=True,
                     title="NEVER_PUBLIC_NAME",photos=["NEVER_PUBLIC_PHOTO"],space_label="SECRET_UNIT"))
G = dict(lat=37.5,lng=127.1,precision="approx",aggregate_scope="dong",aggregate_count=5)


class PublicMapContracts(unittest.TestCase):
    def test_layers_independent_bounds_and_duplicate_rejected(self):
        self.assertEqual(parse({})["layers"],["stay"])
        self.assertEqual(parse(dict(layers="auction,stay,business,sale"))["layers"],["stay","sale","business","auction"])
        self.assertEqual(parse(dict(layers=""))["layers"],[])
        for values in (dict(layers="sale,sale"),dict(layers="unknown"),dict(bounds="nan,0,10,20"),dict(bounds="10,20,0,30")):
            with self.assertRaises(ContractError):parse(values)

    def test_existing_geometry_population_rounding_no_exact_fallback(self):
        self.assertEqual(point(G,limited=True)["radius_m"],500)
        for patch in (dict(aggregate_count=4),dict(lat=37.512345),dict(precision="exact"),dict(aggregate_scope="unknown")):
            self.assertIsNone(point({**G,**patch},limited=True))
        self.assertIsNone(point({**G,"aggregate_scope":"sgg","aggregate_count":9},limited=True))
        self.assertIsNotNone(point({**G,"aggregate_scope":"sgg","aggregate_count":10},limited=True))

    def test_price_requires_selected_period_no_missing_zero(self):
        v=parse(dict(check_in="2027-01-01",check_out="2027-01-03",min_total="200000"))
        self.assertIsNone(visible_stay(P,A,None,point(G,limited=True),v))
        self.assertIsNotNone(visible_stay(P,A,dict(total_krw=250000),point(G,limited=True),v))
        with self.assertRaises(ContractError):parse(dict(min_total="200000"))
        self.assertEqual(parse(dict(check_in="2027-01-01",check_out="2027-01-03",max_total="2000000000"))["max_total"],2000000000)
        with self.assertRaises(ContractError):parse(dict(check_in="2027-01-01",check_out="2027-01-03",max_total="730000000001"))

    def test_public_summary_filters_studio_area_guests_options_flags(self):
        v=parse(dict(rooms="0",min_area="21",guests="2",options="wifi,parking",instant="1",discount="1"))
        out=visible_stay(P,A,None,None,v)
        self.assertEqual(out["summary"]["rooms"],0)
        self.assertNotIn("SECRET_UNIT",str(out))
        self.assertNotIn("NEVER_PUBLIC",str(out))
        for patch in (dict(rooms="1"),dict(min_area="22"),dict(guests="3"),dict(options="washer")):
            self.assertIsNone(visible_stay(P,A,None,None,parse(patch)))

    def test_no_summary_consent_no_filtered_attribute_inference(self):
        application=dict(payload={**A["payload"],"public_summary":False})
        self.assertNotIn("summary",visible_stay(P,application,None,None,parse({})))
        self.assertIsNone(visible_stay(P,application,None,None,parse(dict(rooms="0"))))

    def test_legacy_limited_ignores_extra_identity_and_exact_metadata(self):
        row=dict(public=True,public_id="42",disclosure_scope="limited",public_point=G,
                 title="NEVER_PUBLIC_NAME",photos=["NEVER_PUBLIC_PHOTO"],lat=37.512345,
                 address="NEVER_PUBLIC_ADDRESS",master_building_id=999999)
        out=visible_legacy("sale",row)
        self.assertEqual(out["title"],"매매 매물")
        self.assertNotIn("NEVER_PUBLIC",str(out))
        self.assertNotIn("999999",str(out))
        with self.assertRaises(ContractError):visible_legacy("sale",{**row,"public":False})

    def test_overlapping_offsets_aggregate_ids_never_mutate_coords(self):
        rows=[dict(layer=layer,public_id=str(i),point=point(G,limited=True)) for layer in ("stay","sale","business","auction") for i in (42,43)]
        before=deepcopy(rows);markers=slots(rows)
        self.assertEqual(len(markers),4)
        self.assertEqual(len({tuple(m["offset"]) for m in markers}),4)
        self.assertTrue(all(m["count"]==2 for m in markers))
        self.assertEqual(rows,before)
        self.assertEqual({m["marker_shape"] for m in markers},{"price-bubble","diamond","hexagon","square"})

    def test_original_public_api_adapters_only_get_and_limited_q_never_private(self):
        calls=[]
        def source(path,params):
            calls.append((path,params))
            if path=="/api/auctions/map":
                return dict(ok=True,items=[dict(id=42,lat=37.5,lng=127.1,master_building_id=999999)],truncated=False)
            limited=params["disclosure_scope"]=="limited"
            return dict(ok=True,has_more=False,items=[dict(id=42,is_limited_listing=limited,
                building_name="강남",approx_lat=37.5,approx_lng=127.1,approx_location_label="동 중심 근처",
                lat=37.512345,lng=127.123456,transaction_target=params["transaction_target"])])
        adapter=NativePublicAdapters(get_public_json=source,default_bounds=[33,124,39,132])
        for callback in adapter.ports().values():callback(parse(dict(q="강남")))
        self.assertTrue(calls)
        self.assertTrue(all("q" not in args for path,args in calls if args.get("disclosure_scope")=="limited"))
        self.assertTrue(all(path in {"/api/listings","/api/auctions/map"} for path,args in calls))
        out=adapter.auctions(parse({}))
        self.assertNotIn("999999",str(out))

    def test_legacy_api_failure_not_empty_success_and_no_private_label_q(self):
        adapter=NativePublicAdapters(get_public_json=lambda *_:dict(ok=False),default_bounds=[33,124,39,132])
        with self.assertRaises(ContractError):adapter.listings("sale",parse({}))
        with self.assertRaises(ContractError):adapter.auctions(parse({}))
