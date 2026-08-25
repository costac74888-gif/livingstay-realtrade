// 직거래 매물 카드·게시판·건물상세의 사진 배지와 SVG 행동 버튼을 회귀 점검한다.
const fs = require("fs");

function expect(condition, message) {
  if (!condition) throw new Error(message);
}

const listings = fs.readFileSync("static/listings.html", "utf8");
const main = fs.readFileSync("static/js/main.js", "utf8");
const icons = fs.readFileSync("static/js/listing_icons.js", "utf8");

const inlineScript = listings.match(/<script>\s*((?:\(function\(\)\{)[\s\S]*?)<\/script>\s*<\/body>/);
expect(inlineScript, "static/listings.html의 인라인 스크립트를 찾지 못했습니다.");
new Function(inlineScript[1]);

for (const needle of [
  'class="ls-card-l1"',
  'class="ls-card-l2"',
  'class="ls-card-l3"',
  'class="ls-card-l4"',
  'class="ls-card-photo-right"',
  'class="listing-like-btn${',
  'class="listing-chat-btn',
  'class="listing-share-btn"',
  'LivingstayListingIcons.chat()',
  'LivingstayListingIcons.share()',
  'LivingstayListingIcons.heart(!!item.liked)',
  'LivingstayListingIcons.photoCount(photoCount)',
  'e.stopPropagation();\n      openChat(item.id);',
]) {
  expect(listings.includes(needle), `목록 카드 4줄/사진/행동 UI 누락: ${needle}`);
}

expect(
  main.includes('class="b-listing-l1"') &&
  main.includes('class="b-listing-l2"') &&
  main.includes('class="b-listing-l3"') &&
  main.includes('class="b-listing-l4"') &&
  main.includes('class="b-listing-photo-btn listing-photo-btn"') &&
  main.includes('LivingstayListingIcons.photoCount(photos.length)') &&
  main.includes('LivingstayListingIcons.heart(!!lr.liked)') &&
  main.includes('listingsBody.querySelectorAll(".listing-share-btn")'),
  "건물상세 매물 카드가 동일한 4줄/사진 배지/SVG 행동 구조가 아닙니다."
);
expect(
  icons.includes("LivingstayListingIcons") &&
  icons.includes("photoCount") &&
  icons.includes('fill="currentColor"'),
  "공용 SVG 아이콘 또는 활성 찜 채움 아이콘이 없습니다."
);
const iconContext = { window: {} };
require("vm").createContext(iconContext);
require("vm").runInContext(icons, iconContext);
expect(
  iconContext.window.LivingstayListingIcons.photoCount(2).includes("ls-photo-count") &&
  iconContext.window.LivingstayListingIcons.photoCount(5).includes(">5</span>") &&
  iconContext.window.LivingstayListingIcons.photoCount(1) === "",
  "사진 2장 이상 배지 또는 1장 이하 숨김 규칙이 정확하지 않습니다."
);
const boardBlock = listings.slice(listings.indexOf("function renderBoardRow"), listings.indexOf("function renderWholeListingCard"));
const cardBlock = listings.slice(listings.indexOf("function renderCardItem"), listings.indexOf("// ── 목록 로드"));
const detailBlock = main.slice(main.indexOf("function _renderListings"), main.indexOf("_renderListings(allListings)"));
for (const [name, block] of [["게시판형", boardBlock], ["카드형", cardBlock]]) {
  expect(
    block.indexOf("LivingstayListingIcons.heart(") < block.indexOf("LivingstayListingIcons.chat()") &&
    block.indexOf("LivingstayListingIcons.chat()") < block.indexOf("LivingstayListingIcons.share()"),
    `${name} 행동 버튼 순서가 찜 → 채팅 → 공유가 아닙니다.`
  );
}
const normalDetailBlock = detailBlock.slice(detailBlock.indexOf("return `<div class=\"b-listing-card\""), detailBlock.indexOf("}).join(\"\");"));
expect(
  normalDetailBlock.indexOf("LivingstayListingIcons.heart(") < normalDetailBlock.indexOf("LivingstayListingIcons.chat()") &&
  normalDetailBlock.indexOf("LivingstayListingIcons.chat()") < normalDetailBlock.indexOf("LivingstayListingIcons.share()"),
  "기존 개별호실 건물상세 카드의 행동 버튼 순서가 바뀌었습니다."
);
for (const [name, block] of [
  ["목록 건물전체", listings.slice(listings.indexOf("function renderWholeListingCard"), listings.indexOf("function renderCardItem"))],
  ["건물상세 건물전체", detailBlock.slice(detailBlock.indexOf("function _wholeListingCard"), detailBlock.indexOf("const cards = listings.map"))],
]) {
  expect(
    block.includes("급매") && block.includes("최근 폐업") && block.includes("매출정보 있음") &&
    block.includes("실인수가") && block.includes("🔒 로그인하고 보기") &&
    block.includes("최근 열람") && block.includes("부대비용 기준의 참고값"),
    `${name} 전용 카드의 거래조건·마스킹·열람자·유의문구가 누락되었습니다.`
  );
  expect(
    block.indexOf("LivingstayListingIcons.heart(") < block.indexOf("LivingstayListingIcons.chat()") &&
    block.indexOf("LivingstayListingIcons.chat()") < block.indexOf("LivingstayListingIcons.share()"),
    `${name} 건물전체 카드의 행동 버튼 순서가 찜 → 채팅 → 공유가 아닙니다.`
  );
}
expect(
  listings.includes("/api/listings/views") && main.includes("/api/listings/views"),
  "건물전체 카드의 실제 열람자 기록 API 호출이 없습니다."
);
const wholeCardBlock = listings.slice(
  listings.indexOf("function renderWholeListingCard"),
  listings.indexOf("function renderCardItem")
);
const normalCardBlock = listings.slice(
  listings.indexOf("function renderCardItem"),
  listings.indexOf("// ── 목록 로드")
);
expect(
  listings.includes(".ls-card-photo-top") &&
  wholeCardBlock.includes('const photoClass = isLimitedListing ? "ls-card-photo-top" : "ls-card-photo-right"') &&
  wholeCardBlock.includes("whole-limited-notice") &&
  wholeCardBlock.includes("const checklistButton = isLimitedListing"),
  "제한공개 카드의 상단 사진·안내문·체크리스트 조건이 없습니다."
);
expect(
  wholeCardBlock.includes("openListingDetail(item);") &&
  normalCardBlock.includes("openListingDetail(item);") &&
  wholeCardBlock.includes(".ls-card-photo-right, .ls-card-photo-top") &&
  normalCardBlock.includes(".ls-card-photo-right, .ls-card-photo-top") &&
  !wholeCardBlock.match(/if \(window\.innerWidth > 520\) return/) &&
  !normalCardBlock.match(/if \(window\.innerWidth > 520\) return/),
  "PC 카드 전체 클릭 또는 사진 강조 예외 처리가 없습니다."
);
expect(
  listings.includes('data-disclosure-scope="public"') &&
  listings.includes('data-disclosure-scope="limited"') &&
  listings.includes('params.set("disclosure_scope", state.disclosure_scope)') &&
  listings.includes("item.is_limited_listing") &&
  listings.includes('shareUrl.searchParams.set("disclosure_scope", "limited")'),
  "공개범위 탭 또는 제한공개 익명·공유 처리 연결이 없습니다."
);
expect(
  wholeCardBlock.includes("const keyMoney = Number(item.key_money_krw || 0)") &&
  wholeCardBlock.includes("price - loan + keyMoney + (price * 0.061)") &&
  wholeCardBlock.indexOf('<div class="whole-metrics">') < wholeCardBlock.indexOf('<div class="whole-badges">') &&
  wholeCardBlock.indexOf('<div class="whole-badges">') < wholeCardBlock.indexOf("${limitedNotice}"),
  "건물전체 카드의 권리금 반영 실인수가 또는 배지 하단 배치가 없습니다."
);
const modal = fs.readFileSync("static/js/listing_modal.js", "utf8");
expect(
  modal.includes("data-listing-detail-map") &&
  modal.includes("location_precision === \"approximate\"") &&
  modal.includes("approx_lat") &&
  modal.includes("https://map.kakao.com/link/map/"),
  "공개범위별 정확·근사 지도위치 버튼 연결이 없습니다."
);

expect(
  main.includes('<div class="side-card-title">직거래 매물</div>') &&
  !main.includes('직거래 매물 <span class="side-sub">공개 등록</span>'),
  "건물상세의 공개 등록 라벨이 제거되지 않았습니다."
);

console.log("OK  직거래 카드·게시판·건물상세 SVG 버튼/사진 배지/공개등록 라벨 회귀 점검");