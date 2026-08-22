// 사업주 방 재고의 층별 표시·채널 자동저장·요약 UI가 빠지지 않았는지 확인한다.
const fs = require("fs");
const vm = require("vm");

const html = fs.readFileSync("static/mypage.html", "utf8");

function expect(condition, message) {
  if (!condition) throw new Error(message);
}

for (const needle of [
  'class="room-floor-add-btn"',
  'class="room-floor-group"',
  'class="room-floor-grid"',
  'class="room-floor"',
  "층 미지정",
  'class="room-channel"',
  "OTA전용",
  "장박가능",
  'class="room-inventory-summary"',
  "장박가능 ' + longStayRooms.length",
  '"/rooms/bulk"',
  "created_count",
  "skipped_count",
  "channel: channelEl ? channelEl.value",
  "floor: floorValue",
]) {
  expect(html.includes(needle), `방 재고 층·채널 UI 누락: ${needle}`);
}

expect(
  html.includes('room.floor == null ? "__unassigned__"') &&
  html.includes("groupKey + \"층\""),
  "층별 그룹 또는 층 미지정 그룹 렌더링이 없습니다."
);
expect(
  html.includes('.room-status, .room-contract-date, .room-floor, .room-channel'),
  "층 또는 채널 변경 자동저장 이벤트가 없습니다."
);

const inventoryMatch = html.match(
  /function roomInventoryHtml\(items\)\{[\s\S]*?(?=\n\s*function loadRoomInventory)/
);
expect(inventoryMatch, "방 재고 렌더링 함수를 찾지 못했습니다.");
const context = {
  escapeHtml: (value) => String(value),
  roomDdayMeta: () => null,
  Number,
};
vm.createContext(context);
vm.runInContext(inventoryMatch[0], context);

const rendered = context.roomInventoryHtml([
  { id: 1, room_label: "기존방", status: "공실", floor: null, channel: "장박가능" },
  { id: 2, room_label: "301", status: "공실", floor: 3, channel: "OTA전용" },
]);
expect(
  rendered.includes('class="room-floor-grid"') &&
  rendered.includes('class="room-floor"') &&
  rendered.indexOf('data-floor="3"') < rendered.indexOf('data-floor="__unassigned__"') &&
  rendered.includes('value="3"') &&
  rendered.includes("전체 2실") &&
  rendered.includes("OTA전용 1실"),
  "층 지정 방과 층 미지정 방의 그리드·그룹·채널 요약 렌더링이 올바르지 않습니다."
);

console.log("OK  방 재고 층별 그리드·층 이동·채널 토글·요약·벌크 생성 UI");