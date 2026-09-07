const fs = require("fs");

const main = fs.readFileSync("static/js/main.js", "utf8");
const css = fs.readFileSync("static/css/main.css", "utf8");

function expect(ok, message) {
  if (!ok) throw new Error(message);
}

expect(
  main.includes('el.className = "map-building-dot"')
    && main.includes('el.dataset.label = b.building_name || "건물"')
    && main.includes('((filters.q || filters.building_id) ? " is-emphasized" : "")')
    && main.includes("zIndex: (filters.q || filters.building_id) ? 25 : 12"),
  "거래가 없는 숙박건물의 가시성 또는 검색 강조가 없습니다.",
);

expect(
  css.includes(".map-building-dot{")
    && css.includes("width:20px;height:20px")
    && css.includes(".map-building-dot:hover::after")
    && css.includes("content:attr(data-label)")
    && css.includes(".map-building-dot.is-emphasized{width:28px;height:28px"),
  "숙박건물 마커의 외곽선·건물명 도움말·검색 강조 스타일이 없습니다.",
);

console.log("map zero-activity marker checks passed");