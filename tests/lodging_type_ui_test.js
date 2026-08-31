const fs = require("fs");
const vm = require("vm");

function expect(condition, message) {
  if (!condition) throw new Error(message);
}

const context = { window: {} };
vm.createContext(context);
vm.runInContext(fs.readFileSync("static/js/format_util.js", "utf8"), context);

const lodging = context.window.LodgingTypes;
const expectedTypes = [
  "생활", "관광", "일반", "에어비앤비", "농어촌민박",
  "캠핑", "한옥", "복합", "준공전", "미분류",
];

expect(lodging, "공통 법정 숙박분류 유틸이 노출되지 않았습니다.");
expect(
  JSON.stringify(Array.from(lodging.order)) === JSON.stringify(expectedTypes),
  "공통 법정 숙박분류 순서가 기준과 다릅니다.",
);

for (const type of expectedTypes) {
  expect(lodging.colors[type], `${type} 색상이 없습니다.`);
  expect(lodging.labels[type], `${type} 표시명이 없습니다.`);
}

expect(lodging.normalize("관광·일반") === "복합", "복합 분류를 정규화하지 못했습니다.");
expect(lodging.normalize("호텔") === "관광", "이전 호텔 값을 관광으로 호환 표시하지 못했습니다.");
expect(lodging.normalize("콘도") === "관광", "이전 콘도 값을 관광으로 호환 표시하지 못했습니다.");
expect(lodging.normalize("", "착공") === "준공전", "착공 건물의 준공전 표시가 깨졌습니다.");
expect(lodging.badge("", null, "허가") === "준공전", "허가 건물의 준공전 배지가 깨졌습니다.");
expect(lodging.color("", "착공") === lodging.colors["준공전"], "착공 건물의 준공전 색상이 깨졌습니다.");
expect(lodging.badge("생활") === "생숙", "생활 분류 약칭이 깨졌습니다.");
expect(lodging.badge("에어비앤비") === "에어비앤비", "에어비앤비 배지가 깨졌습니다.");
expect(
  lodging.badge("캠핑", "자동차야영") === "캠핑·야영(자동차야영)",
  "자동차야영 하위 용도 배지가 깨졌습니다.",
);

for (const page of ["static/index.html", "static/transactions.html", "static/listings.html"]) {
  const html = fs.readFileSync(page, "utf8");
  for (const type of expectedTypes) {
    expect(
      html.includes(`<option value="${type}"`),
      `${page} 용도 필터에 ${type} 옵션이 없습니다.`,
    );
  }
  expect(
    html.includes('<option value="자동차야영"'),
    `${page} 용도 필터에 자동차야영 하위 옵션이 없습니다.`,
  );
}

const sharedBadgePages = [
  "static/building.html",
  "static/agent_dashboard.html",
  "static/agent_profile.html",
  "static/operator_dashboard.html",
  "static/operator_profile.html",
  "static/loan_consultant_dashboard.html",
  "static/loan_consultant_profile.html",
];
for (const page of sharedBadgePages) {
  const html = fs.readFileSync(page, "utf8");
  expect(html.includes("window.LodgingTypes.color"), `${page}가 공통 분류 색상을 사용하지 않습니다.`);
  expect(html.includes("window.LodgingTypes.badge"), `${page}가 공통 분류 배지를 사용하지 않습니다.`);
  expect(
    /markerColor\(b\.lodging_type,\s*b\.building_status\)/.test(html),
    `${page}가 건물 상태를 공통 분류 색상에 전달하지 않습니다.`,
  );
  expect(
    /badgeLabel\(b\.lodging_type,[^)]*b\.building_status\)/.test(html),
    `${page}가 건물 상태를 공통 분류 배지에 전달하지 않습니다.`,
  );
}

const mainJs = fs.readFileSync("static/js/main.js", "utf8");
expect(
  mainJs.includes("lodgingLabelKo(b.lodging_type, b.building_status)"),
  "지도 정보창 분류명에 건물 상태가 전달되지 않습니다.",
);
expect(
  mainJs.includes("markerColor(b.lodging_type, b.building_status)"),
  "지도 마커 분류색에 건물 상태가 전달되지 않습니다.",
);

const appPy = fs.readFileSync("app.py", "utf8");
for (const endpoint of [
  "agent_public_profile",
  "_agent_me_data",
  "operator_public_profile",
  "operator_me",
  "loan_consultant_public_profile",
  "loan_consultant_me",
]) {
  const start = appPy.indexOf(`def ${endpoint}(`);
  const next = appPy.indexOf("\ndef ", start + 1);
  const source = appPy.slice(start, next < 0 ? undefined : next);
  expect(start >= 0, `${endpoint} API를 찾을 수 없습니다.`);
  expect(
    source.includes("mb.lodging_subtype"),
    `${endpoint} API가 자동차야영 하위 용도를 응답하지 않습니다.`,
  );
}

for (const page of ["static/index.html", "static/listings.html", "static/mypage.html"]) {
  const html = fs.readFileSync(page, "utf8");
  const utilPos = html.indexOf("/static/js/format_util.js");
  const modalPos = html.indexOf("/static/js/listing_modal.js");
  expect(utilPos >= 0 && modalPos >= 0 && utilPos < modalPos, `${page}의 공통 유틸 로딩 순서가 잘못됐습니다.`);
}

console.log("lodging type UI checks passed");