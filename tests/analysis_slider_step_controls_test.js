const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const window = {
  setTimeout,
  clearTimeout,
  setInterval,
  clearInterval,
};
vm.runInNewContext(fs.readFileSync("static/js/slider-utils.js", "utf8"), {
  window,
  Math,
  Number,
  RangeError,
  Array,
});
const utils = window.analysisSliderUtils;

assert.deepEqual(
  JSON.parse(JSON.stringify(utils.rangeTicks({ min: 2, max: 13, step: 3 }))),
  [2, 5, 8, 11, 13],
  "range attainable ticks include the endpoint",
);
assert.equal(utils.adjacentTick(47, [44, 46, 48, 50], 1), 48,
  "plus from a directly entered between-tick amount selects the next tick");
assert.equal(utils.adjacentTick(47, [44, 46, 48, 50], -1), 46,
  "minus from a directly entered between-tick amount selects the previous tick");
assert.equal(utils.adjacentTick(48, [44, 46, 48, 50], 1), 50,
  "plus from an attainable amount selects exactly one following tick");
assert.equal(utils.adjacentTick(44, [44, 46, 48, 50], -1), null,
  "minus is unavailable at the minimum");
assert.equal(utils.adjacentTick(50, [44, 46, 48, 50], 1), null,
  "plus is unavailable at the maximum");
assert.deepEqual(
  JSON.parse(JSON.stringify(utils.mappedTicks(4, (tick) => [0, 10, 10, 30, 50][tick]))),
  [0, 10, 10, 30, 50],
  "piecewise mapped slider values preserve the real tick mapping",
);
assert.equal(utils.adjacentTick(10, [0, 10, 10, 30, 50], 1), 30,
  "duplicate mapped ticks are skipped while advancing");

const rental = fs.readFileSync("static/js/rental-analysis.js", "utf8");
const operation = fs.readFileSync("static/js/operation-analysis.js", "utf8");
const rentalCss = fs.readFileSync("static/css/rental-analysis.css", "utf8");
const operationCss = fs.readFileSync("static/css/operation-redesign.css", "utf8");
const sliderUtilsSource = fs.readFileSync("static/js/slider-utils.js", "utf8");

for (const [name, source] of [["rental", rental], ["operation", operation]]) {
  assert.match(source, /data-slider-step/, `${name} renders accessible step buttons`);
  assert.match(source, /data-slider-direction="-1"/, `${name} renders a previous button`);
  assert.match(source, /data-slider-direction="1"/, `${name} renders a next button`);
  assert.match(source, /Arrow\(Left\|Right\|Up\|Down\)/,
    `${name} intercepts range arrows using attainable ticks`);
  assert.match(source, /dispatchEvent\(new Event\("input", \{ bubbles: true \}\)\)/,
    `${name} reuses the slider input pathway`);
  assert.match(source, /dispatchEvent\(new Event\("change", \{ bubbles: true \}\)\)/,
    `${name} reuses the slider change pathway`);
}
assert.match(sliderUtilsSource, /pointerup.*pointerleave.*pointercancel/,
  "long press stops on pointerup, pointerleave, and pointercancel");
assert.match(operation, /livingstayAnalysisTerms\.label\("ADR"\) \+ " \(천원\)"/,
  "operation ADR axis uses the shared Korean term label");
assert.match(operation, /livingstayAnalysisTerms\.label\("OCC"\) \+ " \(%\)"/,
  "operation OCC axis uses the shared Korean term label");
assert.match(sliderUtilsSource, /}, 400\);/,
  "long press begins repeating after 400ms and repeats every 120ms");
assert.match(sliderUtilsSource, /}, 120\);/,
  "long press repeat interval is 120ms");
for (const [name, css] of [["rental", rentalCss], ["operation", operationCss]]) {
  assert.match(css, /width:\s*32px/, `${name} step control has a 32px desktop target`);
  assert.match(css, /width:\s*44px/, `${name} step control has a 44px mobile target`);
  assert.match(css, /@media\s+print[\s\S]*slider-step[\s\S]*display:\s*none/,
    `${name} hides step controls in print`);
}

console.log("분석 슬라이더 단계 버튼 테스트 통과");