const fs = require("fs");

const app = fs.readFileSync("app.py", "utf8");
const admin = fs.readFileSync("static/admin.html", "utf8");

function expect(condition, message) {
  if (!condition) {
    console.error("FAIL", message);
    process.exit(1);
  }
}

expect(
  admin.includes('id="campingImageBackfillRunBtn"') &&
    admin.includes("캠핑 다중사진 이어서 수집") &&
    admin.includes("하루 800회 호출 한도") &&
    admin.includes("체크포인트"),
  "캠핑 다중사진 재개 수집 카드가 없습니다.",
);
expect(
  admin.includes('"/api/admin/camping-image-backfill-status"') &&
    admin.includes('"/api/admin/camping-image-backfill"') &&
    admin.includes("res.status === 401") &&
    admin.includes("res.status === 409") &&
    admin.includes("Number(d.calls_today) >= 800") &&
    admin.includes("remaining_count"),
  "캠핑 이미지 백필 상태/오류 처리 계약이 없습니다.",
);
expect(
  app.includes('"state": state') &&
    app.includes('"updated", "skipped", "failed"') &&
    app.includes('"calls_today": calls_today'),
  "캠핑 이미지 백필 상태 응답 계약이 없습니다.",
);
console.log("OK  캠핑 다중사진 재개 수집 관리자 계약");