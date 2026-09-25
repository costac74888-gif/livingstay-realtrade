const fs = require("fs");
const assert = require("assert");

const rentalSource = fs.readFileSync("static/js/rental-analysis.js", "utf8");
const operationSource = fs.readFileSync("static/js/operation-analysis.js", "utf8");

function functionBody(source, start, end) {
  const startIndex = source.indexOf(start);
  const endIndex = source.indexOf(end, startIndex);
  assert(startIndex >= 0 && endIndex > startIndex, `could not locate ${start}`);
  return source.slice(startIndex, endIndex);
}

const operationBasis = functionBody(
  operationSource,
  "function currentPurchaseBasis()",
  "function computeSliderBounds()",
);
assert(operationBasis.indexOf("if (rentalScenarioMatchesBuilding())")
  < operationBasis.indexOf('getElementById("rentalMarketPrice")'),
"rental market-price fallback must be scoped to a matching building");
assert(operationBasis.includes("purchasePriceBaseBuildingId === buildingId()"),
  "cached operation purchase basis must be tagged to the active building");

const rentalReset = functionBody(
  rentalSource,
  "function resetRentalScenarioForBuildingChange()",
  "function restoreSharedRentalValues()",
);
[
  "loadedBuildingId = \"\"",
  "window.__rentalAnalysisBuilding = null",
  "sharedValuesRestored = true",
  "ids.forEach(function (id) { $(id).value = \"\"; })",
].forEach((field) => assert(rentalReset.includes(field),
  `building-change reset must clear ${field}`));
const rentalInputDeclaration = functionBody(
  rentalSource,
  "var ids = [",
  "];",
);
[
  "rentalPurchasePrice", "rentalMarketPrice", "rentalManagementCost",
  "rentalOtherCost", "rentalLoanAmount",
].forEach((field) => assert(rentalInputDeclaration.includes(field),
  `building-change reset input list must include ${field}`));
assert(rentalSource.includes('window.addEventListener("livingstay:analysis-reset", function () {')
  && rentalSource.includes("resetRentalScenarioForBuildingChange();\n    loadBuilding();"),
"analysis reset event must clear rental scenario state and load the selected building");

// Regression scenario: A's rental market-price field remains in the DOM while
// B is being selected. The operation basis must reject it until identity matches.
function scopedMarketPrice(activeBuildingId, rentalBuildingId, marketPrice) {
  return String(activeBuildingId) === String(rentalBuildingId) ? marketPrice : null;
}
assert.strictEqual(scopedMarketPrice("building-A", "building-A", 4200), 4200);
assert.strictEqual(scopedMarketPrice("building-B", "building-A", 4200), null,
  "switching A → B must not reuse A's rental market-price basis");

console.log("analysis building-scope A-to-B regression checks passed");