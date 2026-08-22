// 관심저장 낙관적 UI가 서버/네트워크 실패 시 즉시 원상복구되는지 확인한다.
const fs = require("fs");
const vm = require("vm");

const source = fs.readFileSync("static/js/main.js", "utf8");
const start = source.indexOf('const FAV_KEY = "livingstay_favorites"');
const end = source.indexOf("\nfunction removeFav", start);

function expect(condition, message) {
  if (!condition) throw new Error(message);
}

expect(start >= 0 && end > start, "toggleFav 함수 영역을 찾지 못했습니다.");
const toggleSource = source.slice(start, end);
expect(
  (toggleSource.match(/\.then\(function\(r\)/g) || []).length === 2 &&
  toggleSource.includes('if (!r.ok) throw new Error("save-failed");') &&
  toggleSource.includes('if (!result.ok) throw new Error(result.message || "save-failed");'),
  "POST/DELETE 응답 상태와 JSON ok 값을 확인하지 않습니다."
);

const alerts = [];
let renderCalls = 0;
let countCalls = 0;
let sideCalls = 0;
let syncCalls = 0;
let checkbox = { checked: false };
const context = {
  URLSearchParams,
  location: { search: "" },
  window: { __livingstayLoggedIn: true },
  document: {
    getElementById(id) {
      if (id === "chkFavOnly") return checkbox;
      return null;
    },
  },
  alert: (message) => alerts.push(message),
  updateFavCountLabel: () => { countCalls += 1; },
  renderFavChips: () => { renderCalls += 1; },
  loadSideFavorites: () => { sideCalls += 1; },
  loadBoard: () => {},
  setTimeout,
  console,
};
context.window.__syncOpenFavBtn = () => { syncCalls += 1; };
vm.createContext(context);
vm.runInContext(toggleSource, context);

async function settle() {
  await new Promise((resolve) => setImmediate(resolve));
  await new Promise((resolve) => setImmediate(resolve));
}

async function run() {
  // HTTP 500 저장 실패: 낙관적으로 추가한 키가 제거되고 오류를 알린다.
  context.fetch = () => Promise.resolve({
    ok: false,
    json: () => Promise.resolve({ ok: false, message: "저장 실패" }),
  });
  vm.runInContext("serverFavKeys = new Set();", context);
  const saved = vm.runInContext(
    "toggleFav({building_name:'아이리스모텔', address:'강원특별자치도 양양군 주청2길 18', building_id:12794})",
    context
  );
  expect(saved === true, "저장 요청이 시작되지 않았습니다.");
  await settle();
  expect(
    !vm.runInContext("serverFavKeys.has('아이리스모텔|강원특별자치도 양양군 주청2길 18')", context),
    "POST 실패 뒤 관심키가 롤백되지 않았습니다."
  );

  // DELETE 네트워크 실패: 낙관적으로 제거한 키와 관심단지 필터를 다시 복원한다.
  context.fetch = () => Promise.reject(new Error("network-offline"));
  checkbox = { checked: false };
  vm.runInContext(
    "serverFavKeys = new Set(['아이리스모텔|강원특별자치도 양양군 주청2길 18']);" +
    "state = {...state, favOnly:true, favKey:'아이리스모텔|강원특별자치도 양양군 주청2길 18'};",
    context
  );
  const removed = vm.runInContext(
    "toggleFav({building_name:'아이리스모텔', address:'강원특별자치도 양양군 주청2길 18', building_id:12794})",
    context
  );
  expect(removed === true, "삭제 요청이 시작되지 않았습니다.");
  await settle();
  expect(
    vm.runInContext("serverFavKeys.has('아이리스모텔|강원특별자치도 양양군 주청2길 18')", context),
    "DELETE 실패 뒤 관심키가 롤백되지 않았습니다."
  );
  expect(
    vm.runInContext("state.favOnly && state.favKey === '아이리스모텔|강원특별자치도 양양군 주청2길 18'", context) &&
    checkbox.checked,
    "DELETE 실패 뒤 활성 관심단지 필터가 복원되지 않았습니다."
  );
  expect(alerts.length === 2, "실패할 때마다 오류 알림이 표시되지 않습니다.");
  expect(renderCalls >= 4 && countCalls >= 4 && sideCalls >= 4 && syncCalls >= 2,
    "실패 롤백 뒤 관심단지 UI와 별 아이콘을 다시 그리지 않습니다.");

  console.log("OK  관심저장 HTTP/네트워크 실패 시 상태·필터·별 아이콘 롤백");
}

run().catch((error) => {
  console.error(error);
  process.exit(1);
});