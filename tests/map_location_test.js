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
  source.includes('id="bMapBtn" class="b-map-return-btn"') &&
    source.includes("const targetBuildingId = Number(b.building_id ?? id)") &&
    source.includes('history.pushState({}, "", "/")') &&
    source.includes("restoreDefaultPanel();") &&
    source.includes("closeMapSearchbar();") &&
    source.includes("setMapLocationTarget(targetBuildingId)") &&
    source.includes("kakaoMap.setLevel(3)") &&
    source.includes("const locationMapFilters = Object.assign({}, mapFiltersFromState())") &&
    source.includes("Promise.resolve(updateMapForZoom(locationMapFilters, { force: true })).then(") &&
    source.includes("syncMapLocationTargetElement(d.el, d.b.id)") &&
    source.includes("_openBuildingFromMap(b)") &&
    source.includes("clickable: true") &&
    !source.includes("mapLocationTargetOverlay") &&
    !source.includes("showMapLocationTargetPoint"),
  "우편번호 줄 지도위치 버튼의 지도 복귀·확대·점멸 흐름이 맞지 않습니다.",
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

console.log("OK  우편번호 줄 지도위치 복귀·확대·점멸 흐름");