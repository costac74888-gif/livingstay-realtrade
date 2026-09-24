const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const window = {};
const source = fs.readFileSync("static/js/slider-utils.js", "utf8");
vm.runInNewContext(source, { window, Math, Number, RangeError });

const utils = window.analysisSliderUtils;
assert.ok(utils, "공통 슬라이더 모듈이 설치되어야 합니다.");

for (const [raw, expected] of [
  [0.75, 1], [2.5, 5], [30, 50], [75, 100], [750, 1000], [3600, 5000],
]) {
  assert.equal(utils.niceStep(raw), expected, `niceStep(${raw})`);
}

assert.throws(() => utils.niceStep(0), RangeError);

assert.deepEqual(
  JSON.parse(JSON.stringify(utils.purchaseBounds(5000))),
  { min: 3500, max: 6500, step: 100 },
);
assert.deepEqual(
  JSON.parse(JSON.stringify(utils.purchaseBounds(52000))),
  { min: 36400, max: 67600, step: 1000 },
);
assert.deepEqual(
  JSON.parse(JSON.stringify(utils.rentBounds(30))),
  { min: 15, max: 50, step: 1 },
);
assert.equal(utils.nearest(47, utils.rentBounds(30)), 47);
assert.deepEqual(
  JSON.parse(JSON.stringify(utils.includeValue(utils.rentBounds(30), 90))),
  { min: 15, max: 90, step: 1 },
);
assert.equal(utils.formatMan(4000), "4,000만원");
assert.equal(utils.formatMan(52000), "5억 2,000만원");
assert.equal(utils.formatMan(32), "32만원");

for (const [kind, min, max] of [
  ["purchase", 100, 500000],
  ["deposit", 0, 5000],
  ["rent", 1, 1000],
  ["vacancy", 0, 12],
  ["adr", 50000, 2000000],
  ["occ", 20, 100],
  ["opex", 10, 80],
  ["mgmtFee", 0, 50],
]) {
  assert.equal(utils.HARD_CAPS[kind][0], min, `${kind} hard minimum`);
  assert.equal(utils.HARD_CAPS[kind][1], max, `${kind} hard maximum`);
  assert.equal(utils.clampHard(kind, min), min, `${kind} accepts minimum`);
  assert.equal(utils.clampHard(kind, max), max, `${kind} accepts maximum`);
  assert.equal(utils.clampHard(kind, min - 1), null, `${kind} rejects below minimum`);
  assert.equal(utils.clampHard(kind, max + 1), null, `${kind} rejects above maximum`);
}
assert.equal(utils.clampHard("loan", 0, 5000), 0);
assert.equal(utils.clampHard("loan", 5000, 5000), 5000);
assert.equal(utils.clampHard("loan", 5001, 5000), null);
assert.equal(utils.clampHard("loan", 400000, 500000), 400000);
assert.equal(utils.clampHard("loan", 400001, 500000), null);
assert.equal(utils.clampHard("loan", 1, 0), null);
for (const invalid of ["", null, undefined, "NaN", "Infinity", -Infinity, NaN]) {
  assert.equal(utils.clampHard("rent", invalid), null, `rent rejects ${String(invalid)}`);
}
assert.throws(() => utils.clampHard("unknown", 1), /알 수 없는 슬라이더 항목/);

console.log("공통 슬라이더 유틸리티 테스트 통과");