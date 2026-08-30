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
    source.includes("setMapLocationTarget(targetBuildingId)") &&
    source.includes("syncMapLocationTargetElement(d.el, d.b.id)") &&
    source.includes("_openBuildingFromMap(b)") &&
    source.includes("clickable: true") &&
    source.includes("const locationMapFilters = Object.assign({}, mapFiltersFromState())") &&
    source.includes("delete locationMapFilters.q") &&
    source.includes("Promise.resolve(updateMapForZoom(locationMapFilters, { force: true })).then(") &&
    !source.includes("updateMapForZoom({ building_id: targetBuildingId }") &&
    !source.includes("mapLocationTargetOverlay") &&
    !source.includes("showMapLocationTargetPoint"),
  "지도위치 이동 시 전체 포인트를 유지하면서 기존 건물 포인트 자체를 점멸시키지 않습니다.",
);
expect(
  css.includes(".map-location-target") &&
    css.includes("map-location-target-pulse") &&
    !css.includes(".map-location-target-pin") &&
    !css.includes("map-location-target-ring"),
  "기존 건물 포인트용 작은 점멸 스타일이 없습니다.",
);
expect(
  source.includes("const LABEL_MAX_LEVEL = 5") &&
    source.includes("const CLUSTER_UMD_MIN_LEVEL  = 6") &&
    source.includes('clusterLevel === "sgg" ? 7 : 5'),
  "개별 포인트 표시가 너무 이른 줌 레벨에서 시작하거나 클러스터 드릴다운이 맞지 않습니다.",
);

console.log("OK  모바일 지도위치 상세 닫기·점멸 포인트");