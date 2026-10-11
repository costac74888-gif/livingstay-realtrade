const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const source = fs.readFileSync("static/js/main.js", "utf8");
const start = source.indexOf("window.__onKakaoSdkLoad = function()");
const end = source.indexOf('document.getElementById("btnSubmitCorrection")', start);
assert.ok(start >= 0 && end > start);
const bootstrap = source.slice(start, end);
for (const deferred of [false, true]) {
  const queued = [], events = [];
  vm.runInNewContext(`
    const window = {__kakaoSdkLoaded:true,kakao:{maps:{
      load:callback => ${deferred ? "queueMicrotask(callback)" : "callback()"}
    }}};
    const kakao = window.kakao;
    function initMap(){ events.push(laterStateInitialized); }
    ${bootstrap}
    const laterStateInitialized = true;
  `, { queueMicrotask: callback => queued.push(callback), events, console });
  assert.deepEqual(events, [], "Map initialization ran during script evaluation");
  while (queued.length) queued.shift()();
  assert.deepEqual(events, [true], "Map initialization missed or preceded later state");
}
console.log("PASS cached/synchronous and asynchronous SDK callbacks initialize after later state");
