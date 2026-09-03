// 관심단지 전체 칩과 최근검색 칩이 모두 건물 상세 이동을 사용하는지 검증한다.
const fs = require("fs");
const vm = require("vm");

const main = fs.readFileSync("static/js/main.js", "utf8");

function expect(condition, message) {
  if (!condition) throw new Error(message);
}

expect(main.includes("let serverFavBuildingIds = new Map()"),
  "관심단지별 상세 건물 ID 캐시가 없습니다.");
expect(main.includes("serverFavBuildingIds.set(key, buildingId)"),
  "로그인 관심단지 응답의 building_id를 캐시하지 않습니다.");
expect(main.includes("const knownBuildingId = serverFavBuildingIds.get(key)"),
  "관심단지 칩이 저장된 건물 ID를 우선 사용하지 않습니다.");
expect(main.includes("openBuildingDetail(knownBuildingId)"),
  "관심단지 칩의 상세 이동 연결이 없습니다.");

const favoriteChipStart = main.indexOf("function createFavChip");
const favoriteChipEnd = main.indexOf("\nfunction openFavOverflowPopover", favoriteChipStart);
expect(favoriteChipStart >= 0 && favoriteChipEnd > favoriteChipStart,
  "관심단지 칩 생성 함수를 찾지 못했습니다.");
const favoriteChipSource = main.slice(favoriteChipStart, favoriteChipEnd);
const favoriteClicked = [];
function fakeElement() {
  return {
    children: [],
    handlers: {},
    appendChild(child) { this.children.push(child); },
    addEventListener(type, handler) { this.handlers[type] = handler; },
    setAttribute() {},
  };
}
const favoriteContext = {
  document: { createElement: fakeElement },
  state: { favKey: null },
  serverFavBuildingIds: new Map([
    ["신라모노그램 강릉|강원특별자치도 강릉시 해안로 210", 2657],
    ["가재와곰펜션|강원특별자치도 평창군 흥정계곡4길 212-27", 14387],
    ["가람초연재|경상북도 안동시 풍천면 하회종가길 76-6", 154332],
  ]),
  closeFavOverflowPopover() {},
  openBuildingDetail(id) { favoriteClicked.push(id); },
  removeFav() {},
};
vm.createContext(favoriteContext);
vm.runInContext(`${favoriteChipSource}\n`, favoriteContext);
for (const key of [
  "신라모노그램 강릉|강원특별자치도 강릉시 해안로 210",
  "가재와곰펜션|강원특별자치도 평창군 흥정계곡4길 212-27",
  "가람초연재|경상북도 안동시 풍천면 하회종가길 76-6",
]) {
  const chip = favoriteContext.createFavChip(key);
  chip.children[0].handlers.click();
}
expect(favoriteClicked.join(",") === "2657,14387,154332",
  "관심단지 칩 전체가 저장된 건물 상세로 이동하지 않습니다.");

const recentStart = main.indexOf("function renderRecentChips");
const recentEnd = main.indexOf("\n// ── 데이터랩", recentStart);
expect(recentStart >= 0 && recentEnd > recentStart, "최근검색 렌더링 함수를 찾지 못했습니다.");
const recentSource = main.slice(recentStart, recentEnd);
expect(recentSource.includes("onclick=\"openBuildingDetail(${Number(b.id)}); return false;\""),
  "최근검색 칩이 건물 상세 이동을 사용하지 않습니다.");

const clicked = [];
const recentRow = { style: {} };
const recentChips = { innerHTML: "" };
const context = {
  Number,
  Date,
  JSON,
  localStorage: {
    getItem: () => JSON.stringify([
      { id: 2657, name: "신라모노그램 강릉", viewed_at: 2 },
      { id: 14387, name: "가재와곰펜션", viewed_at: 1 },
    ]),
  },
  document: {
    getElementById(id) {
      if (id === "recentRow") return recentRow;
      if (id === "recentChips") return recentChips;
      return null;
    },
  },
  escapeHtml: (value) => String(value),
};
context.openBuildingDetail = (id) => clicked.push(id);
vm.createContext(context);
vm.runInContext(`const HS_RECENT_KEY = "hs_recent_buildings"; const HS_RECENT_MAX = 5;\n${recentSource}\nrenderRecentChips();`, context);
const html = recentChips.innerHTML;
expect(html.includes("openBuildingDetail(2657)") && html.includes("openBuildingDetail(14387)"),
  "최근검색 건물 전체가 상세 이동 링크로 렌더링되지 않습니다.");

console.log("OK  관심단지 전체·최근검색 건물 상세 이동 연결");