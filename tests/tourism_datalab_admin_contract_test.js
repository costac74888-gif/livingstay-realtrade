const fs = require("fs");
const html = fs.readFileSync("static/admin.html", "utf8");
for (const text of [
  "관광 데이터랩 갱신",
  "/api/admin/tourism-datalab/preview",
  "/api/admin/tourism-datalab/apply",
  "datalab.visitkorea.or.kr",
  "tourismDatalabApply",
  "apply.disabled",
  "response status",
  "response.ok",
  "response.status === 401",
  "<table class=\"dg-table\""
]) {
  if (!html.includes(text)) throw new Error(`missing Data Lab admin UI: ${text}`);
}
console.log("tourism Data Lab admin UI contract passed");