/* Test-only browser egress guard; complements the server's offline HTTP guard. */
const {chromium} = require("playwright");
const original = chromium.launch.bind(chromium);
chromium.launch = async function(...args) {
  const browser = await original(...args);
  const createContext = browser.newContext.bind(browser);
  browser.newContext = async function(...params) {
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
