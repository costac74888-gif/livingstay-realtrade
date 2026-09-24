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

console.log("공통 슬라이더 유틸리티 테스트 통과");