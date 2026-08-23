// 건물전체 매물 체크리스트의 노출 조건과 저장 경로가 사라지지 않는지 정적으로 확인한다.
const fs = require("fs");
const path = require("path");

const main = fs.readFileSync(path.join(__dirname, "..", "static", "js", "main.js"), "utf8");
const listings = fs.readFileSync(path.join(__dirname, "..", "static", "listings.html"), "utf8");
const checklist = fs.readFileSync(path.join(__dirname, "..", "static", "js", "listing_checklist.js"), "utf8");
const css = fs.readFileSync(path.join(__dirname, "..", "static", "css", "main.css"), "utf8");

function expect(condition, message) {
  if (!condition) throw new Error(message);
}

expect(main.includes('isWholeListing ? `<button type="button" class="listing-checklist-open"'),
  "홈 상세 카드의 건물전체 전용 체크리스트 버튼이 없습니다.");
expect(!main.includes('!isWholeListing ? `<button type="button" class="listing-checklist-open"'),
  "개별호실 매물에 체크리스트 버튼이 노출됩니다.");
expect(listings.includes('window.LivingstayListingChecklist?.open(item.id)'),
  "매물 목록의 체크리스트 열기 연결이 없습니다.");
expect(checklist.includes("STORAGE_PREFIX = \"hs_listing_checklist:\""),
  "비로그인 매물별 localStorage 키가 없습니다.");
expect(checklist.includes("/checklist/progress") && checklist.includes("credentials: \"same-origin\""),
  "로그인 체크 상태 서버 저장 경로가 없습니다.");
expect(checklist.includes("매도자 제공, 미검증") && checklist.includes("정보 없음"),
  "매도자값 미검증 라벨 또는 빈 값 안내가 없습니다.");
expect(checklist.includes("target=\"_blank\"") && checklist.includes("홈앤스테이는 정확성을 보증하지 않습니다"),
  "공인기관 새 탭 링크 또는 면책문구가 없습니다.");
expect(css.includes(".listing-checklist-disclaimer{position:sticky"),
  "체크리스트 상단 고정 면책문구 스타일이 없습니다.");

console.log("OK  건물전체 거래 체크리스트 UI·저장·공개조건 회귀");