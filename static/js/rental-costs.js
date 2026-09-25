/* Shared rental/operation analysis cost rules. All values use 만원. */
(function (root) {
  "use strict";

  function finiteAmount(value) {
    var amount = Number(value);
    return Number.isFinite(amount) && amount > 0 ? amount : 0;
  }

  function estimateAnnualTax(purchasePrice) {
    var purchase = finiteAmount(purchasePrice);
    if (!purchase) return 0;
    var assessedBase = purchase * 0.6;
    var propertyTax = assessedBase * 0.0025;
    var urbanAreaTax = assessedBase * 0.0014;
    var educationTax = propertyTax * 0.2;
    return Math.round((propertyTax + urbanAreaTax + educationTax) * 10) / 10;
  }

  function acquisitionCosts(purchasePrice) {
    var purchase = finiteAmount(purchasePrice);
    return {
      tax: Math.round(purchase * 0.046 * 10) / 10,
      brokerFee: Math.round(purchase * 0.009 * 10) / 10,
    };
  }

  function annualHoldingCosts(propertyTax, managementCost, otherCost) {
    return finiteAmount(propertyTax) + finiteAmount(managementCost) + finiteAmount(otherCost);
  }

  function annualNetYield(annualNetIncome, investmentBasis) {
    var annualNet = Number(annualNetIncome);
    var basis = Number(investmentBasis);
    if (!Number.isFinite(annualNet) || !Number.isFinite(basis) || basis <= 0) return NaN;
    return annualNet / basis * 100;
  }

  root.livingstayRentalCosts = {
    estimateAnnualTax: estimateAnnualTax,
    acquisitionCosts: acquisitionCosts,
    annualHoldingCosts: annualHoldingCosts,
    annualNetYield: annualNetYield,
  };
})(window);