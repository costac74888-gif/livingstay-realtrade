const fs = require("fs");

const admin = fs.readFileSync("static/admin.html", "utf8");
const app = fs.readFileSync("app.py", "utf8");
const css = fs.readFileSync("static/css/main.css", "utf8");
function expect(ok, message) { if (!ok) throw new Error(message); }

expect(admin.includes('data-agency-move="${row.id}"'), "유관기관 순서 이동 버튼이 없습니다.");
expect(admin.includes('aria-label="${dgEscape(row.name)} 위로 이동"'), "위로 이동 버튼의 접근성 설명이 없습니다.");
expect(admin.includes('aria-label="${dgEscape(row.name)} 아래로 이동"'), "아래로 이동 버튼의 접근성 설명이 없습니다.");
expect(admin.includes('fetch("/api/admin/agency-links/reorder"'), "유관기관 순서 저장 요청이 없습니다.");
expect(admin.includes("[ordered[index], ordered[nextIndex]]"), "목록 순서를 교환하는 처리가 없습니다.");
expect(app.includes('@app.route("/api/admin/agency-links/reorder", methods=["POST"])'), "유관기관 순서 저장 API가 없습니다.");
expect(css.includes(".map-agency-row img{height:26px;max-width:168px"), "PC 유관기관 로고가 기존 크기의 2배가 아닙니다.");
expect(css.includes(".map-agency-slide{min-width:0;width:calc(100vw - 56px)") && css.includes(".map-agency-row{flex-wrap:nowrap;overflow-x:auto;overflow-y:hidden") && css.includes(".map-agency-row a{flex:0 0 auto") && css.includes("height:clamp(22px, 7vw, 30px)"), "모바일 유관기관 로고가 한 줄에서 크게 표시되도록 고정되지 않았습니다.");
expect(app.includes("SELECT id FROM agency_links FOR UPDATE"), "동시 변경으로부터 순서 저장을 보호하지 않습니다.");
expect(app.includes("set(ordered_ids) != current_ids"), "오래된 목록으로 순서를 덮어쓰는 것을 차단하지 않습니다.");

console.log("OK  유관기관 순서 변경 회귀 점검");