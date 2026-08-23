// 매물등록 모달의 등록자유형 순서·프리셋·건물상세 버튼 회귀 테스트.
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const modal = fs.readFileSync(path.join(root, "static/js/listing_modal.js"), "utf8");
const main = fs.readFileSync(path.join(root, "static/js/main.js"), "utf8");
const listings = fs.readFileSync(path.join(root, "static/listings.html"), "utf8");
const index = fs.readFileSync(path.join(root, "static/index.html"), "utf8");
const css = fs.readFileSync(path.join(root, "static/css/main.css"), "utf8");

function expect(condition, message) {
  if (!condition) throw new Error(message);
}

const modeAt = modal.indexOf('id="lrModeSection"');
const targetAt = modal.indexOf('id="lrTargetSection"');
const registrantAt = modal.indexOf('id="lrRegistrantType"');
const dealAt = modal.indexOf('id="lrUnitDealButtons"');
const detailAt = modal.indexOf("상세 정보");
expect(modeAt >= 0 && targetAt > modeAt && registrantAt > targetAt && dealAt > registrantAt && detailAt > dealAt,
  "폼 순서가 진행방식 → 거래대상 → 등록자유형 → 거래방식 → 상세정보가 아닙니다.");
for (const id of [
  "lrWholeDealButtons", "lrWholeSalePrice", "lrSuccessionLoan", "lrRealTakeover",
  "lrWholeDeposit", "lrKeyMoney", "lrMonthlyRevenue", "lrAnnualRevenue",
  "lrOperationStatus", "lrDisclosureScope", "lrWholeBuildingInfo",
  "lrShortStayRatio", "lrOtaRevenueRatio", "lrDisclosureHelp",
]) {
  expect(modal.includes(`id="${id}"`), `건물전체 매물 입력란 ${id}이 없습니다.`);
}
expect(
  modal.includes('transaction_target: transactionTarget') &&
  modal.includes("WHOLE_DESCRIPTION_TEMPLATE") &&
  modal.includes("/whole-listing-context") &&
  modal.includes("WHOLE_ACQUISITION_COST_RATE"),
  "건물전체 거래대상·설명 템플릿·자동 정보·실인수가 계산 연결이 없습니다."
);
expect(
  modal.includes("var MAX_PHOTOS = 10") &&
  modal.includes("최대 10장") &&
  modal.includes("lr-photo-public") &&
  modal.includes("photo_public") &&
  modal.includes("사진 공개"),
  "사진 최대 10장 또는 사진별 공개 설정 연결이 없습니다."
);
expect(
  modal.includes("대실 비율") &&
  modal.includes("OTA 매출 비중") &&
  modal.includes("short_stay_ratio") &&
  modal.includes("ota_revenue_ratio") &&
  modal.includes("updateDisclosureHelp") &&
  modal.includes('key === "zoning" && (value == null || value === "")'),
  "운영 비율·공개범위 안내·빈 용도지역 숨김 처리가 없습니다."
);
expect(
  modal.includes("반경 500m 내 동종 숙박시설") &&
  modal.includes("station_name") &&
  modal.includes("도보 약"),
  "건물전체 STEP5의 경쟁업소 합계 또는 지하철 도보시간 표시가 없습니다."
);
expect(
  listings.includes("wholeLocationHint") &&
  listings.includes("loadWholeLocationHints") &&
  listings.includes("/api/whole-listing-contexts") &&
  listings.includes("경쟁업소") &&
  main.includes("_wholeLocationContext") &&
  main.includes("b-whole-location"),
  "건물전체 공개 카드의 경쟁업소·지하철 입지정보 연결이 없습니다."
);
expect(
  !index.includes('id="platformStats"') &&
  !index.includes('data-platform-stat=') &&
  main.includes("/api/stats/platform-summary") &&
  main.includes("async function loadPlatformStats") &&
  css.includes(".platform-stats") &&
  css.includes("grid-template-columns:repeat(2,minmax(0,1fr))"),
  "홈 검색창의 4개 지표가 제거되지 않았거나 데이터랩 재사용용 통계 API 계약이 없습니다."
);

for (const [value, label] of [
  ["owner", "소유자 또는 대리인"],
  ["building_owner", "건물주 또는 대리인"],
  ["business", "사업주(숙박업대표) 또는 대리인"],
]) {
  expect(modal.includes(`{value: "${value}", label: "${label}"}`),
    `등록자유형 ${value} / ${label} 옵션이 없습니다.`);
}
expect(modal.includes("form.dataset.registrantType"),
  "등록자유형 변경 플래그가 폼 data 속성에 저장되지 않습니다.");
for (const id of [
  "lrAreaBusiness", "lrRoomCount", "lrRoomCountHelp",
  "lrWolsePriceMin", "lrWolsePriceMax", "lrShortPriceMin", "lrShortPriceMax",
]) {
  expect(modal.includes(`id="${id}"`), `사업주 전용 입력란 ${id}이 없습니다.`);
}
for (const id of ["lrSalePriceMin", "lrSalePriceMax", "lrJeonseDepositMin", "lrJeonseDepositMax"]) {
  expect(!modal.includes(`id="${id}"`), `매매/전세에 남은 사업주 가격범위 입력란 ${id}이 있습니다.`);
}
expect(modal.includes("/lodging-summary") && modal.includes("loadLodgingSummary"),
  "사업주 대표 숙박업 객실수 자동채움 API 호출이 없습니다.");
expect(modal.includes("price_krw_max") && modal.includes("priceMax"),
  "가격범위 최고가 전송이 없습니다.");
