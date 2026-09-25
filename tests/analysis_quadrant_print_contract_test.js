const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

const analysisJs = fs.readFileSync("static/js/analysis.js", "utf8");
const rentalJs = fs.readFileSync("static/js/rental-analysis.js", "utf8");

const recorderStart = analysisJs.indexOf("var quadrantLayoutRecorder=");
const recorderEnd = analysisJs.indexOf("\n  if(window.Chart", recorderStart);
assert(recorderStart >= 0 && recorderEnd > recorderStart,
  "Property quadrant recorder must be declared before Chart initialization.");

const window = { __analysisChartLayout: { baseline: { x: 431, y: 227 } } };
const sandbox = { window };
vm.runInNewContext(analysisJs.slice(recorderStart, recorderEnd), sandbox);
const plugin = sandbox.quadrantLayoutRecorder;
assert(plugin && typeof plugin.afterDraw === "function",
  "Property quadrant layout recorder is not registered.");

const quadrants = Array.from({ length: 4 }, () => ({ style: {} }));
plugin.afterDraw({
  canvas: {
    id: "scatterChart",
    parentElement: { querySelectorAll: () => quadrants },
  },
  width: 1120,
  height: 560,
  chartArea: { left: 60, top: 20, right: 1090, bottom: 520 },
});

const baseline = window.__analysisChartLayout.baseline;
assert.deepStrictEqual(
  Array.from(baseline.boundaries.vertical),
  [431, 431, 431, 431],
  "Property quadrant vertical edges must match the chart baseline in pixels.",
);
assert.deepStrictEqual(
  Array.from(baseline.boundaries.horizontal),
  [227, 227, 227, 227],
  "Property quadrant horizontal edges must match the chart baseline in pixels.",
);
assert.strictEqual(quadrants[0].style.width, `${(431 / 1120) * 100}%`,
  "Property overlay dimensions must scale with the captured print image.");
assert(analysisJs.includes('addEventListener("beforeprint"')
  && analysisJs.includes('addEventListener("afterprint"')
  && analysisJs.includes("chart.resize(width||1120,height||560)"),
"Property chart must resize before printing and restore its responsive size afterward.");

assert(rentalJs.includes("window.__analysisChartLayout.rental")
  && rentalJs.includes("valueX: benchmarkIncomeYield()")
  && rentalJs.includes("valueY: 0.5")
  && rentalJs.includes("quadrants[0].right, quadrants[1].left")
  && rentalJs.includes('addEventListener("beforeprint"')
  && rentalJs.includes('addEventListener("afterprint"'),
"Rental chart must expose average-baseline/quadrant pixels and resize around printing.");

console.log("property and rental print quadrant checks passed");