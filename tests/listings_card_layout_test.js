// 직거래 매물 카드가 4줄 정보·우측 사진 구조를 유지하고 게시판형은 건드리지 않았는지 확인한다.
const childProcess = require("child_process");
const fs = require("fs");

function expect(condition, message) {
  if (!condition) throw new Error(message);
}

const listings = fs.readFileSync("static/listings.html", "utf8");
const main = fs.readFileSync("static/js/main.js", "utf8");

const inlineScript = listings.match(/<script>\s*((?:\(function\(\)\{)[\s\S]*?)<\/script>\s*<\/body>/);
expect(inlineScript, "static/listings.html의 인라인 스크립트를 찾지 못했습니다.");
new Function(inlineScript[1]);

for (const needle of [
  'class="ls-card-l1"',
  'class="ls-card-l2"',
  'class="ls-card-l3"',
  'class="ls-card-l4"',
  'class="ls-card-photo-right"',
  'class="listing-like-btn"',
  'class="listing-chat-btn',
  'class="listing-share-btn"',
  'highlightCardItem(div)',
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
  main.includes('listingsBody.querySelectorAll(".listing-share-btn")'),
  "건물상세 매물 카드가 동일한 4줄/사진/공유 구조가 아닙니다."
);

const zeroContextDiff = childProcess.execSync(
  "git diff --unified=0 -- static/listings.html",
  { encoding: "utf8" }
);
expect(
  !zeroContextDiff.includes("renderBoardRow"),
  "게시판형 renderBoardRow가 이번 카드형 변경 diff에 포함되었습니다."
);

console.log("OK  직거래 카드 4줄·우측사진·찜/채팅/공유 및 게시판형 회귀 방지");