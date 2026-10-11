"use strict";
// Reviewed/hashed tests must remain byte-identical. Redirect their output at
// the browser boundary instead, without changing assertions or transport guards.
// Stay lazy: NODE_OPTIONS also reaches non-browser children.
const Module = require("node:module");
const { artifactPath } = require("./capture_artifacts.cjs");
const load = Module._load;
const types = new WeakSet();
const pages = new WeakSet();
const contexts = new WeakSet();

function capturePage(page) {
  if (pages.has(page)) return;
  pages.add(page);
  for (const method of ["screenshot", "pdf"]) {
    const original = page[method]?.bind(page);
    if (original) page[method] = options => original(options?.path
      ? { ...options, path: artifactPath(options.path) } : options);
  }
}

function captureContext(context) {
  if (contexts.has(context)) return;
  contexts.add(context);
  context.on("page", capturePage);
  for (const page of context.pages()) capturePage(page);
}

Module._load = function(name, ...args) {
  const exports = load.call(this, name, ...args);
  if (name !== "playwright") return exports;
  for (const type of [exports.chromium, exports.webkit, exports.firefox]) {
    if (!type || types.has(type)) continue;
    types.add(type);
    const launch = type.launch.bind(type);
    type.launch = async function(...options) {
      const browser = await launch(...options);
      const newContext = browser.newContext.bind(browser);
      browser.newContext = async function(...params) {
        const context = await newContext(...params);
        captureContext(context);
        return context;
      };
      const newPage = browser.newPage.bind(browser);
      browser.newPage = async function(...params) {
        const page = await newPage(...params);
        captureContext(page.context());
        capturePage(page);
        return page;
      };
      return browser;
    };
  }
  return exports;
};
