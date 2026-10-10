// UI fixtures do not create real accounts, deliver notifications, or bypass app auth.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");
const { execFileSync } = require("node:child_process");
const { chromium } = require("playwright");
const root = path.resolve(__dirname, "..");
const calls = [];
const offices = [1, 2].map(id => ({id:`agent:agents:${id}`,role:"agent",business_id:id,
  business_table:"agents",business_name:`검사 사무소 ${id}`,dashboard_url:"/agent/dashboard"}));
const partnerContexts = {
  operator: [{id:"operator:operators:1",role:"operator",business_id:1,business_table:"operators",business_name:"위탁 업체",dashboard_url:"/operator/dashboard"}],
  loan_consultant: [{id:"loan_consultant:loan_consultants:1",role:"loan_consultant",business_id:1,business_table:"loan_consultants",business_name:"대출 사무소",dashboard_url:"/loan-consultant/dashboard"}],
  lodging_operator: [{id:"lodging_operator:operator_lodging:1",role:"lodging_operator",business_id:1,business_table:"operator_lodging",business_name:"숙박 사업장",dashboard_url:"/lodging-operator/manage"}],
};
const general = {id:"general",role:"general",dashboard_url:"/mypage"};
const everyContext = [general,
  ...offices,...Object.values(partnerContexts).flat()];
