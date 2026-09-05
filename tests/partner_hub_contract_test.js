const assert = require("node:assert/strict");
const fs = require("node:fs");

const partner = fs.readFileSync("static/partner.html", "utf8");

for (const label of ["운영자", "중개사", "운영지원", "대출상담사", "분양자"]) {
  assert.match(partner, new RegExp(`partner-cat-title">${label}<`));
}
assert.match(partner, /class="partner-main-grid"/);
assert.match(partner, /href="#operator-guide"/);
assert.match(partner, /id="operator-guide"/);
assert.match(partner, /href="\/agents"/);
assert.match(partner, /href="\/operators"/);
assert.match(partner, /href="\/loan-partners"/);
assert.match(partner, /href="\/apply\/presale"/);
assert.match(partner, /href="\/apply\/lodging-operator\?type=\$\{key\}"/);

console.log("partner hub contract: ok");