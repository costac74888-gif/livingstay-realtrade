const fs = require("fs");
const html = fs.readFileSync("static/admin.html", "utf8");
for (const text of [
  "관광 데이터랩 갱신",
  "/api/admin/tourism-datalab/preview",
  "/api/admin/tourism-datalab/apply",
  "datalab.visitkorea.or.kr",
  "tourismDatalabApply",
  "CSV 파일 추가 · 안전 미리보기",
  "상세주소 CSV는 1~100위와 도로명주소 100개",
  "운영 DB 반영 예정",
  "관광 데이터랩 원본",
  "/api/admin/tourism-datalab/collections",
  "모든 수집처",
  "업데이트 예정일",
  "운영 DB와 실제 홈페이지",
  "apply.disabled",
  "response status",
  "response.ok",
  "response.status === 401",
  "<table class=\"dg-table\""
]) {
  if (!html.includes(text)) throw new Error(`missing Data Lab admin UI: ${text}`);
}
console.log("tourism Data Lab admin UI contract passed");