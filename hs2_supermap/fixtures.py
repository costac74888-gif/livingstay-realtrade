"""Actual owned PostgreSQL registration/pricing; synthetic native read adapters/SDK."""
from flask import Response
from hs2_calendar.fixtures import create_fixture_app as calendar_app
from hs2_consumer.api import create_blueprint as consumer_blueprint
from hs2_listings.review import review
from .repository import SuperMapRepository
from .api import create_blueprint

WHO = dict(user_id=101, context_id="operator:fixture:101", role="operator")
APPROX = dict(lat=37.5, lng=127.1, precision="approx", aggregate_scope="dong", aggregate_count=8)

SDK = """
window.kakao={maps:{
 load:cb=>cb(),LatLng:function(lat,lng){this.lat=lat;this.lng=lng;this.getLat=()=>lat;this.getLng=()=>lng;},
 Map:function(el,options){el.dataset.fixtureMap='true';el.style.position='relative';this.el=el;this.relayout=()=>{};
 this.getBounds=()=>({getSouthWest:()=>new kakao.maps.LatLng(33,124),getNorthEast:()=>new kakao.maps.LatLng(39,132)});},
 CustomOverlay:function(o){this.content=o.content;this.position=o.position;this.setMap=m=>{
 if(this.content.parentNode)this.content.remove();if(m){this.content.style.position='absolute';
 this.content.style.left='50%';this.content.style.top='50%';m.el.append(this.content);}
 };if(o.map)this.setMap(o.map);},Circle:function(o){this.setMap=()=>{};},
 event:{addListener:(map,event,cb)=>{map.el['fixture_'+event]=cb;},removeListener:()=>{}}
}};
"""


def native_source(layer):
    return lambda values: dict(items=[
        dict(public=True, public_id="42", disclosure_scope="limited", public_point=APPROX,
             title="NEVER_PUBLIC_BUILDING", address="NEVER_PUBLIC_ADDRESS", lat=37.512345,
             lng=127.123456, photo="NEVER_PUBLIC_PHOTO", master_building_id=999999),
        dict(public=True, public_id="43", disclosure_scope="public",
             public_title={"sale": "공개 매매", "business": "공개 영업권 양도", "auction": "공개 공매"}[layer],
             public_point=dict(lat=37.5,lng=127.1,precision="exact"))], truncated=False)


def create_fixture_app(initialize=True, populate=None):
    app = calendar_app(initialize, populate=populate)
    if populate is True or (populate is None and initialize):
        for row in app.fixture_repo.list(WHO):
            data = {**row["payload"], "public_summary": True, "options": ["wifi", "parking"],
                    "instant": True, "discount": True}
            row = app.fixture_repo.change(WHO, row["id"], row["revision"], "save", data)
            app.fixture_repo.change(WHO, row["id"], row["revision"], "submit")
            review(app.fixture_repo, row["id"], 700, row["revision"], "approve", "제한된 운영자 공개요약 동의 확인", rights=True, disclosure=True)
            command = dict(start="2026-10-11",end="2028-10-11",inclusive=True,
                action="nightly" if data["stay_kind"]=="lodging" else "periods",
                values={str(i):100000 for i in range(7)} if data["stay_kind"]=="lodging" else dict(weekly=300000,monthly=1000000))
            app.fixture_calendar.update(WHO, row["id"], 0, row["revision"], command)
    app.fixture_supermap = SuperMapRepository(app.fixture_calendar,
        public_geometry=lambda _: dict(APPROX), public_location_match=lambda _,q: q in {"서울", "강남", "숙박"},
        legacy_layers={k:native_source(k) for k in ("sale","business","auction")})
    app.register_blueprint(consumer_blueprint(public_catalog=app.fixture_calendar.consumer_rows,
        map_config=lambda:dict(sdk_url="/hs2/consumer-fixture-sdk.js")))
    app.register_blueprint(create_blueprint(app.fixture_supermap,
        map_config=lambda:dict(sdk_url="/hs2/supermap-fixture-sdk.js"), allow_request=lambda:True))

    @app.get("/hs2/supermap-fixture-sdk.js")
    @app.get("/hs2/consumer-fixture-sdk.js")
    def sdk():
        return Response(SDK,mimetype="application/javascript")
    return app
