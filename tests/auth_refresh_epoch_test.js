const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const { test } = require("node:test");

const source = fs.readFileSync("static/js/auth.js", "utf8");
const start = source.indexOf("  var authRefreshEpoch = 0;\n  function refreshMe() {");
const end = source.indexOf("  // 헤더 밖 페이지", start);
assert(start >= 0 && end > start, "Extract the complete session refresh signature");

function fixture() {
  const requests = [], events = [], state = { user: null };
  const context = vm.createContext({
    window: {},
    sessionStorage: { getItem: () => "1", removeItem: () => {} },
    fetch: () => new Promise((resolve, reject) => requests.push({ resolve, reject })),
    renderLoggedIn: user => { state.user = user; },
    renderLoggedOut: () => { state.user = null; },
    emitAuthChange: (loggedIn, user) => events.push({ loggedIn, user }),
  });
  vm.runInContext(source.slice(start, end), context);
  return { context, requests, events, state };
}
const settle = () => new Promise(setImmediate);
const reply = (request, data) => request.resolve({ json: async () => data });
const member = id => ({ logged_in: true, account_type: "user", id });

test("late anonymous response cannot undo a completed member login", async () => {
  const f = fixture();
  f.context.refreshMe();
  const latest = f.context.refreshMe();
  assert.equal(typeof latest.then, "function");
  reply(f.requests[1], member("owned-member"));
  await latest;
  reply(f.requests[0], { logged_in: false });
  await settle();
  assert.equal(f.context.window.__livingstayLoggedIn, true);
  assert.equal(f.state.user.id, "owned-member");
  assert.equal(f.events.length, 1);
});

test("late authenticated response cannot restore a logged-out session", async () => {
  const f = fixture();
  f.context.refreshMe(); f.context.refreshMe();
  reply(f.requests[1], { logged_in: false });
  await settle();
  reply(f.requests[0], member("owned-old-member"));
  await settle();
  assert.equal(f.context.window.__livingstayLoggedIn, false);
  assert.equal(f.state.user, null);
  assert.deepEqual(f.events, [{ loggedIn: false, user: null }]);
});

test("late transport failure cannot clear a newer authenticated session", async () => {
  const f = fixture();
  f.context.refreshMe(); f.context.refreshMe();
  reply(f.requests[1], member("owned-member"));
  await settle();
  f.requests[0].reject(new Error("owned stale transport failure"));
  await settle();
  assert.equal(f.context.window.__livingstayLoggedIn, true);
  assert.equal(f.events.length, 1);
});

test("latest business identity keeps member-only polling disabled", async () => {
  const f = fixture();
  f.context.refreshMe(); f.context.refreshMe();
  reply(f.requests[1], { logged_in: true, account_type: "operator", id: "owned-operator" });
  await settle();
  reply(f.requests[0], { logged_in: false });
  await settle();
  assert.equal(f.context.window.__livingstayAccountType, "operator");
  assert.equal(f.context.window.__livingstayLoggedIn, false);
  assert.equal(f.events.length, 1);
  assert.equal(f.events[0].loggedIn, true);
  assert.equal(f.state.user.id, "owned-operator");
});

test("late previous-member response cannot replace a new account identity", async () => {
  const f = fixture();
  f.context.refreshMe(); f.context.refreshMe();
  reply(f.requests[1], member("owned-new-member"));
  await settle();
  reply(f.requests[0], member("owned-old-member"));
  await settle();
  assert.equal(f.state.user.id, "owned-new-member");
  assert.equal(f.events.length, 1);
});

test("a latest transport failure still fails closed rather than hiding errors", async () => {
  const f = fixture();
  f.context.refreshMe();
  reply(f.requests[0], member("owned-member"));
  await settle();
  f.context.refreshMe();
  f.requests[1].reject(new Error("owned latest transport failure"));
  await settle();
  assert.equal(f.context.window.__livingstayLoggedIn, false);
  assert.equal(f.context.window.__livingstayAccountType, null);
  assert.equal(f.state.user, null);
  assert.equal(f.events.at(-1).loggedIn, false);
});
