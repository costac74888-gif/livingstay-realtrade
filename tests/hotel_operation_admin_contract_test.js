const fs = require("fs");

function expect(ok, message) {
  if (!ok) throw new Error(message);
}

const admin = fs.readFileSync("static/admin.html", "utf8");
expect(admin.includes("연간 호텔업 운영현황 ZIP · 운영분석 비교자료"), "운영관리자에 운영현황 ZIP 영역이 없습니다.");
expect(admin.includes('id="hotelOperationArchiveFile"'), "운영현황 ZIP 첨부 버튼이 없습니다.");
expect(admin.includes('accept=".zip,application/zip"'), "ZIP 파일만 선택하도록 제한하지 않았습니다.");
expect(admin.includes("ZIP 검사·자동 해제·서비스 적용"), "ZIP 자동 해제·적용 버튼이 없습니다.");
expect(admin.includes("/api/admin/hotel-operation/apply"), "운영현황 적용 API가 연결되지 않았습니다.");
expect(admin.includes("/api/admin/hotel-operation/status"), "현재 적용 현황 API가 연결되지 않았습니다.");
expect(admin.includes("가장 최신 기준연도를 서비스에서 사용"), "연도별 자료 보존 안내가 없습니다.");

console.log("hotel operation admin contract checks passed");