const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

function fixture() {
  let closed = 0, dialog = null;
  const handlers = {};
  const context = {
    document: {
      currentScript: null,
      getElementById: () => null,
      querySelector: () => dialog,
      body: {classList: {remove() {}}},
    },
    window: {addEventListener: (name, fn) => handlers[name] = fn},
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,
    "../static/js/membership.js"), "utf8"), context);
  return {
    open() {dialog = {remove() {closed++; dialog = null;}};},
    emit(loggedIn, id, account_type = "user", extra = {}) {
      handlers["livingstay:auth"]({detail: {
        loggedIn, user: loggedIn ? {id, account_type, ...extra} : null,
      }});
    },
    get closed() {return closed;},
  };
}

const stable = fixture();
stable.emit(true, 1);
stable.open();
stable.emit(true, 1);
assert.equal(stable.closed, 0, "same-account refresh must retain the dialog");
stable.emit(true, 2);
assert.equal(stable.closed, 1, "account switch must close the dialog");
stable.open();
stable.emit(false);
assert.equal(stable.closed, 2, "logout must close the dialog");

const late = fixture();
late.open();
late.emit(true, 1);
assert.equal(late.closed, 0, "late initial signed-in refresh must not close the dialog");
late.emit(true, 1, "operator");
assert.equal(late.closed, 1, "role change must close the dialog");
const business = fixture();
const operator = {active_role:"operator",active_business_table:"operators",active_business_id:1};
business.emit(true, 1, "user", operator);
business.open();
business.emit(true, 1, "user", operator);
assert.equal(business.closed, 0, "same unified business context must retain the dialog");
business.emit(true, 1, "user", {...operator,active_business_id:2});
assert.equal(business.closed, 1, "business switch must close the dialog");
business.open();
business.emit(true, 1, "user", {active_role:"general"});
assert.equal(business.closed, 2, "unified role switch must close the dialog");
console.log("OK membership dialog: refresh, delayed initial auth, account/role change and logout");
