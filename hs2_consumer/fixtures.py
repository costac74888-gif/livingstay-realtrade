"""Synthetic public projections/quotes only; never a live catalog fallback."""
from flask import Flask, Response
from .api import create_blueprint

SDK = """
window.kakao={maps:{load:cb=>cb(),LatLng:function(a,b){this.lat=a;this.lng=b;},
Map:function(el,options){el.dataset.fixtureMap='true';el.textContent='격리 지도 SDK 인터페이스 검사';this.relayout=function(){};}}};
"""


def fixture_catalog(values):
    items = []
    for index, (kind, total) in enumerate((("lodging", 240000), ("non_lodging", 210000), ("lodging", None))):
        row = dict(public_id=f"00000000-0000-4000-8000-{index + 1:012d}",
                   stay_kind=kind, location_precision="withheld",
                   private_address="NEVER_PUBLIC_ADDRESS", lat=37.5, lng=127.1,
                   title="NEVER_PUBLIC_BUILDING_NAME", photo="NEVER_PUBLIC_PHOTO")
        if total is not None and values["check_in"]:
            row["quote"] = dict(check_in=values["check_in"], check_out=values["check_out"],
                               total_krw=total, complete=True, public_price_allowed=True,
                               source_version="synthetic-explicit-period-quote")
        items.append(row)
    return items


def create_fixture_app():
    app = Flask("hs2_consumer_synthetic")
    app.register_blueprint(create_blueprint(public_catalog=fixture_catalog,
        map_config=lambda: {"sdk_url": "/hs2/consumer-fixture-sdk.js"}))

    @app.get("/hs2/consumer-fixture-sdk.js")
    def sdk():
        return Response(SDK, mimetype="application/javascript")
    return app
