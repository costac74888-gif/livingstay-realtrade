"use strict";

const fs = require("fs");

const app = fs.readFileSync("app.py", "utf8");
const admin = fs.readFileSync("static/admin.html", "utf8");
const grid = fs.readFileSync("static/js/admin.js", "utf8");

function expect(condition, message) {
  if (!condition) throw new Error(message);
}

expect(
  app.includes('elif lt_filter in PRIMARY_LODGING_TYPES + ("복합",):'),
  "관리자 건물 용도 필터가 공통 법정분류 전체를 허용하지 않습니다.",
);
expect(
  app.includes('it["display_building_name"]') &&
    app.includes('it["building_name_report_display"]'),
  "활성 영업신고 상호의 관리자 대표 표시가 없습니다.",
);
expect(
  app.includes('it["lodging_room_known"] = bool(deduplicated_active_lodgings) and all('),
  "다중 활성 신고의 객실 수가 일부 누락돼도 정확한 합계로 표시될 수 있습니다.",
);
expect(
  admin.includes('row.display_building_name || v') &&
    admin.includes("영업신고 기준") &&
    admin.includes(">객실수</th>") &&
    admin.includes(">사이트수</th>") &&
    admin.includes("시설규모(㎡)") &&
    admin.includes(">영업상태</th>") &&
    admin.includes("업종·시설유형") &&
    admin.includes("원본 출처") &&
    admin.includes('colspan="14"') &&
    admin.includes('const roomInfo = lr.room_count != null') &&
    admin.includes('const siteInfo = lr.camping_site_count != null') &&
    admin.includes(">미확인</span>"),
  "관리자 영업사업장 공통 14개 컬럼 표시가 없습니다.",
);
expect(
  app.includes('"camping_site_count": lr.get("camping_site_count")') &&
    app.includes('"source_label":      _admin_lodging_source_label') &&
    app.includes('return "고캠핑 API" if permit.count(":") == 1 else "정부 야영장 CSV"'),
  "관리자 영업사업장 응답에 사이트수 또는 원본 출처가 없습니다.",
);
expect(
  grid.includes("new AbortController()") &&
    grid.includes("this._reloadController.abort()") &&
    grid.includes('this._bodyMessage("불러오는 중…")') &&
    grid.includes("requestSeq !== this._reloadSeq"),
  "빠른 필터 전환의 이전 요청 취소 또는 로딩 상태가 없습니다.",
);

console.log("OK  관리자 법정분류 필터·신고명·객실 미확인·요청 경합 점검");