"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const source = fs.readFileSync("static/admin.html", "utf8");
const start = source.indexOf("// 일/월/연도별 페이지뷰는 같은 측정값");
const end = source.indexOf("// 오늘 경로별 조회수 상위 5", start);
assert(start !== -1 && end > start, "방문자 추이 차트 렌더러를 찾을 수 없습니다.");

const elements = Object.fromEntries(["viewsTrendTitle", "viewsTrendHint", "chartViews", "viewsTrendPeriod"]
  .map((id) => [id, { textContent: "", addEventListener(event, handler) { this.handler = handler; } }]));
const charts = [];
class Chart {
  constructor(canvas, options) {
    this.canvas = canvas;
    this.options = options;
    charts.push(this);
  }
  destroy() { this.destroyed = true; }
}
const context = {
  d: { views: {
    daily: [{ day: "2026-09-01", count: 2 }, { day: "2026-09-02", count: 0 }],
    monthly: [{ month: "2026-08", count: 12 }, { month: "2026-09", count: 2 }],
    yearly: [{ year: "2025", count: 38 }, { year: "2026", count: 14 }],
  } },
  collectStart: "2025-01-02",
  document: { getElementById: (id) => elements[id] },
  Chart,
  ChartDataLabels: {},
  BRAND: { brass: "#B4863F", brassSoft: "#eee", ink: "#16202E" },
  commonOpts: {},
  statsCharts: [],
  num: (value) => String(value),
};
vm.runInNewContext(source.slice(start, end), context);
assert.equal(elements.viewsTrendTitle.textContent, "일별 방문자 추이");
assert.deepEqual(Array.from(charts[0].options.data.datasets[0].data), [2, 0]);
assert.equal(elements.viewsTrendHint.textContent.includes("당월 1일~오늘"), true);

elements.viewsTrendPeriod.handler({ target: { value: "monthly" } });
assert.equal(charts[0].destroyed, true);
assert.equal(elements.viewsTrendTitle.textContent, "월별 방문자 추이");
assert.deepEqual(Array.from(charts[1].options.data.labels), ["2026-08", "2026-09"]);
assert.deepEqual(Array.from(charts[1].options.data.datasets[0].data), [12, 2]);

elements.viewsTrendPeriod.handler({ target: { value: "yearly" } });
assert.equal(charts[1].destroyed, true);
assert.equal(elements.viewsTrendTitle.textContent, "연도별 방문자 추이");
assert.deepEqual(Array.from(charts[2].options.data.labels), ["2025", "2026"]);
assert.deepEqual(Array.from(charts[2].options.data.datasets[0].data), [38, 14]);
assert.equal(context.statsCharts.length, 1, "기간 변경 후 이전 차트가 남아 있습니다.");
console.log("OK  관리자 방문자 추이 선택 메뉴·그래프 전환");