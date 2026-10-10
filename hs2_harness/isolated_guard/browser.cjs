"use strict";
const cp = require("node:child_process");
const net = require("node:net");
const http = require("node:http");
const https = require("node:https");
const dns = require("node:dns");
const origin = new URL(process.env.HS2_FIXTURE_ORIGIN || "http://invalid");
if (origin.hostname !== "127.0.0.1" || !origin.port || !process.env.HS2_CHROMIUM) throw Error("Owned browser fixture required");
const deny = () => { throw Error("HS2 browser: external network/process forbidden"); };
const spawn = cp.spawn;
cp.spawn = (file, args, options) => {
  if (file !== process.env.HS2_CHROMIUM || !args.includes("--no-sandbox")) return deny();
  return spawn(file,args,options);
};
for (const name of ["exec","execSync","execFile","execFileSync","spawnSync","fork"]) cp[name]=deny;
const connect = net.Socket.prototype.connect;
net.Socket.prototype.connect = function(...args) {
  const options = args[0];
  if (!options || typeof options !== "object" || options.host !== origin.hostname || Number(options.port)!==Number(origin.port)) return deny();
  return connect.apply(this,args);
};
const allowed = value => {
  const url = typeof value === "string" || value instanceof URL ? new URL(value) : new URL(`http://${value.hostname || value.host}:${value.port || 80}`);
  if (url.origin!==origin.origin) deny();
};
for (const name of ["request","get"]) { const fn=http[name]; http[name]=function(...args){allowed(args[0]);return fn.apply(this,args);}; https[name]=deny; }
for (const name of ["lookup","resolve","resolve4","resolve6"]) dns[name]=deny;
