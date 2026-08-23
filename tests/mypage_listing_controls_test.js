// 마이페이지 매물 보류·공개범위 조작 UI 계약을 정적으로 확인한다.
const fs = require("fs");

const html = fs.readFileSync("static/mypage.html", "utf8");

function expect(condition, message) {
  if (!condition) throw new Error(message);
}

for (const needle of [
  '"보류": "보류중"',
  'class="lr-hold-btn"',
  'class="lr-resume-btn"',
  'class="lr-disclosure-btn"',
  'if (it.transaction_target === "whole")',
  'isResume ? "resume" : "hold"',
  '"/disclosure-scope"',
  'method: "PATCH"',
  'disclosure_scope: nextScope',
  'btn.setAttribute("data-scope", nextScope)',
]) {
  expect(html.includes(needle), `매물 보류·공개범위 UI 누락: ${needle}`);
}

const cardStart = html.indexOf('class="lr-edit-btn"');
const holdStart = html.indexOf("holdButton", cardStart);
const withdrawStart = html.indexOf('class="lr-withdraw-btn"', cardStart);
const disclosureStart = html.indexOf("scopeButton +", cardStart);
expect(
  cardStart >= 0 && holdStart > cardStart && withdrawStart > holdStart && disclosureStart > withdrawStart,
  "매물 조작 버튼이 수정·보류·철회·공개범위 순서로 렌더링되지 않습니다."
);

console.log("OK  매물 보류·보류해제·공개범위 토글 UI 계약");