const fs = require("fs");
const vm = require("vm");
const assert = require("assert");

const sharedSource = fs.readFileSync("static/js/rental-costs.js", "utf8");
const operationSource = fs.readFileSync("static/js/operation-analysis.js", "utf8");
const context = { window: {} };
vm.runInNewContext(sharedSource, context);
const costs = context.window.livingstayRentalCosts;

function yieldForBuilding(monthlyNetMan, purchaseMan) {
  const propertyTax = costs.estimateAnnualTax(purchaseMan);
  const holdingCosts = costs.annualHoldingCosts(propertyTax, 0, 0);
  const acquisition = costs.acquisitionCosts(purchaseMan);
  const annualNet = monthlyNetMan * 12 - holdingCosts;
  const investment = purchaseMan + acquisition.tax + acquisition.brokerFee;
  return { holdingCosts, yield: costs.annualNetYield(annualNet, investment) };
}

const buildingA = yieldForBuilding(95.6, 4000);
const buildingB = yieldForBuilding(95.6, 8000);
assert.strictEqual(buildingA.holdingCosts, costs.estimateAnnualTax(4000));
assert.strictEqual(buildingB.holdingCosts, costs.estimateAnnualTax(8000));
assert.notStrictEqual(buildingA.holdingCosts, buildingB.holdingCosts,
  "switching buildings must recalculate estimated holding cost from the active operation purchase price");
assert.notStrictEqual(buildingA.yield, buildingB.yield,
  "switching buildings must recalculate the return basis from the active operation purchase price");
assert(operationSource.includes("annualHoldingCosts(propertyTax, 0, 0)"),
  "operation yield must not inherit extra costs from a potentially different rental unit");
const publishStateSource = operationSource.slice(
  operationSource.indexOf("function publishOperationState()"),
  operationSource.indexOf("function renderOperationChart()"),
);
assert(!publishStateSource.includes("rentalManagementCost")
  && !publishStateSource.includes("rentalOtherCost"),
"operation yield must be independent of rental-form management and other-cost inputs");
assert(operationSource.includes('annualHoldingCostsAssumption: "매입가 기준 추정 보유세만 반영.'));

console.log("operation building-switch cost isolation checks passed");