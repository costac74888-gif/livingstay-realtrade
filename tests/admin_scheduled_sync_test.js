const fs = require("fs");

const app = fs.readFileSync("app.py", "utf8");
const admin = fs.readFileSync("static/admin.html", "utf8");
const repl = fs.readFileSync(".replit", "utf8");

function expect(condition, message) {
  if (!condition) {
    console.error("FAIL", message);
    process.exit(1);
  }
}

expect(
  app.includes('@app.route("/api/admin/scheduled-sync-status")') &&
    app.includes('@app.route("/api/admin/scheduled-sync/retry", methods=["POST"])') &&
    app.includes('@app.route("/api/admin/scheduled-sync/run", methods=["POST"])') &&
    app.includes("_claim_scheduled_sync_start"),
  "통합 동기화 상태·재시도 API가 없습니다.",
);

expect(
  admin.includes('id="dsSecScheduled"') &&
    admin.includes('id="scheduledSyncStages"') &&
    admin.includes("실패·중단 단계 재시도") &&
    admin.includes("지금 수집") &&
    admin.includes("Scheduled Deployment") &&
    admin.includes('id="manualSyncDetails"'),
  "관리자 통합 동기화 카드 또는 수동 보완 접기 영역이 없습니다.",
);

expect(
  repl.includes('name = "정기 API 통합 동기화"') &&
    repl.includes("--skip-stage transactions --skip-stage rural --skip-stage hanok") &&
    repl.includes('name = "최근 실거래 자동 동기화"') &&
    repl.includes('name = "농어촌민박 자동 동기화"') &&
    repl.includes('name = "한옥체험업 자동 동기화"'),
  "실거래·농어촌민박·한옥 독립 예약 워크플로가 없습니다.",
);

const projectBlock = repl.slice(
  repl.indexOf('name = "Project"'),
  repl.indexOf('name = "Start application"'),
);
expect(
  !projectBlock.includes('args = "Fast Sync"') &&
    !projectBlock.includes('args = "Merge Dev→Prod (실제반영)"') &&
    !projectBlock.includes('args = "Backfill General Lodging"'),
  "기본 Project 실행에 운영 데이터 작업이 남아 있습니다.",
);

console.log("OK  관리자 정기 API 통합 동기화 구성");