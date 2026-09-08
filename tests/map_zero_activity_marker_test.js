const fs = require("fs");

const main = fs.readFileSync("static/js/main.js", "utf8");
const css = fs.readFileSync("static/css/main.css", "utf8");

function expect(ok, message) {
  if (!ok) throw new Error(message);
}

expect(
  main.includes("`width:14px;height:14px;padding:0;border:2px solid #fff")
    && main.includes("clickable: true, zIndex: 5")
    && !main.includes('el.className = "map-building-dot"'),
  "거래가 없는 숙박건물이 기존의 작은 점 마커로 표시되지 않습니다.",
);

expect(
  !css.includes(".map-building-dot{")
    && !css.includes(".map-building-dot.is-emphasized"),
  "숙박건물의 이중 원형 또는 확대 강조 스타일이 남아 있습니다.",
);

console.log("map zero-activity marker checks passed");