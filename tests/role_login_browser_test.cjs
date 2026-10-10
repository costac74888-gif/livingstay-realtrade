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
let user = null;
let multiple = false;
const general = {id:"general",role:"general",dashboard_url:"/mypage"};
const server = http.createServer(async(req,res) => {
  const url = new URL(req.url,"http://test");
  const json = data => { res.setHeader("Content-Type","application/json"); res.end(JSON.stringify(data)); };
  if (req.method !== "GET") {
    let data = ""; for await (const chunk of req) data += chunk;
    const body = data ? JSON.parse(data) : {};
    calls.push({path:url.pathname,body});
    if (url.pathname === "/api/auth/login" || url.pathname === "/api/agent/login") {
      const role = url.pathname.includes("/agent/") ? "agent" : body.role;
      user = {logged_in:true,name:"검사 회원",account_type:"user",provider:"email",
        active_context:role === "agent" && !multiple ? offices[0] : general,contexts:[general,...offices]};
      return json(role === "agent" && multiple ? {ok:true,select_context:true,contexts:offices}
        : {ok:true,redirect:role === "agent" ? "/agent/dashboard" : "/mypage"});
    }
    if (url.pathname === "/api/auth/context") {
      user.active_context = offices.find(c => c.id === body.context_id);
      return json({ok:true,redirect:"/agent/dashboard"});
    }
    return json({ok:true});
  }
  if (url.pathname === "/api/auth/me") return json(user || {logged_in:false});
  if (url.pathname.startsWith("/api/")) return json({ok:true,items:[],keys:[],contexts:[general,...offices]});
  if (url.pathname === "/agent/login") {
    res.setHeader("Content-Type","text/html");
    return res.end(fs.readFileSync(path.join(root,"static/agent_login.html")));
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
      await ctx.close();
    }
    console.log("PASS shared-password login entries, role dashboards/office badge, selection and reset: desktop/mobile");
  } finally {await browser.close();await new Promise(resolve=>server.close(resolve));}
})().catch(error=>{console.error(error);process.exitCode=1;server.close();});
