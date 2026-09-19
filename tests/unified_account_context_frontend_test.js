const assert = require("node:assert/strict");
const fs = require("node:fs");

const auth = fs.readFileSync("static/js/auth.js", "utf8");
const header = fs.readFileSync("static/js/header.js", "utf8");
const mypage = fs.readFileSync("static/mypage.html", "utf8");
const css = fs.readFileSync("static/css/main.css", "utf8");

for (const label of ["일반회원", "중개사", "숙박 운영자", "운영지원업체", "대출상담사"]) {
  assert.match(auth, new RegExp(label));
}
assert.match(auth, /\/api\/auth\/context/);
assert.match(auth, /general: "일반회원"/);
assert.match(auth, /payload\.business_table/);
assert.match(auth, /contexts \|\| d\.available_contexts \|\| d\.available_roles/);
assert.match(auth, /contexts\.length < 2/);
assert.match(auth, /aria-label="사용 역할과 사업장 선택"/);
assert.match(mypage, /mypageContextBox/);
assert.match(mypage, /legacyRoleLinkBox/);
assert.match(mypage, /\/api\/auth\/link-legacy-role/);
assert.match(mypage, /withdrawCurrentPassword/);
assert.match(mypage, /contexts\.length <= 1/);
assert.match(css, /\.auth-context-switcher/);
assert.match(css, /\.header-menu \.auth-context-switcher/);
assert.match(header, /id="authArea"/);

console.log("unified account context frontend contract: ok");