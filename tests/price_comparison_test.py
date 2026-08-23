"""건물 상세 가격 비교·건물전체 객실당 가격의 경계값을 점검한다."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import _building_price_comparison


def expect(condition, message):
    if not condition:
        raise AssertionError(message)


both = _building_price_comparison(100000, 110000)
expect(
    both == {
        "recent_deal_price": 100000,
        "listing_min_price": 110000,
        "price_gap_percent": 10.0,
    },
    f"양쪽 가격의 차이율 계산이 잘못됨: {both}",
)

lower = _building_price_comparison(125000, 100000)
expect(lower["price_gap_percent"] == -20.0, f"음수 차이율 계산이 잘못됨: {lower}")

for missing in (
    (None, 110000),
    (100000, None),
    (None, None),
    (0, 110000),
    (100000, 0),
):
    result = _building_price_comparison(*missing)
    expect(
        result == {
            "recent_deal_price": None,
            "listing_min_price": None,
            "price_gap_percent": None,
        },
        f"가격 누락/0일 때 세 필드가 함께 null이 아님: {missing} → {result}",
    )

room_price = round(200000 / 25)
expect(room_price == 8000, f"객실당 가격 수기 검산 실패: 200000 / 25 = {room_price}")
expect(round(199999 / 24) == 8333, "객실당 가격 반올림 검산 실패")

app_source = (ROOT / "app.py").read_text(encoding="utf-8")
main_source = (ROOT / "static/js/main.js").read_text(encoding="utf-8")
listings_source = (ROOT / "static/listings.html").read_text(encoding="utf-8")
expect(
    "t.price AS recent_deal_price" in app_source
    and "MIN(lr.price_krw) AS listing_min_price" in app_source
    and "lt.recent_deal_price" in app_source
    and "lp.listing_min_price" in app_source
    and "COALESCE(lr.disclosure_scope, 'public') = 'public'" in app_source,
    "건물상세 API의 최근 실거래가·전체공개 매물 최저가 조회가 누락됨",
)
expect(
    "const wholeRoomPriceText = lr.price_krw != null" in main_source
    and "객실당 ${_fmtN(Math.round(Number(lr.price_krw) / Number(lr.room_count)))}만원" in main_source
    and "const roomPriceText = item.price_krw != null" in listings_source
    and "객실당 ${Math.round(Number(item.price_krw) / Number(item.room_count)).toLocaleString()}만원" in listings_source,
    "건물전체 매물의 객실당 가격이 두 카드 화면에 반영되지 않음",
)

print("OK  가격 비교 양·음수/누락 경계와 객실당 가격 검산")