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
  app.includes('@app.route("/api/admin/lodging-source-overview")') &&
    app.includes('@app.route("/api/admin/lodging-import/preview", methods=["POST"])') &&
    app.includes('@app.route("/api/admin/lodging-import/<token>/apply", methods=["POST"])') &&
    admin.includes('id="lodgingSourceCards"') &&
    admin.includes('id="lodgingImportPreviewBtn"') &&
    admin.includes("승인 반영"),
  "숙박 원본별 현황·수동 실행 또는 파일 미리보기·승인 기능이 없습니다.",
);

expect(
  admin.includes('id="dsBoard"') &&
    admin.includes("function renderDataSyncBoardRow(row)") &&
    admin.includes("function runDataSyncBoardAction(row)") &&
    admin.includes("function startDataSyncBoardUpdates()") &&
    admin.includes("row.last_error_summary") &&
    admin.includes("row.today_calls") &&
    admin.includes("row.daily_limit") &&
    admin.includes("row.last_success_at") &&
    admin.includes("dataSyncBoardBusy.has") &&
    admin.includes('"/api/admin/datasync-board/action"') &&
    admin.includes("실패·오래됨·일시중단") &&
    admin.includes("다시 실행") &&
    ["is-done","is-running","is-waiting","is-stale","is-failed","is-paused","is-unknown"]
      .every(state => admin.includes(state)),
  "현재 통합 동기화 보드의 상태·한도·최근 오류·중복 실행 방지·재실행 기능이 없습니다.",
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
    !projectBlock.includes('args = "Backfill Retry"') &&
    !projectBlock.includes('args = "Fill PK"') &&
    !projectBlock.includes('args = "Merge Dev→Prod (실제반영)"') &&
    !projectBlock.includes('args = "Backfill General Lodging"') &&
    !projectBlock.includes('args = "정기 API 통합 동기화"'),
  "기본 Project 실행에 운영 데이터 작업이 남아 있습니다.",
);

console.log("OK  관리자 정기 API 통합 동기화 구성");