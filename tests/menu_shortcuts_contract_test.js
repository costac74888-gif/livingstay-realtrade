const fs = require("fs");

const menu = fs.readFileSync("static/menu.html", "utf8");

function expect(ok, message) {
  if (!ok) throw new Error(message);
}

const orderedLabels = [
  "지도 홈",
  "내건물시세",
  "직거래매물",
  "실거래목록",
  "자산분석",
  "마이페이지",
  "알림",
  "채팅",
  "이용안내",
];

let previous = -1;
for (const label of orderedLabels) {
  const current = menu.indexOf(label);
  expect(current > previous, `바로가기 순서에서 '${label}' 위치가 올바르지 않습니다.`);
  previous = current;
}

expect(
  menu.includes('class="menu-shortcuts-grid"')
    && menu.includes("grid-template-columns:repeat(2")
    && menu.includes(".menu-link-guide {")
    && menu.includes("grid-column:1 / -1"),
  "모바일 바로가기가 2열 버튼과 전체 폭 이용안내로 구성되지 않았습니다.",
);

expect(
  menu.includes('id="menuAdminAnalysis" href="/analysis" style="display:none;"')
    && menu.includes('fetch("/api/admin/menu-access"')
    && menu.includes("data.is_admin")
    && menu.includes('analysisLink.style.removeProperty("display")'),
  "자산분석 바로가기가 운영관리자 확인 전 노출됩니다.",
);

console.log("menu shortcut layout checks passed");