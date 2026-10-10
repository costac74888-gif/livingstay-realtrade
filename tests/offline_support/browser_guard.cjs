/* Test-only browser egress guard; complements the server's offline HTTP guard. */
// Do not import Playwright into every terser/npm subprocess. Install the guard
// only when a browser test actually loads it.
const Module = require("node:module");
const ownedOrigin = process.env.OWNED_REGRESSION_ORIGIN;
function requireOwnedURL(value, base = ownedOrigin) {
  if (!ownedOrigin) return;
  const owned = new URL(ownedOrigin);
  if (owned.hostname !== "127.0.0.1" || !owned.port || owned.protocol !== "https:") {
    throw new Error("Invalid owned regression HTTP capability");
  }
  const text = typeof value?.url === "function" ? value.url() : (value?.url || value);
  if (new URL(String(text), base).origin !== owned.origin) {
    throw new Error("Regression HTTP request outside owned origin denied");
  }
}
function guardAPI(context, base) {
  if (!ownedOrigin) return context;
  for (const method of ["get", "post", "put", "patch", "delete", "head", "fetch"]) {
    const original = context[method].bind(context);
    context[method] = function(url, ...args) {
      requireOwnedURL(url, base);
      return original(url, ...args);
    };
  }
  return context;
}
if (ownedOrigin) {
  const nativeFetch = globalThis.fetch;
  globalThis.fetch = function(url, ...args) {
    requireOwnedURL(url);
    return nativeFetch.call(this, url, ...args);
  };
  for (const protocol of ["http", "https"]) {
    const transport = require("node:" + protocol);
    for (const method of ["request", "get"]) {
      const original = transport[method];
      transport[method] = function(target, ...args) {
        const url = typeof target === "string" || target instanceof URL ? target :
          `${target.protocol || protocol + ":"}//${target.hostname || target.host}${target.port ? ":" + target.port : ""}${target.path || "/"}`;
        requireOwnedURL(url);
        return original.call(this, target, ...args);
      };
    }
  }
}
const load = Module._load;
const guarded = new WeakSet();
Module._load = function(name, ...args) {
  const exports = load.call(this, name, ...args);
  if (name !== "playwright" || guarded.has(exports.chromium)) return exports;
  const {chromium} = exports;
  guarded.add(chromium);
  if (ownedOrigin) {
    const newRequestContext = exports.request.newContext.bind(exports.request);
    exports.request.newContext = async function(options = {}) {
      const opts = {baseURL: ownedOrigin, ignoreHTTPSErrors: true, ...options};
      requireOwnedURL(opts.baseURL);
      return guardAPI(await newRequestContext(opts), opts.baseURL);
    };
  }
  const original = chromium.launch.bind(chromium);
  chromium.launch = async function(...args) {
  const browser = await original(...args);
  const createContext = browser.newContext.bind(browser);
  browser.newContext = async function(...params) {
    // Exercise visitor UI, not the app's intentional HeadlessChrome 204 block.
    // Explicit mobile/other caller user agents remain unchanged.
    params[0] = {
      userAgent: "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
      ...(process.env.OWNED_REGRESSION_ORIGIN ? {ignoreHTTPSErrors: true} : {}),
      ...params[0],
    };
    const context = await createContext(...params);
    guardAPI(context.request, params[0]?.baseURL || ownedOrigin);
    await context.route("**/*", route => {
      if (process.env.OWNED_REGRESSION_ORIGIN) {
        const url = new URL(route.request().url());
        if (!["data:", "blob:"].includes(url.protocol) &&
            url.origin !== process.env.OWNED_REGRESSION_ORIGIN) {
          return route.abort("blockedbyclient");
        }
      }
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
