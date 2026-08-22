// 매물등록 모달의 등록자유형 순서·프리셋·건물상세 버튼 회귀 테스트.
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const modal = fs.readFileSync(path.join(root, "static/js/listing_modal.js"), "utf8");
const main = fs.readFileSync(path.join(root, "static/js/main.js"), "utf8");

function expect(condition, message) {
  if (!condition) throw new Error(message);
}

const modeAt = modal.indexOf('id="lrModeSection"');
const registrantAt = modal.indexOf('id="lrRegistrantType"');
const dealAt = modal.indexOf('id="lrDealButtons"');
const detailAt = modal.indexOf("상세 정보");
expect(modeAt >= 0 && registrantAt > modeAt && dealAt > registrantAt && detailAt > dealAt,
  "폼 순서가 진행방식 → 등록자유형 → 거래유형 → 상세정보가 아닙니다.");

for (const [value, label] of [
  ["owner", "소유자 또는 대리인"],
  ["building_owner", "건물주 또는 대리인"],
  ["business", "사업주(숙박업대표) 또는 대리인"],
]) {
  expect(modal.includes(`{value: "${value}", label: "${label}"}`),
    `등록자유형 ${value} / ${label} 옵션이 없습니다.`);
}
expect(modal.includes("presetRegistrantType") && modal.includes("presetDealType"),
  "장기방 등록용 사전선택 파라미터가 없습니다.");
expect(modal.includes("form.dataset.registrantType"),
  "등록자유형 변경 플래그가 폼 data 속성에 저장되지 않습니다.");

expect(main.includes('id="btnBuyRequest"') && main.includes("display:none"),
  "매수의뢰 버튼이 숨김 처리되지 않았습니다.");
expect(main.includes('id="btnLongTermRoom"') && main.includes(">장기방 내놓기</button>"),
  "장기방 내놓기 버튼이 없습니다.");
expect(
  main.includes('presetRegistrantType: "business"') &&
  main.includes('presetDealType: "단기임대"'),
  "장기방 내놓기 버튼의 사업주/단기임대 사전선택이 없습니다."
);

console.log("OK  등록자유형 3분류·폼 순서·장기방 사전선택·매수의뢰 숨김");