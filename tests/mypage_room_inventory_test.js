// 마이페이지 방 재고 D-day 경계값 회귀 테스트.
// 인라인 스크립트의 계산 함수를 실제 HTML에서 읽어 검증한다.
const fs = require("fs");
const vm = require("vm");

const html = fs.readFileSync("static/mypage.html", "utf8");
const match = html.match(
  /function roomDdayMeta\(dateText\)\{[\s\S]*?\n   \}\n\n   function roomInventoryHtml/
);
if (!match) {
  throw new Error("roomDdayMeta 함수를 static/mypage.html에서 찾지 못했습니다.");
}

const fixedNow = new Date(2026, 0, 1, 12, 0, 0);
class FixedDate extends Date {
  constructor(...args) {
    super(args.length ? args[0] : fixedNow.getTime());
  }
  static UTC(...args) {
    return Date.UTC(...args);
  }
}

const context = { Date: FixedDate, Math, Number };
vm.createContext(context);
vm.runInContext(match[0].replace(/\n\n   function roomInventoryHtml$/, ""), context);

function isoAfter(days) {
  const date = new Date(2026, 0, 1 + days);
  return [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, "0"),
    String(date.getDate()).padStart(2, "0"),
  ].join("-");
}

const cases = [
  [31, "#6B7684", `만기 ${isoAfter(31)}`],
  [30, "#B45309", "D-30"],
  [7, "#B42318", "D-7"],
  [6, "#B42318", "D-6"],
];

for (const [days, color, label] of cases) {
  const result = context.roomDdayMeta(isoAfter(days));
  if (!result || result.color !== color || result.label !== label) {
    throw new Error(
      `D-day ${days}일 경계 실패: ${JSON.stringify(result)} (기대 ${color}, ${label})`
    );
  }
}

console.log("OK  방 재고 D-day 31/30/7/6일 경계 및 색상");