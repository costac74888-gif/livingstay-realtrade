const fs = require("fs");
const html = fs.readFileSync("static/admin.html", "utf8");
for (const text of [
  "관광 데이터랩 갱신",
  "/api/admin/tourism-datalab/preview",
  "/api/admin/tourism-datalab/apply",
  "datalab.visitkorea.or.kr",
  "tourismDatalabApply",
  "현재 조회·적용 대상:",
  "상세주소 CSV는 1~100위와 도로명주소 100개",
  "운영 DB 반영 예정",
  "관광 데이터랩 원본",
  "현재 목록: 운영 DB 원본 이력 · 적용 대상: 실제 홈페이지",
  "현재 목록: 개발 DB 원본 이력 · 적용 대상: 개발 검증 DB",
  "운영 DB·실제 홈페이지에 적용",
  "개발 DB에 적용(검증용)",
  "실제 홈페이지는 바뀌지 않습니다",
  "향후 정기 업데이트의 최종 반영은 이 운영 관리자 화면에서 합니다",
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