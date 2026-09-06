const fs = require("fs");

const admin = fs.readFileSync("static/admin.html", "utf8");

function expect(condition, message) {
  if (!condition) throw new Error(message);
}

const sectionIds = [
  "dsSecBrhub",
  "dsSecBackfillLodging",
  "dsSecGeo",
  "dsSecPhotos",
  "dsSecTitle",
  "dsSecZip",
  "dsSecTx",
  "dsSecTxBackfill",
  "dsSecBroker",
  "dsSecBrokerGeo",
  "dsSecRealty",
  "dsSecLodgingStaging",
  "dsSecCampingImages",
  "dsSecGocampingWeb",
  "dsSecLodging",
  "dsSecPermits",
  "dsSecReclassify",
  "dsSecClassificationProvenance",
  "dsSecStores",
  "dsSecPendingCompletion",
  "dsSecBackup",
];

for (const id of sectionIds) {
  expect(
    admin.includes(`id="${id}"`) && admin.includes(`${id}: [`),
    `동기화 섹션 ${id}의 실행 위치 안내가 누락되었습니다.`,
  );
}

expect(
  admin.includes('dsSecCampingImages: ["production"') &&
  admin.includes('dsSecGocampingWeb: ["production"') &&
  admin.includes('dsSecLodging: ["disabled"'),
  "캠핑·고캠핑·기존 숙박 동기화의 실행 환경 구분이 올바르지 않습니다.",
);

expect(
  admin.includes('scope === "production"\n          ? "운영 관리자에서 실행"') &&
  admin.includes('scope === "development"\n            ? "개발 관리자에서만 실행"') &&
  admin.includes(': "사용 중지 · 비상 복구 전용"'),
  "운영·개발·사용 중지 실행 위치 문구가 없습니다.",
);

console.log("OK  데이터 동기화 버튼 실행 위치 구분");