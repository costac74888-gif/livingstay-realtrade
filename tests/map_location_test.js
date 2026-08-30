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
    source.includes("restoreDefaultPanel();"),
  "모바일 지도위치 클릭 시 상세 패널을 닫는 동작이 없습니다.",
);
expect(
  source.includes("showMapLocationTargetPoint(b.id, b.lat, b.lng)") &&
    source.includes("new kakao.maps.CustomOverlay"),
  "지도위치 전용 원형 포인트가 없습니다.",
);
expect(
  css.includes(".map-location-target-pin") &&
    css.includes("map-location-target-pulse"),
  "지도위치 포인트 점멸 스타일이 없습니다.",
);

console.log("OK  모바일 지도위치 상세 닫기·점멸 포인트");