let user = null;
let multiple = false;
const server = http.createServer(async(req,res) => {
  const url = new URL(req.url,"http://test");
  const json = data => { res.setHeader("Content-Type","application/json"); res.end(JSON.stringify(data)); };
  if (req.method !== "GET") {
    let data = ""; for await (const chunk of req) data += chunk;
    const body = data ? JSON.parse(data) : {};
    calls.push({path:url.pathname,body});
    if (url.pathname === "/api/auth/login" || url.pathname === "/api/agent/login") {
      const role = url.pathname.includes("/agent/") ? "agent" : body.role;
      const eligible = role === "agent" ? offices : role === "partner"
        ? [...partnerContexts.operator,...partnerContexts.loan_consultant] : (partnerContexts[role] || []);
      const choose = multiple && role !== "general";
      const active = choose || role === "general" ? general : eligible[0];
      user = {logged_in:true,name:"검사 회원",account_type:"user",provider:"email",
        active_context:active,contexts:everyContext};
      return json(choose ? {ok:true,select_context:true,contexts:eligible}
        : {ok:true,redirect:active.dashboard_url});
    }
    if (url.pathname === "/api/auth/context") {
      user.active_context = everyContext.find(c => c.id === body.context_id);
      return json({ok:true,redirect:user.active_context.dashboard_url});
    }
    return json({ok:true});
  }
  if (url.pathname === "/api/auth/me") return json(user || {logged_in:false});
  if (url.pathname.startsWith("/api/")) return json({ok:true,items:[],keys:[],contexts:[general,...offices]});
  if (url.pathname === "/agent/login") {
    res.setHeader("Content-Type","text/html");
    return res.end(fs.readFileSync(path.join(root,"static/agent_login.html")));
  }
  const roleFiles = {"/operator/login":"operator_login.html","/loan-consultant/login":"loan_consultant_login.html",
    "/lodging-operator/login":"partner_login.html","/partner/login":"partner_login.html"};
  if (roleFiles[url.pathname]) {
    res.setHeader("Content-Type","text/html");
    return res.end(fs.readFileSync(path.join(root,"static",roleFiles[url.pathname])));
  }
  if (url.pathname === "/menu") {
    res.setHeader("Content-Type","text/html");
    return res.end(fs.readFileSync(path.join(root,"static/menu.html")));
  }
  if (url.pathname.startsWith("/static/")) {
    const filename = path.resolve(root,"."+url.pathname);
    if (!filename.startsWith(root+"/static/")) {res.writeHead(403);return res.end();}
    try {
      res.setHeader("Content-Type",filename.endsWith(".css") ? "text/css" :
        filename.endsWith(".js") ? "text/javascript" : "image/png");
      return res.end(fs.readFileSync(filename));
    } catch {res.writeHead(404);return res.end();}
  }
  res.setHeader("Content-Type","text/html");
  res.end('<html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><link rel="stylesheet" href="/static/css/main.css"><body><header id="siteHeader"></header><script src="/static/js/header.js"></script><script src="/static/js/auth.js"></script></body></html>');
});
(async()=>{
  await new Promise(resolve=>server.listen(0,"127.0.0.1",resolve));
  const base=`http://127.0.0.1:${server.address().port}`;
  const browser=await chromium.launch({executablePath:execFileSync("which",["chromium"],{encoding:"utf8"}).trim(),args:["--no-sandbox"]});
  try {
    for (const width of [1280,390]) {
      user=null; multiple=false;
      const ctx=await browser.newContext({viewport:{width,height:900}});
      const page=await ctx.newPage();
      const errors=[];page.on("pageerror",e=>errors.push(e.message));
      await page.goto(base+"/?login=general");
      await page.locator("#authModal").waitFor({state:"visible"});
      assert.equal(await page.locator("#authModalTitle").innerText(),"일반회원 로그인");
      assert.equal(await page.locator('a[href="/agent/login"]').count(),1);
      await page.fill("#authEmail","test@example.test");
      await page.fill("#authPassword"," shared-pass-123 ");
      await page.locator('#authForm button[type="submit"]').click();
      await page.waitForURL("**/mypage");
      assert.equal(calls.findLast(c=>c.path==="/api/auth/login").body.role,"general");
      assert.equal(calls.findLast(c=>c.path==="/api/auth/login").body.password," shared-pass-123 ");
      await page.locator(".auth-active-context").waitFor({state:"attached"});
      assert.equal(await page.locator("#headerMypageLink").getAttribute("href"),"/mypage");
      assert.match(await page.locator(".auth-active-context").innerText(),/일반회원/);
      if (width <= 520) {
        await page.click("#hamburgerBtn");await page.waitForURL("**/menu");
        await page.locator("#menuActiveContext").waitFor();
        assert.match(await page.locator("#menuActiveContext").innerText(),/일반회원/);
        assert.equal(await page.locator("#menuMypageLink").getAttribute("href"),"/mypage");
      }
      await page.goto(base+"/agent/login");
      await page.fill("#agentEmail","test@example.test");
      await page.fill("#agentPassword"," shared-pass-123 ");
      await page.click("#loginBtn");
      await page.waitForURL("**/agent/dashboard");
      await page.locator(".auth-active-context").waitFor({state:"attached"});
      assert.equal(calls.findLast(c=>c.path==="/api/agent/login").body.password," shared-pass-123 ");
      assert.match(await page.locator(".auth-active-context").innerText(),/중개사.*검사 사무소 1/);
      assert.equal(await page.locator("#headerMypageLink").getAttribute("href"),"/agent/dashboard");
      if (width <= 520) {
        await page.click("#hamburgerBtn");await page.waitForURL("**/menu");
        await page.locator("#menuActiveContext").waitFor();
        assert.match(await page.locator("#menuActiveContext").innerText(),/중개사.*검사 사무소 1/);
        assert.equal(await page.locator("#menuMypageLink").getAttribute("href"),"/agent/dashboard");
      }
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
      multiple=true;
      await page.goto(base+"/agent/login");
      await page.fill("#agentEmail","test@example.test");await page.fill("#agentPassword","shared-pass-123");
      await page.click("#loginBtn");
      await page.selectOption("#contextChoice","agent:agents:2");
      await page.getByRole("button",{name:"선택한 사무소로 접속"}).click();
      await page.waitForURL("**/agent/dashboard");
      assert.equal(calls.findLast(c=>c.path==="/api/auth/context").body.context_id,"agent:agents:2");
      await page.goto(base+"/?login=reset");
      await page.locator("#authModal").waitFor({state:"visible"});
      assert.equal(await page.locator("#authModalTitle").innerText(),"비밀번호 찾기");
      assert.deepEqual(errors,[]);
      for (const [role, route, dashboard] of [
        ["operator","/operator/login","/operator/dashboard"],
        ["loan_consultant","/loan-consultant/login","/loan-consultant/dashboard"],
        ["lodging_operator","/lodging-operator/login","/lodging-operator/manage"],
        ["partner","/partner/login","/operator/dashboard"],
      ]) {
        multiple=false;user=null;
        await page.goto(base+route);
        assert.equal(await page.locator('a[href="/?login=reset"]').count(),1);
        await page.locator('#loginForm input[autocomplete="username"]').fill("test@example.test");
        await page.locator('input[type="password"]').fill(" shared-pass-123 ");
        await page.check("#rememberLogin");
        await page.click("#loginBtn");
        await page.waitForURL("**"+dashboard);
        const body=calls.findLast(c=>c.path==="/api/auth/login").body;
        assert.equal(body.role,role);
        assert.equal(body.password," shared-pass-123 ");
        assert.equal(body.remember,true);
        await page.locator(".auth-active-context").waitFor({state:"attached"});
        assert.equal(await page.locator("#headerMypageLink").getAttribute("href"),dashboard);
        if (width<=520) {
          await page.goto(base+"/menu");
          await page.locator("#menuActiveContext").waitFor();
          assert.equal(await page.locator("#menuMypageLink").getAttribute("href"),dashboard);
        }
      }
      multiple=true;
      await page.goto(base+"/partner/login");
      await page.locator('#loginForm input[autocomplete="username"]').fill("test@example.test");
      await page.locator('input[type="password"]').fill("shared-pass-123");
      await page.click("#loginBtn");
      await page.selectOption("#contextChoice",partnerContexts.loan_consultant[0].id);
      await page.getByRole("button",{name:"선택한 역할로 접속"}).click();
      await page.waitForURL("**/loan-consultant/dashboard");
      assert.equal(calls.findLast(c=>c.path==="/api/auth/context").body.context_id,partnerContexts.loan_consultant[0].id);
      assert.deepEqual(errors,[]);
      await ctx.close();
    }
    console.log("PASS general/broker/operator/loan/lodging/partner entries, shared password, remember, dashboards and context selection: desktop/mobile");
  } finally {await browser.close();await new Promise(resolve=>server.close(resolve));}
})().catch(error=>{console.error(error);process.exitCode=1;server.close();});
