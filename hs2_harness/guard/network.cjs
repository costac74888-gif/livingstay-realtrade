/* Reviewed offline Node checks only; no HTTP, sockets, workers or subprocesses. */
"use strict";
const denied = () => { throw new Error("HS2 harness: external effects forbidden"); };
for (const name of ["http", "https"]) {
  const mod = require(name);
  mod.request = denied;
  mod.get = denied;
}
const net = require("net");
net.connect = net.createConnection = denied;
net.Socket.prototype.connect = denied;
require("tls").connect = denied;
const dns = require("dns");
for (const key of Object.keys(dns)) {
  if (typeof dns[key] === "function") dns[key] = denied;
}
const child = require("child_process");
for (const key of ["spawn", "spawnSync", "exec", "execSync", "execFile", "execFileSync", "fork"]) child[key] = denied;
require("worker_threads").Worker = class { constructor() { denied(); } };
global.fetch = denied;
global.WebSocket = class { constructor() { denied(); } };
