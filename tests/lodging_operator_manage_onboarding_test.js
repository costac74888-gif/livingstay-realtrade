const fs = require("fs");

const manage = fs.readFileSync("static/lodging_operator_manage.html", "utf8");
const apply = fs.readFileSync("static/apply_lodging_operator.html", "utf8");
function expect(ok, message) { if (!ok) throw new Error(message); }

expect(manage.includes('id="applyAction" hidden'), "미승인 운영자의 등록 신청 영역이 없습니다.");
expect(manage.includes('id="applyLink"') && manage.includes("운영자 등록 신청"), "운영자 등록 신청 버튼이 없습니다.");
expect(manage.includes("applyAction.hidden=false"), "운영자 관리 접근 실패 후 등록 신청 버튼이 표시되지 않습니다.");
expect(manage.includes("allowedTypes.has(requestedType)"), "허용된 숙박 유형만 신청 화면에 전달하지 않습니다.");
expect(manage.includes("`/apply/lodging-operator?type=${requestedType}`"), "운영자 등록 신청 링크에 숙박 유형이 전달되지 않습니다.");
expect(apply.includes("<title>운영자등록 | 홈앤스테이</title>"), "운영자 등록 화면의 문서 제목이 올바르지 않습니다.");
expect(apply.includes(">운영자등록</h1>"), "운영자 등록 화면의 제목이 올바르지 않습니다.");

console.log("OK  미승인 숙박 운영자 등록 안내 회귀 점검");