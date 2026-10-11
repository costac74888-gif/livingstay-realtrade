"""Synthetic Seongsu inventory. May only be installed in the owned Preview."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import os

from hs2_listings.fixtures import CANDIDATE, PNG
from hs2_listings.review import review
from hs2_supermap.fixtures import WHO

NAMES = [
    "서울숲 코지 스튜디오", "성수 주·월 레지던스", "연무장 블루 스테이",
    "뚝섬 미니 로프트", "성수 패밀리 하우스", "서울숲 워크룸",
    "성수 브릭 스테이", "연무장 테라스룸", "뚝섬 선라이트",
    "성수 넓은 투룸", "서울숲 슬로우 스테이", "성수 워크앤리빙",
    "연무장 트윈 스테이", "뚝섬 한달살이",
]
DISCLAIMER = "테스트용 가상 매물 · 실재 매물/영업신고/법적 운영 가능성 확인 아님"


def require_owned(app):
    from hs2_data.repository import connect_fixture, require_fixture
    if os.environ.get("HS2_HARNESS_GUARD") != "1" or not hasattr(app, "fixture_repo"):
        raise RuntimeError("Synthetic owned Preview required")
    with connect_fixture() as conn:
        require_fixture(conn)


def seed_seongsu(app):
    require_owned(app)
    today = datetime.now(ZoneInfo("Asia/Seoul")).date()
    app.fixture_calendar.business_date = lambda: today
    start, end = today + timedelta(days=1), today + timedelta(days=540)
    rows = app.fixture_repo.list(WHO)
    if len(rows) != 2:
        raise RuntimeError("Fresh two-row Preview foundation required")
    order = [row["id"] for row in sorted(rows, key=lambda r: r["payload"]["stay_kind"] != "lodging")]
    # Existing fully tested foundations are retained; add 12 real fixture
    # registrations using the same review/calendar/booking repositories.
    photo = app.fixture_repo.upload(WHO, PNG, "image/png")["id"]
    for i in range(2, len(NAMES)):
        kind = "lodging" if i % 2 == 0 else "non_lodging"
        values = dict(
            title=f"[가상] 성수 {NAMES[i]}", space_label=f"가상 공간 {i+1:02}",
            stay_kind=kind, rooms=1 + i % 3, area_m2=str(22 + i * 4),
            guests=2 + i % 5, nightly=(178000 if i == 2 else 0 if i == 12 else
                                     70000 + i * 9000) if kind == "lodging" else None,
            weekly=260000 + i * 30000 if kind == "non_lodging" and i != 13 else None,
            monthly=900000 + i * 110000 if kind == "non_lodging" and i != 3 else None,
            min_stay=1 if kind == "lodging" else 7, photos=[photo],
            options=["wifi"] + (["kitchen", "washer"] if i % 3 else ["parking"]),
            instant=i % 2 == 0, discount=i % 4 == 0,
            responsibility=True, public_summary=True,
        )
        row = app.fixture_repo.create(WHO, CANDIDATE, values)
        order.append(row["id"])
        row = app.fixture_repo.change(WHO, row["id"], row["revision"], "submit")
        review(app.fixture_repo, row["id"], 700, row["revision"], "approve",
               "Owned 가상 매물만 승인; 실제 권한/영업허가 검증 아님",
               rights=True, disclosure=True)
    rows = app.fixture_repo.list(WHO)
    # Preserve the first two foundations, then stable creation order for labels.
    rows.sort(key=lambda row: order.index(row["id"]))
    catalog = {}
    for i, row in enumerate(rows):
        p = row["payload"]
        state = app.fixture_calendar.read(WHO, row["id"])
        rates = ({str(d): p["nightly"] + (20000 if d >= 4 else 0) for d in range(7)}
                 if p["stay_kind"] == "lodging"
                 else dict(weekly=p["weekly"], monthly=p["monthly"]))
        version = app.fixture_calendar.update(WHO, row["id"], state["version"],
            state["source_revision"], dict(start=start.isoformat(), end=end.isoformat(),
                inclusive=True, action=("open" if p["nightly"] == 0 else "nightly")
                    if p["stay_kind"] == "lodging" else "periods",
                # The frozen engine requires positive override/quote prices.
                # Publish the legitimate zero BASE, never fabricate a zero quote.
                values={} if p["stay_kind"] == "lodging" and p["nightly"] == 0 else rates))
        blocked = []
        if i % 3 == 0:
            closed_start, closed_end = start + timedelta(days=8), start + timedelta(days=11)
            state = app.fixture_calendar.read(WHO, row["id"])
            app.fixture_calendar.update(WHO, row["id"], state["version"],
                state["source_revision"], dict(start=closed_start.isoformat(),
                    end=closed_end.isoformat(), action="close", values={}, inclusive=True))
            blocked = [(closed_start + timedelta(days=d)).isoformat() for d in range(3)]
        public = row["public_id"]
        catalog[public] = dict(
            synthetic=True, name=f"[가상] {NAMES[i]}", disclaimer=DISCLAIMER,
            description=f"성수동 체험용 가상 공간 {i+1:02}. {p['area_m2']}㎡, 최대 {p['guests']}명. "
                        "실제 주소·소유자·연락처와 무관한 테스트 데이터입니다. "
                        "요금은 임의 테스트 요금이며 숙박/임대의 법적 운영 가능성을 보장하지 않습니다.",
            photos=[f"/__development__/seongsu/assets/interior-{1+i%4}.jpg"],
            category=p["stay_kind"], neighborhood="성수동1가" if i < 7 else "성수동2가",
            area_m2=float(p["area_m2"]), rooms=p["rooms"], guests=p["guests"],
            amenities=list(p["options"]), nightly_krw=p["nightly"],
            weekly_krw=p["weekly"], monthly_krw=p["monthly"],
            available_from=start.isoformat(), available_until=end.isoformat(),
            blocked_dates=blocked, booking_supported=True,
            point=dict(lat=37.5401 + (i % 7) * .00085,
                       lng=127.0432 + (i // 7) * .010 + (i % 3) * .0007),
            application_id=row["id"],
        )
    app.fixture_demo_catalog = catalog
    app.fixture_supermap.public_geometry = lambda key: dict(
        lat=round(catalog[key]["point"]["lat"], 2),
        lng=round(catalog[key]["point"]["lng"], 2),
        precision="approx", aggregate_scope="dong", aggregate_count=8)
    app.fixture_supermap.public_location_match = lambda key, query: (
        key in catalog and (query in {"성수", "성수동", "서울", "서울숲", "뚝섬"}
            or query in catalog[key]["name"] or query in catalog[key]["neighborhood"]))
    native = {}
    for layer, label in (("sale", "매매"), ("business", "영업권 양도"), ("auction", "공매")):
        native[layer] = []
        for i in range(3):
            key = f"demo-{layer}-{i+1}"
            meta = dict(synthetic=True, name=f"[가상] 성수 {label} 테스트 {i+1}",
                description=f"{DISCLAIMER}. 실제 매매 계약·공매 사건·영업신고가 아닙니다. "
                    "레이어 구분과 상세 요약을 확인하는 가상 항목이며 단기임대 예약 대상이 아닙니다.",
                category=layer, neighborhood="성수동2가", photos=[
                    f"/__development__/seongsu/assets/interior-{i+1}.jpg"],
                area_m2=60 + i * 40, rooms=2, guests=0, amenities=["wifi"],
                nightly_krw=None, weekly_krw=None, monthly_krw=None,
                test_asking_krw=(500000000 if layer == "sale" else 30000000 if layer == "business"
                                 else 200000000) + i * 10000000,
                available_from=start.isoformat(), available_until=end.isoformat(),
                blocked_dates=[], booking_supported=False, disclaimer=DISCLAIMER,
                point=dict(lat=37.5464 + i * .0005,
                           lng=127.043 + ("sale", "business", "auction").index(layer) * .006))
            catalog[key] = meta
            native[layer].append(dict(public=True, public_id=key, disclosure_scope="public",
                public_title=meta["name"], public_point=dict(**meta["point"], precision="exact")))
    def native_source(layer):
        return lambda values: dict(items=[
            row for row in native[layer] if not values["q"] or values["q"] in {"성수", "성수동", "서울"}
            or values["q"] in catalog[row["public_id"]]["name"]], truncated=False)
    app.fixture_supermap.legacy_layers = {layer: native_source(layer) for layer in native}
    return catalog
