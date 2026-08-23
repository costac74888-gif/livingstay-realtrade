// 홈 데이터 규모 지표가 API 응답의 4개 숫자를 실제 DOM에 쓰는지 점검한다.
const fs = require("fs");
const vm = require("vm");

const main = fs.readFileSync("static/js/main.js", "utf8");
const start = main.indexOf("async function loadPlatformStats(){");
const end = main.indexOf("\n}\n\n// 최초 로드:", start);
if (start < 0 || end < start) throw new Error("loadPlatformStats 함수를 찾지 못했습니다.");

const keys = ["building_count", "biz_count", "transaction_count", "listing_count"];
const elements = keys.map((key) => ({
  dataset: { platformStat: key },
  textContent: "불러오는 중…",
}));
const platformStats = {
  querySelector: (selector) => {
    const match = selector.match(/data-platform-stat="([^"]+)"/);
    return elements[keys.indexOf(match && match[1])] || null;
  },
};
const calls = [];
const context = {
  document: {
    getElementById: (id) => id === "platformStats" ? platformStats : null,
  },
  fetch: async (url, options) => {
    calls.push({ url, options });
    return {
      ok: true,
      json: async () => ({
        ok: true,
        building_count: 11802,
        biz_count: 3841,
        transaction_count: 16652,
        listing_count: 27,
      }),
    };
  },
  console: { error: () => {} },
};
vm.createContext(context);
vm.runInContext(main.slice(start, end + 2), context);

(async () => {
  await context.loadPlatformStats();
  if (calls.length !== 1 || calls[0].url !== "/api/stats/platform-summary") {
    throw new Error("플랫폼 통계 API 호출이 정확하지 않습니다.");
  }
  const actual = elements.map((el) => el.textContent);
  const expected = ["11,802", "3,841", "16,652", "27"];
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(`4개 지표 DOM 렌더링이 잘못됨: ${JSON.stringify(actual)}`);
  }
  console.log("OK  홈 플랫폼 통계 API 4개 숫자 DOM 렌더링");
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});