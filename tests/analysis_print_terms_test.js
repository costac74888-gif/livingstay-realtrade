const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

const termsJs = fs.readFileSync("static/js/analysis-terms.js", "utf8");
const context = {
  window: {},
  document: {
    readyState: "loading",
    addEventListener() {},
  },
};
vm.runInNewContext(termsJs, context);

const terms = context.window.livingstayAnalysisTerms;
assert(terms && typeof terms.expand === "function",
  "The shared analysis terms helper must be available.");
assert.strictEqual(terms.label("ADR"), "ADR(객실 평균요금)");
assert.strictEqual(terms.expand("ADR(객실 평균요금)"), "ADR(객실 평균요금)",
  "Already translated terms must remain unchanged.");

const paragraphSeen = new Set();
assert.strictEqual(terms.expand("ADR", { seen: paragraphSeen }), "ADR(객실 평균요금)");
assert.strictEqual(terms.expand(" · ADR", { seen: paragraphSeen }), " · ADR",
  "Only the first occurrence in a paragraph is expanded.");
assert.strictEqual(terms.expand("ADR", { seen: new Set() }), "ADR(객실 평균요금)",
  "A new paragraph gets its own first-use expansion.");

const sourceText = "ADR";
terms.expand(sourceText);
assert.strictEqual(sourceText, "ADR", "Term expansion must not mutate source text.");

console.log("analysis print shared-term checks passed");