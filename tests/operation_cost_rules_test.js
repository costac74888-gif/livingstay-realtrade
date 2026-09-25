const fs = require("fs");
const vm = require("vm");
const assert = require("assert");

const root = process.cwd();
const sharedSource = fs.readFileSync(`${root}/static/js/rental-costs.js`, "utf8");
const rentalSource = fs.readFileSync(`${root}/static/js/rental-analysis.js`, "utf8");
const operationSource = fs.readFileSync(`${root}/static/js/operation-analysis.js`, "utf8");
const html = fs.readFileSync(`${root}/static/analysis.html`, "utf8");
const context = { window: {} };
vm.runInNewContext(sharedSource, context);

const costs = context.window.livingstayRentalCosts;
const near = (actual, expected, label) => {
  assert(Math.abs(actual - expected) < 0.0001, `${label}: expected ${expected}, got ${actual}`);
};

const acquisition = costs.acquisitionCosts(4000);
near(acquisition.tax, 184, "acquisition tax");
near(acquisition.brokerFee, 36, "broker fee");
near(costs.estimateAnnualTax(4000), 10.6, "annual holding tax estimate");
near(costs.annualHoldingCosts(10.6, 0, 0), 10.6, "annual holding costs");
near(costs.annualNetYield(95.6 * 12 - 10.6, 4000 + 184 + 36), 26.9336492891, "net annual yield");
assert(Number.isNaN(costs.annualNetYield(100, 0)), "zero investment basis must be uncomputable");

assert(html.indexOf("/static/js/rental-costs.js") < html.indexOf("/static/js/rental-analysis.js"),
  "shared cost rules must load before rental-analysis.js");
assert(rentalSource.includes("livingstayRentalCosts.estimateAnnualTax"));
assert(rentalSource.includes("livingstayRentalCosts.annualHoldingCosts"));
assert(operationSource.includes("sharedCosts.annualNetYield"));
assert(operationSource.includes("annualHoldingCosts:"));
assert(operationSource.includes("investmentBasis:"));
assert(!operationSource.includes("net * 12 / (buy * 10000)"));
assert(operationSource.includes("window.__operationChartRelayout"));
assert(operationSource.includes("quadrantBoundaries"));

console.log("operation shared cost rules checks passed");