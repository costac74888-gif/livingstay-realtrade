// 이용안내의 기존 기능 안내 보존과 매물·안전 신규 콘텐츠 회귀 테스트.
const fs = require("fs");
const path = require("path");

const guide = fs.readFileSync(path.join(__dirname, "..", "static", "guide.html"), "utf8");
const mypage = fs.readFileSync(path.join(__dirname, "..", "static", "mypage.html"), "utf8");

function expect(condition, message) {
  if (!condition) throw new Error(message);
}

for (const text of [
  "실거래가 무료조회",
  "관심단지",
  "최근 본 건물",
  "시세 랭킹",
]) {
  expect(guide.includes(text), `기존 이용안내 '${text}'가 사라졌습니다.`);
}

for (const text of [
  "생숙 등 개별 호실이신가요, 모텔·호텔 건물 전체이신가요?",
  "개별호실",
  "건물전체",
  "실인수가 자동계산",
  "운영정보(매출·상태)",
  "정상 영업 중인데 매물로 나온 걸 알리고 싶지 않다면?",
  "전체공개",
  "제한공개",
  "건물명 노출 여부",
  "노출 위치",
  "정확한 정보는 채팅 시작 후 판매자에게 문의하세요",
  "구체적인 건물명·매물 정보는 자동으로 공개되지 않습니다",
  "예상 취득부대비용 6.1%",
  "저장되지 않는 참고값",
  "사업주(숙박업대표)",
  "직접 등록한 매물의 소유자",
  "매물내놓기 현황",
  "사업장 관리",
  "방 재고",
  "입실",
  "공실",
  "OTA전용",
  "장박가능",
  "계약만기 임박 자동알림",
  "이메일과 사이트 알림",
  "휴대폰 인증",
  "채팅 시작",
  "연락처 공유 주의",
  "영업신고번호를 한 번 인증",
  "다시 등록할 때 인증을 생략",
  "매출·운영정보는 매도자가 등록한 수치이며",
]) {
  expect(guide.includes(text), `신규 이용안내 문구 '${text}'가 없습니다.`);
}

for (const id of ["listing-guide", "disclosure-guide", "business-guide", "safe-chat-guide", "trust-notice"]) {
  expect(guide.includes(`id="${id}"`), `이용안내 섹션 ${id}가 없습니다.`);
}

const listingAt = guide.indexOf('id="listing-guide"');
const disclosureAt = guide.indexOf('id="disclosure-guide"');
const businessAt = guide.indexOf('id="business-guide"');
const chatAt = guide.indexOf('id="safe-chat-guide"');
const trustAt = guide.indexOf('id="trust-notice"');
expect(listingAt < disclosureAt && disclosureAt < businessAt && businessAt < chatAt && chatAt < trustAt,
  "신규 이용안내 섹션 순서가 매물 유형 → 공개범위 → 사업주 → 채팅 → 신뢰장치가 아닙니다.");
expect(!guide.includes("정확한 정보는 채팅 시작 후에만 공개됩니다"),
  "제한공개 정보가 채팅 시작만으로 자동 공개된다고 안내하면 안 됩니다.");
expect(!guide.includes("연락처 노출 자동 경고"),
  "연락처를 자동 감지·경고하는 미구현 기능을 안내하면 안 됩니다.");
expect(!guide.includes("사업장 관리 탭"),
  "실제 존재하지 않는 마이페이지 사업장 관리 탭을 안내하면 안 됩니다.");
expect(
  mypage.includes('data-tab="listing"') && mypage.includes("매물내놓기 현황"),
  "안내가 가리키는 마이페이지 매물내놓기 현황 탭이 실제 페이지에 없습니다."
);

expect(
  guide.includes(".guide-dual-grid") &&
  guide.includes(".guide-inventory-layout") &&
  guide.includes(".guide-safety-grid") &&
  guide.includes("@media (max-width: 680px)") &&
  guide.includes("grid-template-columns: 1fr"),
  "이용안내 모바일 카드 반응형 스타일이 없습니다."
);

console.log("OK  이용안내 기존 기능 보존·매물·공개범위·사업주·채팅·면책 콘텐츠");