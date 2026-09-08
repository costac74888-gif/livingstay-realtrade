const fs = require("fs");

const main = fs.readFileSync("static/js/main.js", "utf8");
const css = fs.readFileSync("static/css/main.css", "utf8");

function expect(ok, message) {
  if (!ok) throw new Error(message);
}

expect(
  main.includes('class="operator-banner-cta"')
    && main.includes(">운영 파트너 등록</a>"),
  "운영 파트너 등록 버튼이 없습니다.",
);
expect(
  css.includes(
    ".operator-banner-cta{white-space:nowrap;text-align:center;max-width:none}",
  ),
  "모바일 운영 파트너 등록 버튼이 한 줄로 고정되지 않았습니다.",
);

console.log("operator partner CTA mobile checks passed");