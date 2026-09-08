const fs = require("fs");

const source = fs.readFileSync("static/js/format_util.js", "utf8");
const index = fs.readFileSync("static/index.html", "utf8");

const expected = {
  생활: "#1769AA",
  관광: "#008577",
  일반: "#B83E7D",
  에어비앤비: "#D9363E",
  농어촌민박: "#5F8F22",
  캠핑: "#5D4037",
  한옥: "#C96A00",
  복합: "#8068B3",
  준공전: "#C62828",
  미분류: "#66717D",
};

for (const [label, color] of Object.entries(expected)) {
  if (!source.includes(`"${label}": "${color}"`)) {
    throw new Error(`${label} 마커의 진한 색상 ${color}이 없습니다.`);
  }
  if (!index.includes(
    `data-lodging-type="${label}" style="cursor:pointer;"`,
  ) || !index.includes(`<i style="background:${color};"></i>`)) {
    throw new Error(`${label} 지도 범례 색상이 마커와 일치하지 않습니다.`);
  }
}

console.log("map marker color contrast checks passed");