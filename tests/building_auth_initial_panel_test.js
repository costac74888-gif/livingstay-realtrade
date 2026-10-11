const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const source = fs.readFileSync("static/js/main.js", "utf8");
const start = source.indexOf("let buildingPanelAuthInitialized = false;");
const end = source.indexOf("function updateFavCountLabel()", start);
assert.ok(start >= 0 && end > start, "Full auth-listener signature required");
const renders = [], handlers = {};
let selected = "property", favorites = 0;
const card = {textContent: ""};
const context = {
  window: {
    __openBuildingId: 11,
    __auctionPanelContext: {auctionId: 22, tab: "auction", items: [{id: 22}]},
    addEventListener: (name, callback) => {handlers[name] = callback;},
  },
  document: {
    getElementById: () => card,
    querySelector: () => ({dataset: {panel: selected}}),
  },
  renderBuildingPanel: (id, options) => renders.push({id, options}),
  loadServerFavKeys: async () => {favorites++;},
};
vm.runInNewContext(source.slice(start, end), context);
(async () => {
  await handlers["livingstay:auth"]();
  assert.equal(renders.length, 0, "Initial auth must not reset a pending auction deep link");
  assert.equal(favorites, 1, "Initial favorite refresh is preserved");
  selected = "auction";
  await handlers["livingstay:auth"]();
  assert.equal(renders.length, 1, "Subsequent account refresh still rechecks access");
  assert.equal(renders[0].id, 11);
  assert.equal(renders[0].options.auctionId, 22);
  assert.equal(renders[0].options.detailTab, "auction");
  selected = "operations";
  await handlers["livingstay:auth"]();
  assert.equal(renders[1].options.detailTab, "operations", "Later tab choice is preserved");
  assert.equal(favorites, 3);
  console.log("PASS initial auth preserves pending auction; later refresh checks access and retains chosen tab");
})().catch(error => {console.error(error); process.exitCode = 1;});
