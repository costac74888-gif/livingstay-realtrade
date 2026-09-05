const fs = require("fs");
const admin = fs.readFileSync("static/admin.html", "utf8");
const app = fs.readFileSync("app.py", "utf8");
const worker = fs.readFileSync("backfill_gocamping_web.py", "utf8");
function expect(condition, message) {
  if (!condition) throw new Error(message);
}
for (const id of [
  "gocampingWebBackfillStatus",
  "gocampingWebDryRunBtn",
  "gocampingWebRunBtn",
  "gocampingWebRetryBtn",
  "gocampingWebRefreshBtn"
]) {
  expect(admin.includes(`id="${id}"`), `관리자 컨트롤 누락: ${id}`);
}
expect(admin.includes("setInterval(loadGocampingWebBackfillStatus, 5000)"), "5초 상태 폴링 누락");
expect(app.includes("/api/admin/gocamping-web-backfill-status"), "상태 API 누락");
expect(app.includes("/api/admin/gocamping-web-backfill"), "실행 API 누락");
expect(app.includes("start_new_session=True"), "detached 실행 누락");
expect(worker.includes("--status-key") && worker.includes("--run-id"), "worker fencing 인자 누락");
expect(worker.includes("실행 소유권이 변경되어 중단"), "run ID fencing 누락");
expect(worker.includes("gocamping_records"), "전체 웹 원본 저장 누락");
console.log("OK gocamping web admin contract");