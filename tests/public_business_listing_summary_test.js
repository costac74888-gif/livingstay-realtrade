// 공개 매물 화면에서 사업주 장기방의 가격·호실수 표시 정책이 빠지지 않았는지 확인한다.
const fs = require("fs");
const vm = require("vm");

function expect(condition, message) {
  if (!condition) throw new Error(message);
}

const listingsHtml = fs.readFileSync("static/listings.html", "utf8");
const listingHelpers = listingsHtml.match(
  /function fmtN\(v\)\{[\s\S]*?(?=\n\s*\/\/ ── 상태)/
);
expect(listingHelpers, "공개 목록 가격 표시 유틸리티를 찾지 못했습니다.");
const listingContext = { window: {}, Number };
vm.createContext(listingContext);
vm.runInContext(listingHelpers[0], listingContext);

const businessAvailable = {
  is_business_listing: true,
  room_price_min: 90,
  room_price_max: 120,
  room_count: 88,
};
const businessUnavailable = {
  is_business_listing: true,
  room_price_min: null,
  room_price_max: null,
  room_count: 88,
};
const owner = {
  is_business_listing: false,
  deal_type: "월세",
  price_krw: 1000,
  monthly_rent_krw: 50,
  price_krw_max: null,
  room_count: 3,
};
expect(
  listingContext.listingPriceText(businessAvailable) === "장기임대 가능 · 90~120만원/월" &&
  listingContext.listingPriceText(businessUnavailable) === "현재 문의 가능 여부는 채팅으로 확인해주세요" &&
  listingContext.listingPriceText(owner) === "보1,000/50만",
  "게시판·카드형 사업주 가격 또는 기존 매물 가격 표시가 올바르지 않습니다."
);
expect(
  listingsHtml.includes("!item.is_business_listing && item.room_count") &&
  listingsHtml.includes("listingPriceText(item) + rooms") &&
  listingsHtml.includes("const priceStr = listingPriceText(item)"),
  "게시판형 또는 카드형에서 사업주 호실수 비노출·가격 요약을 사용하지 않습니다."
);

const mainJs = fs.readFileSync("static/js/main.js", "utf8");
const detailHelpers = mainJs.match(
  /function _businessStayPriceText\(lr, formatNumber\)\{[\s\S]*?(?=\n\s*function _openDirectListingCard)/
);
expect(detailHelpers, "건물상세 매물 가격 표시 유틸리티를 찾지 못했습니다.");
const detailContext = { Number };
vm.createContext(detailContext);
vm.runInContext(detailHelpers[0], detailContext);
const formatNumber = (value) => value != null ? Number(value).toLocaleString() : "-";
expect(
  detailContext._listingPriceText(businessAvailable, formatNumber) === "장기임대 가능 · 90~120만원/월" &&
  detailContext._listingPriceText(businessUnavailable, formatNumber) === "현재 문의 가능 여부는 채팅으로 확인해주세요" &&
  detailContext._listingPriceText(owner, formatNumber) === "보1,000/50만",
  "건물상세 카드·팝업의 사업주 가격 또는 기존 매물 가격 표시가 올바르지 않습니다."
);
expect(
  mainJs.includes("!lr.is_business_listing && lr.room_count") &&
  mainJs.includes("const priceText = _listingPriceText(lr, formatNumber)") &&
  mainJs.includes("const priceText = _listingPriceText(lr, _fmtN)"),
  "건물상세 목록 또는 상세 팝업에서 사업주 호실수 비노출·가격 요약을 사용하지 않습니다."
);
expect(
  listingsHtml.includes("permitBadgeHtml") &&
  listingsHtml.includes("operationRatioBadgesHtml") &&
  listingsHtml.includes("permit_number_masked") &&
  listingsHtml.includes("short_stay_ratio") &&
  listingsHtml.includes("ota_revenue_ratio") &&
  mainJs.includes("_permitBadgeMarkup") &&
  mainJs.includes("_operationRatioMarkup"),
  "신고번호 마스킹 또는 운영 비율 배지가 공개 목록·건물상세에 연결되지 않았습니다."
);

console.log("OK  사업주 공개 장기방 가격·문의 안내·호실수 비노출 화면");