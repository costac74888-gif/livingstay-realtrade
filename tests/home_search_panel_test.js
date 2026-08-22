// 홈 지도 검색바가 버튼을 한 줄로 유지하고 관심단지를 접어 두는지 정적 회귀 점검한다.
const fs = require("fs");

const html = fs.readFileSync("static/index.html", "utf8");
const css = fs.readFileSync("static/css/main.css", "utf8");
const main = fs.readFileSync("static/js/main.js", "utf8");

function expect(condition, message) {
  if (!condition) throw new Error(message);
}

expect(
  html.includes('class="search-actions"') &&
  html.includes('id="btnSearch"') &&
  html.includes('id="btnResetSearch"'),
  "검색·초기화 버튼 공통 행 컨테이너가 없습니다."
);
expect(
  html.includes('class="fav-chips"') &&
  html.includes('class="transactions-note"') &&
  html.includes('class="note-info"') &&
  html.includes('id="btnOpenSubmit"'),
  "관심단지·안내·내 건물 수정 요청 압축 UI가 없습니다."
);
expect(
  css.includes(".search-actions{display:flex") &&
  css.includes(".search-grid{display:flex") &&
  css.includes(".search-row2{gap:8px; overflow-x:auto") &&
  css.includes(".note-full{display:none;}"),
  "모바일 가로 스크롤·안내 축소 CSS가 없습니다."
);
expect(
  main.includes("const visibleKeys = favs.slice(0, 4);") &&
  main.includes("const hiddenKeys = favs.slice(4);") &&
  main.includes("`+더보기(${hiddenKeys.length})`") &&
  main.includes("fav-overflow-popover"),
  "관심단지 4개 제한 또는 더보기 팝오버 로직이 없습니다."
);
expect(
  main.includes("trackRecentBuilding(id, bName") &&
  !main.includes("trackRecentBuilding(buildingId, bName"),
  "건물 상세의 최근 본 건물 기록이 정의되지 않은 식별자를 사용합니다."
);

console.log("OK  홈 검색바 압축·관심단지 더보기·모바일 가로 스크롤·최근 본 건물 UI");