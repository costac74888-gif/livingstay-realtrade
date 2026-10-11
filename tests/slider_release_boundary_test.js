const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

class Target {
  constructor() { this.handlers = {}; this.disabled = false; }
  addEventListener(type, fn) { (this.handlers[type] ||= []).push(fn); }
  emit(type, extra = {}) {
    for (const fn of this.handlers[type] || []) {
      fn({ button: 0, detail: 0, preventDefault() {}, ...extra });
    }
  }
}

function scenario() {
  const window = new Target(), document = new Target(), button = new Target();
  const timers = new Map();
  let sequence = 0, count = 0;
  window.setTimeout = fn => { timers.set(++sequence, [fn, false]); return sequence; };
  window.setInterval = fn => { timers.set(++sequence, [fn, true]); return sequence; };
  window.clearTimeout = window.clearInterval = id => timers.delete(id);
  const context = { window, document, Set, Array };
  vm.runInNewContext(fs.readFileSync("static/js/slider-utils.js", "utf8"), context);
  window.analysisSliderUtils.bindStepButtons(
    { querySelectorAll: () => [button] }, () => { count++; return true; });
  return { window, document, button, value: () => count,
    tick() {
      for (const [id, [fn, repeat]] of [...timers]) {
        if (!timers.has(id)) continue;
        if (!repeat) timers.delete(id);
        fn();
      }
    } };
}

const cases = [
  ["touch compatibility click is not a second increment", s => {
    s.button.emit("pointerdown", { pointerType: "touch" });
    s.button.emit("pointerup", { pointerType: "touch" });
    const released = s.value();
    s.button.emit("click", { pointerType: "touch", sourceCapabilities: { firesTouchEvents: true } });
    assert.equal(s.value(), released);
    s.button.emit("keydown", { key: "Enter" });
    s.button.emit("click");
    assert.equal(s.value(), released + 1, "Keyboard activation must remain available");
  }],
  ...["pointerup", "pointercancel", "touchend", "touchcancel", "blur"].map(type =>
    [type + " outside the button stops repeat", s => {
      s.button.emit("pointerdown", { pointerType: "touch" });
      s.tick(); s.tick();
      s.window.emit(type);
      const released = s.value();
      s.tick(); s.tick();
      assert.equal(s.value(), released);
    }]),
  ["hidden document stops repeat", s => {
    s.button.emit("pointerdown");
    s.tick();
    s.document.hidden = true;
    s.document.emit("visibilitychange");
    const released = s.value();
    s.tick(); s.tick();
    assert.equal(s.value(), released);
  }],
];
const errors = [];
for (const [name, run] of cases) {
  try { run(scenario()); console.log("PASS", name); }
  catch (error) { errors.push(name); console.error("FAIL", name, error.message); }
}
assert.deepEqual(errors, [], "Every release/cancellation boundary must pass");
