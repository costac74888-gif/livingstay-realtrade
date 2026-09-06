const fs = require("fs");

const main = fs.readFileSync("static/js/main.js", "utf8");
const css = fs.readFileSync("static/css/main.css", "utf8");

function expect(condition, message) {
  if (!condition) {
    console.error(`FAIL ${message}`);
    process.exit(1);
  }
}

expect(
  main.includes('data-lodging-breakdown-row="tourism" hidden') &&
  main.includes('data-lodging-breakdown-row="general" hidden') &&
  main.includes('data-lodging-breakdown-row="camping" hidden'),
  "관광숙박·일반숙박·캠핑 세부행이 모두 초기 접힘 상태여야 합니다.",
);
expect(
  main.includes('data-lodging-collapse="${breakdownKind}"') &&
  main.includes('content.querySelectorAll("[data-lodging-collapse]")'),
  "세 유형이 공통 화살표 토글을 사용해야 합니다.",
);
expect(
  main.includes('button.setAttribute("aria-expanded", String(expanded))') &&
  main.includes('세부항목 ${expanded ? "숨기기" : "보기"}'),
  "토글 접근성 상태와 설명이 함께 갱신되어야 합니다.",
);
expect(
  css.includes('.datalab-breakdown-row[hidden]{display:none;}') &&
  css.includes('.datalab-row-toggle[aria-expanded="true"] .datalab-collapse-label::before{content:"▴";}'),
  "공통 접힘 행과 화살표 방향 CSS가 필요합니다.",
);

console.log("OK  숙박 통계 관광·일반·캠핑 접기/펼치기");