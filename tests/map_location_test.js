const fs = require("fs");

const source = fs.readFileSync("static/js/main.js", "utf8");
const css = fs.readFileSync("static/css/main.css", "utf8");

function expect(condition, message) {
  if (!condition) {
    console.error("FAIL", message);
    process.exit(1);
  }
}

expect(
  source.includes('window.matchMedia("(max-width: 980px)").matches') &&
    source.includes('history.pushState({}, "", "/")') &&
    source.includes("restoreDefaultPanel();") &&
    source.includes("closeMapSearchbar();"),
  "모바일 지도위치 클릭 시 상세·검색 패널을 함께 닫는 동작이 없습니다.",
);
expect(
  source.includes("const targetBuildingId = Number(b.building_id ?? id)") &&
    source.includes("showMapLocationTargetPoint(targetBuildingId, b.lat, b.lng)") &&
    source.includes("new kakao.maps.CustomOverlay") &&
    source.includes("requestAnimationFrame(() => {") &&
    source.includes("Promise.resolve(updateMapForZoom({ building_id: targetBuildingId }, { force: true })).then("),
  "지도 이동·마커 재렌더 뒤 지도위치 전용 원형 포인트를 다시 보장하지 않습니다.",
);
expect(
  css.includes(".map-location-target-pin") &&
    css.includes("map-location-target-pulse") &&
    css.includes("map-location-target-ring"),
  "지도위치 포인트 점멸 스타일이 없습니다.",
);

console.log("OK  모바일 지도위치 상세 닫기·점멸 포인트");