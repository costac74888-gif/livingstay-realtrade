// 사업주 방 재고가 층별 벌크 UI 없이 개별 카드·복사 흐름을 유지하는지 확인한다.
const fs = require("fs");
const vm = require("vm");

const html = fs.readFileSync("static/mypage.html", "utf8");

function expect(condition, message) {
  if (!condition) throw new Error(message);
}

for (const needle of [
  'class="room-label"',
  'class="room-deposit"',
  'class="room-monthly-rent"',
  'class="room-copy-btn"',
  'class="room-channel"',
  "OTA전용",
  "장박가능",
  'class="room-inventory-summary"',
  "장박가능 ' + longStayRooms.length",
  "monthly_rent_krw: monthlyRent",
  "deposit_krw: deposit",
  "monthly_rent_krw: rentText ? Number(rentText) : null",
  "deposit_krw: depositText ? Number(depositText) : null",
  'room_label: label',
  "새 호실",
]) {
  expect(html.includes(needle), `방 재고 개별 입력·복사 UI 누락: ${needle}`);
}

expect(
  !html.includes('class="room-floor-add-btn"') &&
  !html.includes('class="room-floor-group"') &&
  !html.includes('"/rooms/bulk"'),
  "제거 대상인 층별 벌크 생성 UI가 남아 있습니다."
);
expect(
  html.includes('.room-label, .room-deposit, .room-monthly-rent, .room-status, .room-contract-date, .room-channel'),
  "호실·보증금·월세·상태·계약만기일·채널 변경 자동저장 이벤트가 없습니다."
);

const inventoryMatch = html.match(
  /function roomInventoryHtml\(items\)\{[\s\S]*?(?=\n\s*function loadRoomInventory)/
);
expect(inventoryMatch, "방 재고 렌더링 함수를 static/mypage.html에서 찾지 못했습니다.");
const context = {
  escapeHtml: (value) => String(value),
  roomDdayMeta: () => null,
  Number,
};
vm.createContext(context);
vm.runInContext(inventoryMatch[0], context);

const rendered = context.roomInventoryHtml([
  { id: 1, room_label: "기존방", deposit_krw: 500, monthly_rent_krw: 90, status: "공실", channel: "장박가능" },
  { id: 2, room_label: "301", monthly_rent_krw: 120, status: "공실", channel: "OTA전용" },
]);
expect(
  rendered.includes('class="room-inventory-list"') &&
  rendered.includes('class="room-deposit"') &&
  rendered.includes('value="500"') &&
  rendered.includes('class="room-monthly-rent"') &&
  rendered.includes('value="90"') &&
  rendered.includes('class="room-copy-btn"') &&
  rendered.includes("전체 2실") &&
  rendered.includes("OTA전용 1실"),
  "방 재고 단순 목록·월세·복사·채널 요약 렌더링이 올바르지 않습니다."
);

console.log("OK  방 재고 개별 카드·보증금·월세·복사·채널·요약 UI");