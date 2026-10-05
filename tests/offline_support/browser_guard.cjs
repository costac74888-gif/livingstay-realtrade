/* Test-only browser egress guard; complements the server's offline HTTP guard. */
// Do not import Playwright into every terser/npm subprocess. Install the guard
// only when a browser test actually loads it.
const Module = require("node:module");
const load = Module._load;
const guarded = new WeakSet();
Module._load = function(name, ...args) {
  const exports = load.call(this, name, ...args);
  if (name !== "playwright" || guarded.has(exports.chromium)) return exports;
  const {chromium} = exports;
  guarded.add(chromium);
  const original = chromium.launch.bind(chromium);
  chromium.launch = async function(...args) {
  const browser = await original(...args);
  const createContext = browser.newContext.bind(browser);
  browser.newContext = async function(...params) {
    // Exercise visitor UI, not the app's intentional HeadlessChrome 204 block.
    // Explicit mobile/other caller user agents remain unchanged.
    params[0] = {
      userAgent: "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
      ...params[0],
    };
    const context = await createContext(...params);
    await context.route("**/*", route => {
      const host = new URL(route.request().url()).hostname;
      const publicAPI = /(^|\.)data\.go\.kr$|(^|\.)odcloud\.kr$|(^|\.)juso\.go\.kr$|(^|\.)vworld\.kr$/.test(host);
      return publicAPI ? route.abort("blockedbyclient") : route.continue();
    });
    return context;
  };
  return browser;
  };
  return exports;
};
