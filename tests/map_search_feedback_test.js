"use strict";

// 지도 검색 결과의 두 가지 사용자 안내가 빠지거나 전국 배지를 다시 호출하지 않는지
// main.js의 실제 구현 구간을 기준으로 확인한다.
const fs = require("fs");

const main = fs.readFileSync("static/js/main.js", "utf8");
function expect(condition, message) {
  if (!condition) throw new Error(message);
}

const mapMarkerSection = main.slice(
  main.indexOf("async function loadMapMarkers"),
  main.indexOf("// 현재 지도 줌 레벨로 클러스터 모드를 결정"),
);
const zoomSection = main.slice(
  main.indexOf("async function updateMapForZoom"),
  main.indexOf("async function initMap"),
);

expect(
  main.includes('function showMapEmptyBanner(msg = "이 지역은 아직 등록된 매물이 없어요")'),
  "검색 결과 없음 배너 함수가 없습니다.",
);
expect(
  zoomSection.includes("const hasRegionFilter = !!(fallback.si_do || fallback.sgg_nm || fallback.umd_nm);") &&
  zoomSection.includes('loadClusterOverlays("umd", fallback);') &&
  zoomSection.includes('showMapEmptyBanner("검색 결과가 없습니다. 건물명을 다시 확인해주세요.");'),
  "q 검색 0건에서 지역 필터 유무에 따른 폴백 분기가 없습니다.",
);
expect(
  mapMarkerSection.includes("if (placed === 1 && filters.q && validItems[0]?.building_name)") &&
  mapMarkerSection.includes("matchedName && searchedName !== matchedName") &&
  mapMarkerSection.includes("정확히 일치하는 건물은 없어"),
  "단일 부분일치 결과 안내 토스트가 없습니다.",
);

console.log("OK  지도 검색 0건 전국 배지 방지·부분일치 안내 토스트");