// 홈 지도 검색바가 모바일에서 화면 폭을 채우고 관심단지 칩을 보장하는지 점검한다.
const fs = require("fs");
const vm = require("vm");

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
  css.includes("right:var(--stage-gap);") &&
  css.includes("top:calc(var(--stage-gap) + 52px);") &&
  css.includes("width:auto; max-width:none;") &&
  css.includes("grid-template-columns:repeat(2,minmax(0,1fr));") &&
  css.includes("grid-column:1 / -1;") &&
  css.includes(".map-searchbar .search-row2") &&
  css.includes("flex-wrap:wrap; white-space:normal; overflow:visible;") &&
  css.includes("#favChips:not(:empty)") &&
  css.includes(".note-full{display:none;}"),
  "모바일 검색바 폭 확장·관심단지 줄바꿈 CSS가 없습니다."
);
expect(
  main.includes("const visibleKeys = favs.slice(0, 3);") &&
  main.includes("const hiddenKeys = favs.slice(3);") &&
  main.includes("`+더보기(${hiddenKeys.length})`") &&
  main.includes("fav-overflow-popover") &&
  main.includes("closeFavOverflowPopover();\n    try {") &&
  main.includes("_favOverflowPopoverButton.setAttribute(\"aria-expanded\", \"false\")") &&
  main.includes("window.openBuildingDetail = function(id){\n  closeFavOverflowPopover();"),
  "관심단지 4개 제한 또는 더보기 팝오버 로직이 없습니다."
);
expect(
  main.includes("function _renderDetailCards(b, buildingId)") &&
  main.includes("trackRecentBuilding(buildingId, bName") &&
  !main.includes("trackRecentBuilding(id, bName") &&
  main.includes("_renderDetailCards(fresh, buildingId)") &&
  main.includes("_renderDetailCards(b, id)"),
  "건물 상세의 최근 본 건물 기록이 _renderDetailCards의 실제 ID를 사용하지 않습니다."
);

const trackStart = main.indexOf("function trackRecentBuilding(id, name, addr){");
const trackEnd = main.indexOf("\n}\n\nfunction renderRecentChips", trackStart);
expect(trackStart >= 0 && trackEnd > trackStart, "최근 본 건물 기록 함수를 찾지 못했습니다.");
const storage = {};
const trackContext = {
  localStorage: {
    getItem: (key) => storage[key] || null,
    setItem: (key, value) => { storage[key] = value; },
  },
  renderRecentChips: () => {},
  Date,
  JSON,
};
vm.createContext(trackContext);
vm.runInContext(
  "const HS_RECENT_KEY = 'hs_recent_buildings'; const HS_RECENT_MAX = 5;\n" +
  main.slice(trackStart, trackEnd + 2),
  trackContext
);
for (let id = 1; id <= 6; id += 1) {
  vm.runInContext(`trackRecentBuilding(${id}, '건물 ${id}', '주소 ${id}');`, trackContext);
}
const recent = JSON.parse(storage.hs_recent_buildings || "[]");
expect(
  recent.length === 5 && recent[0].id === 6 && recent[4].id === 2,
  "최근 본 건물이 최신순 5개로 보관되지 않습니다."
);
vm.runInContext("trackRecentBuilding('6', '건물 6 갱신', '주소 6');", trackContext);
const refreshed = JSON.parse(storage.hs_recent_buildings || "[]");
expect(
  refreshed.length === 5 && refreshed[0].id === 6 && refreshed[0].name === "건물 6 갱신",
  "최근 본 건물의 문자열·숫자 ID 중복이 정리되지 않습니다."
);
expect(
  main.includes('onclick="openBuildingDetail(${Number(b.id)}); return false;"') &&
  main.includes("function closeMapSearchbar()") &&
  main.includes("closeMapSearchbar();"),
  "최근검색과 모바일 지도위치가 공통 상세 이동·검색바 닫기 동작을 사용하지 않습니다."
);

console.log("OK  홈 검색바 압축·관심단지 더보기·최근 본 건물 기록·모바일 UI");