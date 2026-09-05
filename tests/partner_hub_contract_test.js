const assert = require("node:assert/strict");
const fs = require("node:fs");

const partner = fs.readFileSync("static/partner.html", "utf8");

for (const label of ["운영자", "중개사", "운영지원", "대출상담사", "분양자"]) {
  assert.match(partner, new RegExp(`partner-cat-title">${label}<`));
}
for (const icon of ["🛎️", "🤝", "🧰", "💰", "🏗️", "🏠", "⛺", "🌾", "🏯", "🏢"]) {
  assert.ok(partner.includes(icon), `${icon} 분야 아이콘이 없습니다.`);
}
assert.match(partner, /class="partner-main-grid"/);
assert.match(partner, /href="#operator-guide"/);
assert.match(partner, /id="operator-guide"/);
assert.match(partner, /href="\/apply\/agent"/);
assert.match(partner, /href="\/apply\/operator"/);
assert.match(partner, /href="\/apply\/loan"/);
assert.match(partner, /href="\/apply\/presale"/);
assert.match(partner, /href="\/apply\/lodging-operator\?type=\$\{key\}"/);
assert.match(partner, /params\.get\("building_id"\)/);
assert.match(partner, /\/apply\/agent\?\$\{query\}/);
assert.match(partner, /\/apply\/operator\?\$\{query\}/);
assert.match(partner, /\/apply\/loan\?\$\{query\}/);
assert.match(partner, /\/apply\/presale\?building_id=/);
assert.ok(
  partner.indexOf('applyContext("");') < partner.indexOf('fetch(`/api/buildings/${encodeURIComponent(id)}/brief`)'),
  "상세 진입의 건물 ID는 건물명 조회 전에 링크에 반영되어야 합니다."
);

console.log("partner hub contract: ok");