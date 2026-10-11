"use strict";
// Trusted-test guard. Mandatory proxy covers redirects, API requests and
// page.route(continue), which can bypass context-level routes.
const Module = require("node:module");
const fs = require("node:fs");
const path = require("node:path");
const net = require("node:net");
const http = require("node:http");
const https = require("node:https");
const cp = require("node:child_process");
const ports = new Set();
const proxyPorts = new Set();
const ownedOrigin = process.env.OWNED_REGRESSION_ORIGIN;
const owned = ownedOrigin || process.env.HOMENSTAY_OWNED_ORIGIN;
if (owned) {
  const url = new URL(owned);
  const protocol = ownedOrigin ? "https:" : "http:";
  if (url.protocol !== protocol || url.hostname !== "127.0.0.1" || !url.port)
    throw Error("FIXTURE_SETUP: literal owned loopback origin required");
  ports.add(Number(url.port));
}
const denied = () => { throw Error("OFFLINE_ISOLATION: external network/process denied"); };
const local = host => ["127.0.0.1", "localhost", "::1"].includes(host);
const allowed = url => ownedOrigin ? url.origin === ownedOrigin :
  local(url.hostname) && ports.has(Number(url.port || 80)) && url.protocol === "http:";
function requireOwnedURL(value, base = ownedOrigin) {
  if (!ownedOrigin) return;
  const text = typeof value?.url === "function" ? value.url() : (value?.url || value);
  if (new URL(String(text), base).origin !== ownedOrigin)
    throw Error("Regression HTTP request outside owned origin denied");
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
const rawRequest = {http: http.request, https: https.request};
if (ownedOrigin) {
  const nativeFetch = globalThis.fetch;
  globalThis.fetch = function(url, ...args) {
    requireOwnedURL(url);
    return nativeFetch.call(this, url, ...args);
  };
  for (const protocol of ["http", "https"]) {
    const transport = protocol === "http" ? http : https;
    for (const method of ["request", "get"]) {
      const original = transport[method];
      transport[method] = function(target, ...args) {
        const requestPath = target.path || "/";
        const text = typeof target === "string" || target instanceof URL ? target :
          `${target.protocol || protocol + ":"}//${target.hostname || target.host}${target.port ? ":" + target.port : ""}${requestPath.startsWith("/") ? requestPath : "/" + requestPath}`;
        const url = new URL(text);
        // Internal Playwright transport may contact the mandatory proxy.
        // That proxy independently validates its ultimate destination.
        if (!(url.protocol === "http:" && url.hostname === "127.0.0.1"
              && proxyPorts.has(Number(url.port)))) requireOwnedURL(url);
        return original.call(this, target, ...args);
      };
    }
  }
}
const listen = net.Server.prototype.listen;
net.Server.prototype.listen = function(...args) {
  const options = args[0];
  if (typeof options === "object") {
    if (options.path || (options.host && !local(options.host))) return denied();
    args[0] = {...options, host: "127.0.0.1"};
  } else if (typeof options === "number") {
    if (typeof args[1] === "string" && !local(args[1])) return denied();
    if (typeof args[1] === "function") args.splice(1, 0, "127.0.0.1");
    else args[1] = "127.0.0.1";
  } else return denied();
  this.once("listening", () => {
    this.__offlinePort = this.address().port;
    ports.add(this.__offlinePort);
  });
  this.once("close", () => {
    if (this.__offlinePort) ports.delete(this.__offlinePort);
  });
  return listen.apply(this, args);
};
const connect = net.Socket.prototype.connect;
net.Socket.prototype.connect = function(...args) {
  const options = Array.isArray(args[0]) ? args[0][0] : net._normalizeArgs(args)[0];
  if (!local(options.host || "localhost") || !ports.has(Number(options.port))) return denied();
  return connect.apply(this, args);
};
for (const method of ["spawn", "spawnSync", "execFile", "execFileSync"]) {
  const original = cp[method];
  cp[method] = function(file, args, ...rest) {
    if (!["python", "python3", "node", "which", "sh", "chromium", "chromium-browser",
          "google-chrome", "npm", "terser", "git"].includes(path.basename(file))) return denied();
    if (path.basename(file) === "git" && !["show", "diff"].includes(args?.[0])) return denied();
    if (path.basename(file) === "sh" &&
        !(args?.[0] === "-c" && /^command -v (chromium|chromium-browser|google-chrome)$/.test(args[1])))
      return denied();
    return original.call(this, file, args, ...rest);
  };
}
cp.exec = cp.execSync = denied;
let proxyPromise;
function proxy() {
  return proxyPromise ||= new Promise(resolve => {
    const server = http.createServer((req, res) => {
      let url;
      try { url = new URL(req.url); } catch { res.writeHead(403); res.end(); return; }
      if (!allowed(url)) { res.writeHead(403); res.end("OFFLINE_ISOLATION"); return; }
      const protocol = url.protocol === "https:" ? "https" : "http";
      const upstream = rawRequest[protocol].call(protocol === "https" ? https : http,
        url, {method: req.method, headers: req.headers},
        response => { res.writeHead(response.statusCode, response.headers); response.pipe(res); });
      upstream.on("error", () => { res.writeHead(502); res.end(); });
      req.pipe(upstream);
    });
    server.on("connect", (req, socket, head) => {
      let url;
      try { url = new URL((ownedOrigin ? "https://" : "http://") + req.url); }
      catch { socket.destroy(); return; }
      if (!allowed(url)) { socket.end("HTTP/1.1 403 Forbidden\r\n\r\n"); return; }
      const upstream = net.connect(Number(url.port), url.hostname, () => {
        socket.write("HTTP/1.1 200 Connection Established\r\n\r\n");
        if (head.length) upstream.write(head);
        socket.pipe(upstream); upstream.pipe(socket);
      });
      upstream.on("error", () => socket.destroy());
      socket.on("error", () => upstream.destroy());
      socket.on("close", () => upstream.destroy());
    });
    server.listen(0, "127.0.0.1", () => {
      proxyPorts.add(server.address().port);
      server.unref();
      resolve(`http://127.0.0.1:${server.address().port}`);
    });
  });
}
const load = Module._load;
const guarded = new WeakSet();
Module._load = function(name, ...args) {
  const exports = load.call(this, name, ...args);
  if (name !== "playwright" || guarded.has(exports.chromium)) return exports;
  const {chromium} = exports;
  guarded.add(chromium);
  const newRequestContext = exports.request.newContext.bind(exports.request);
  exports.request.newContext = async function(options = {}) {
    const server = await proxy();
    const opts = { ...(ownedOrigin ? {baseURL: ownedOrigin, ignoreHTTPSErrors: true} : {}),
      ...options, proxy: {server, bypass: ""}};
    if (ownedOrigin) requireOwnedURL(opts.baseURL);
    return guardAPI(await newRequestContext(opts), opts.baseURL);
  };
  const launch = chromium.launch.bind(chromium);
  chromium.launchPersistentContext = denied;
  chromium.launch = async function(options = {}) {
    const server = await proxy();
    const browser = await launch({...options, proxy: {server, bypass: ""},
      args: [...(options.args || []).filter(a => !/^--proxy/.test(a)),
        "--proxy-bypass-list=<-loopback>"]});
    const contextOptions = params => ({
      userAgent: "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
      ...(ownedOrigin ? {ignoreHTTPSErrors: true} : {}),
      ...params, proxy: {server, bypass: ""}, serviceWorkers: "block",
    });
    async function routes(context) {
      guardAPI(context.request, ownedOrigin);
      const artifactRoot = path.resolve(process.env.HOMENSTAY_OFFLINE_ARTIFACT_DIR
        || path.join(__dirname, "../../..", ".local/suite-audit/browser-artifacts"));
      function retainGeneratedOutput(page) {
        for (const method of ["screenshot", "pdf"]) {
          const original = page[method]?.bind(page);
          if (!original) continue;
          page[method] = options => {
            const root = path.resolve(__dirname, "../../..", "screenshots");
            const output = options?.path && path.resolve(options.path);
            if (output && (output === root || output.startsWith(root + path.sep))) {
              const destination = path.join(artifactRoot, path.relative(root, output));
              fs.mkdirSync(path.dirname(destination), {recursive: true});
              options = {...options, path: destination};
            }
            return original(options);
          };
        }
      }
      context.on("page", retainGeneratedOutput);
      for (const page of context.pages()) retainGeneratedOutput(page);
      await context.route("**/*", route => {
        const url = new URL(route.request().url());
        if (url.hostname === "dapi.kakao.com" && url.pathname === "/v2/maps/sdk.js")
          return route.fulfill({contentType: "text/javascript",
            body: fs.readFileSync(path.join(__dirname, "kakao_sdk.js"), "utf8")});
        if (url.hostname === "cdnjs.cloudflare.com" && /\/Chart\.js\/.*chart\.umd/.test(url.pathname))
          return route.fulfill({contentType: "text/javascript",
            body: fs.readFileSync(require.resolve("chart.js/auto").replace(/auto[/\\]auto\.cjs$/, "dist/chart.umd.js"), "utf8")});
        if (url.hostname === "cdn.jsdelivr.net" &&
            url.pathname === "/npm/chartjs-plugin-datalabels@2.2.0/dist/chartjs-plugin-datalabels.min.js")
          return route.fulfill({contentType: "text/javascript",
            body: fs.readFileSync(require.resolve("chartjs-plugin-datalabels")
              .replace(/chartjs-plugin-datalabels\.js$/, "chartjs-plugin-datalabels.min.js"), "utf8")});
        return allowed(url) ? route.continue() : route.abort("blockedbyclient");
      });
    }
    const newContext = browser.newContext.bind(browser);
    browser.newContext = async params => {
      const context = await newContext(contextOptions(params));
      await routes(context);
      return context;
    };
    const newPage = browser.newPage.bind(browser);
    browser.newPage = async params => {
      const page = await newPage(contextOptions(params));
      await routes(page.context());
      return page;
    };
    return browser;
  };
  return exports;
};