expect(
  modal.includes('$("#lrAreaOwnerWrap").style.display = !whole && !isBusiness ? "block" : "none"') &&
  modal.includes('$("#lrAreaBusinessWrap").style.display = !whole && isBusiness ? "block" : "none"') &&
  modal.includes('$("#lrPriceWolseBusiness").style.display = dealType === "월세" && isBusiness && !whole ? "flex" : "none"') &&
  modal.includes('$("#lrShortTermBusiness").style.display = dealType === "단기임대" && isBusiness && !whole ? "flex" : "none"') &&
  modal.includes('$("#lrPriceSale").style.display = dealType === "매매" && !isBusiness && !whole ? "block" : "none"') &&
  modal.includes('$("#lrWholeSale").style.display = whole && dealType === "매매" ? "block" : "none"'),
  "사업주/소유자 전용면적 전환 또는 거래유형별 수익률 표시 로직이 없습니다."
);

expect(main.includes('id="btnBuyRequest"') && main.includes("display:none"),
  "매수의뢰 버튼이 숨김 처리되지 않았습니다.");
expect(!main.includes("btnLongTermRoom") && !main.includes("장기방 내놓기"),
  "제거된 장기방 내놓기 버튼 또는 클릭 코드가 남아 있습니다.");
for (const id of [
  "lrBusinessVerifyGate", "lrBusinessPermitNumber", "lrBusinessVerifySubmit",
]) {
  expect(modal.includes(`id="${id}"`), `사업주 영업신고번호 인증 UI ${id}가 없습니다.`);
}
expect(
  modal.includes("/business-verification") &&
  modal.includes("checkBusinessVerification") &&
  modal.includes("phone_verified && user.phone") &&
  modal.includes("else showListingForm()"),
  "기존 휴대폰 인증 계정 건너뛰기 또는 사업주 신고번호 인증 흐름이 없습니다."
);
const verifyStart = modal.indexOf("function checkBusinessVerification()");
const verifyEnd = modal.indexOf("\n    }\n    $(\"#lrBusinessVerifySubmit\")", verifyStart);
const verifyBlock = modal.slice(verifyStart, verifyEnd);
const verifyFetchAt = verifyBlock.indexOf('fetch("/api/building/"');
const verifyGateAfterFetchAt = verifyBlock.indexOf("showBusinessGate();", verifyFetchAt);
expect(
  verifyStart >= 0 &&
  verifyFetchAt > 0 &&
  verifyBlock.indexOf('$("#lrAuthLoading").style.display = "block";') < verifyFetchAt &&
  verifyBlock.indexOf('form.style.display = "none";') < verifyFetchAt &&
  verifyBlock.indexOf('businessGate.style.display = "none";') < verifyFetchAt &&
  verifyGateAfterFetchAt > verifyFetchAt &&
  verifyBlock.indexOf("showListingForm();", verifyFetchAt) > verifyFetchAt,
  "사업주 인증 상태 확인 전에 게이트가 노출되거나, 공용 로딩 처리 순서가 잘못되었습니다."
);
const verifyCatchAt = verifyBlock.indexOf("}).catch(function (error) {");
expect(
  verifyCatchAt > verifyFetchAt &&
  verifyBlock.indexOf("showBusinessGate();", verifyCatchAt) > verifyCatchAt,
  "사업주 인증 API 오류 시 게이트가 노출되지 않습니다."
);
expect(
  modal.includes("DRAFT_REGISTRANT_LABELS") &&
  modal.includes('business: "사업주 등록"') &&
  modal.includes('owner: "소유자 등록"') &&
  modal.includes('building_owner: "건물주 등록"') &&
  modal.includes('agent: "중개사 등록"') &&
  modal.includes('other: "기타 관계자 등록"'),
  "초안 복원용 등록자유형 한글 라벨 매핑이 없습니다."
);
expect(
  modal.includes("draftRegistrantLabel(draftInfo.registrant_type)") &&
  modal.includes("draftDealLabel(draftInfo.deal_type)") &&
  modal.includes("매물 정보(\" + draftSummary + \")가 있습니다."),
  "초안 복원 확인창에 저장된 등록자유형·거래유형이 포함되지 않습니다."
);
const helperStart = modal.indexOf("var DRAFT_REGISTRANT_LABELS =");
const helperEnd = modal.indexOf("\n\n  function registrantOptions", helperStart);
expect(helperStart >= 0 && helperEnd > helperStart, "초안 라벨 변환 함수를 찾지 못했습니다.");
const helperContext = {};
require("vm").createContext(helperContext);
require("vm").runInContext(
  "var DEAL_TYPES = ['매매', '전세', '월세', '단기임대'];\n" +
  modal.slice(helperStart, helperEnd) +
  "\nvar businessSummary = draftRegistrantLabel('business') + ', ' + draftDealLabel('단기임대');" +
  "\nvar ownerSummary = draftRegistrantLabel('owner') + ', ' + draftDealLabel('매매');",
  helperContext
);
expect(
  helperContext.businessSummary === "사업주 등록, 단기임대" &&
  helperContext.ownerSummary === "소유자 등록, 매매",
  "사업주·소유자 초안의 확인창 라벨 조합이 정확하지 않습니다."
);
expect(
  main.includes("lr.price_krw_max") && main.includes("lr.room_count") &&
  listings.includes("item.price_krw_max") && listings.includes("item.room_count"),
  "건물상세 또는 공개 매물 목록에서 사업주 가격범위·총 호실수가 표시되지 않습니다."
);

console.log("OK  등록자유형·사업주 가격범위/호실수·휴대폰 인증 건너뛰기·신고번호 인증·장기방 버튼 제거");