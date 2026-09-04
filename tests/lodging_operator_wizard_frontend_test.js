const fs = require("fs");

const apply = fs.readFileSync("static/apply_lodging_operator.html", "utf8");
const manage = fs.readFileSync("static/lodging_operator_manage.html", "utf8");
const main = fs.readFileSync("static/js/main.js", "utf8");
const building = fs.readFileSync("static/building.html", "utf8");
const admin = fs.readFileSync("static/admin.html", "utf8");
function expect(ok, message) { if (!ok) throw new Error(message); }

["data-step=\"1\"", "data-step=\"2\"", "data-step=\"3\"", "data-step=\"4\"",
 "/api/buildings/${encodeURIComponent(buildingId)}/brief",
 "/api/apply/lodging-operator/phone-challenge",
 "/verify", "challenge_id:phoneToken", "/api/apply/lodging-operator/upload",
 "doc_biz_license_url", "doc_biz_reg_url", "빠른 검토 대상", "자동 승인되지는 않습니다."].forEach(text =>
  expect(apply.includes(text), `운영자 신청 마법사에 ${text} 처리가 없습니다.`)
);
expect(manage.includes("/api/lodging-operator/photos"), "운영자 사진 목록 API가 없습니다.");
expect(manage.includes("/photos/reorder") && manage.includes("photo_ids:photos.map") && manage.includes("/primary") && manage.includes("data-delete"),
  "사진 순서·대표·삭제 관리 기능이 없습니다.");
expect(main.includes('params.set("building_id"') && building.includes("building_id=${encodeURIComponent(buildingId)}"),
  "건물 상세 진입 등록 링크가 building_id를 전달하지 않습니다.");
expect(admin.includes('key: "lodging_operator"') && admin.includes("숙박시설 운영자"),
  "관리자 회원 그룹에 숙박시설 운영자가 없습니다.");
console.log("OK  숙박 운영자 마법사·갤러리·회원그룹 회귀 점검");