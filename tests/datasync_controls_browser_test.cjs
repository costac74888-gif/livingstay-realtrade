/* Real board controls in an offline browser; every request is intercepted. */
const fs = require("node:fs");
const assert = require("node:assert/strict");
const {execFileSync} = require("node:child_process");
const {chromium} = require("playwright");
const source = fs.readFileSync("static/admin.html","utf8");
const begin = source.indexOf("    let dataSyncBoardTimer = null;");
const end = source.indexOf("    function showDataSync()",begin);
const templateBegin = source.indexOf("mount.innerHTML = `",end)+"mount.innerHTML = `".length;
const templateEnd = source.indexOf("\n      `;",templateBegin);
const script = source.slice(begin,end);
const html = source.slice(templateBegin,templateEnd);
const css = fs.readFileSync("static/css/main.css","utf8")
  + [...source.matchAll(/<style>([\s\S]*?)<\/style>/g)].map(m=>m[1]).join("\n");
const fixture = JSON.parse(execFileSync("python",["-c",`
import json
from datetime import datetime,timezone
from datasync_board import build_board
now=datetime(2026,10,6,3,tzinfo=timezone.utc)
def rec(d): return {"value":json.dumps(d),"updated_at":now}
meta={
"tx_sync_status":rec({"state":"paused","stop_reason":"daily_cap"}),
"tx_backfill_status":rec({"state":"running"}),
"geocode_sync_status":rec({"state":"idle"}),
"title_info_sync_status":rec({"state":"done","finished_at":now.isoformat()}),
"admin:camping_image_backfill:status":rec({"state":"running"})}
print(json.dumps(build_board(meta,now=now,enabled={})))
`],{encoding:"utf8"}));
const target = fixture.rows.find(r=>r.key==="dsSecTx");
const single = row => ({ok:true,rows:[row],checked_at:fixture.checked_at});
const rowSelector = key => `.ds-board-row[data-key="${key}"]`;
async function answer(page,body,status=200,index=0) {
  return page.evaluate(({body,status,index})=>{
    const req=window.requests.splice(index,1)[0];
    if (!req) throw Error("No intercepted request");
    req.finish({ok:status>=200&&status<300,status,json:async()=>body});
    return req.url;
  },{body,status,index});
}
async function pending(page,part) {
  await page.waitForFunction(part=>window.requests.some(r=>r.url.includes(part)),part);
}
async function tick(page,ms) {
  await page.evaluate(ms=>{
    window.testNow+=ms;
    const due=[...window.timers].filter(([,t])=>t.at<=window.testNow);
    due.forEach(([id,t])=>{window.timers.delete(id);t.fn();});
  },ms);
}
(async()=>{
  const browser=await chromium.launch({
    executablePath:execFileSync("which",["chromium"],{encoding:"utf8"}).trim(),
    args:["--no-sandbox"],
  });
  try {
    for (const width of [1280,390]) {
      const context=await browser.newContext({viewport:{width,height:900}});
      await context.route("**/*",route=>route.abort());
      const page=await context.newPage();
      const errors=[];
      page.on("pageerror",e=>errors.push(e.message));
      await page.setContent(`<style>${css}</style><main id="mount" style="padding:12px"></main>`);
      await page.evaluate(({html,script})=>{
        window.ADMIN_IS_PRODUCTION_ENV=true;
        window.mount=document.getElementById("mount");
        window.testNow=Date.now();
        Date.now=()=>window.testNow;
        window.calls=[];window.requests=[];window.intervals=[];window.timers=new Map();
        window.nextTimer=0;window.cleared=[];window.confirmTexts=[];window.accept=true;
        window.setTimeout=(fn,ms)=>{const id=++window.nextTimer;window.timers.set(id,{fn,ms,at:window.testNow+ms});return id;};
        window.clearTimeout=id=>window.timers.delete(id);
        window.setInterval=(fn,ms)=>{window.intervals.push({fn,ms});return window.intervals.length;};
        window.clearInterval=id=>window.cleared.push(id);
        window.fetch=(url,options)=>{
          window.calls.push({url,options});
          return new Promise(finish=>window.requests.push({url,options,finish}));
        };
        window.confirm=text=>{window.confirmTexts.push(text);return window.accept;};
        window.mount.innerHTML=window.eval("`"+html+"`");
        window.eval(script+"\nwindow.loadDataSyncBoard=loadDataSyncBoard;window.runDataSyncBoardAction=runDataSyncBoardAction;window.startDataSyncBoardUpdates=startDataSyncBoardUpdates;");
        window.startDataSyncBoardUpdates();
        window.scrollTargets=[];
        document.querySelectorAll('[id^="dsSec"]').forEach(n=>{
          n.scrollIntoView=()=>window.scrollTargets.push(n.id);
        });
      },{html,script});
      await answer(page,fixture);
      await page.locator(".ds-board-row").first().waitFor();
      assert.equal(await page.locator(".ds-board-row").count(),24);
      assert.equal(await page.locator(`${rowSelector("dsSecTitle")} button`).count(),0,"Completed hides retry");
      assert.equal(await page.locator(`${rowSelector("dsSecStores")} button`).count(),0,"Unknown hides retry");
      assert.ok(await page.locator(`${rowSelector("dsSecCampingImages")} button`).isDisabled());
      assert.match(await page.locator(rowSelector("dsSecBrhub")).innerText(),/버튼 없음/);
      assert.equal(await page.locator(`${rowSelector("dsSecRuralHanokTrades")} button`).count(),0);
      const run=page.locator(`${rowSelector("dsSecTx")} .ds-board-run`);
      assert.ok((await run.boundingBox()).height>=36);
      await run.click();
      await pending(page,"?key=dsSecTx");
      assert.ok(await run.isDisabled());
      // Busy lock must hold even if another caller bypasses the disabled DOM.
      await page.evaluate(row=>window.runDataSyncBoardAction(row),target);
      assert.equal(await page.evaluate(()=>window.requests.length),1);
      await answer(page,single(target));
      await pending(page,"/action");
      assert.equal(await page.evaluate(()=>window.scrollTargets.length),0);
      const confirmation=(await page.evaluate(()=>window.confirmTexts))[0];
      assert.match(confirmation,/최근 실거래을\(를\).*외부 API 호출.*진행할까요/);
      assert.match(confirmation,/오늘 한도에 걸려 멈춘 작업입니다/);
      assert.match(confirmation,/같은 API를 공유하는 과거 실거래이 실행 중입니다/);
      const posted=await page.evaluate(()=>window.requests[0].options);
      assert.deepEqual(JSON.parse(posted.body),{key:"dsSecTx",action:"run"});
      await answer(page,{ok:true,message:"DO_NOT_ECHO_RAW_BACKEND_MESSAGE"},202);
      await page.locator(".ds-board-toast.is-success").waitFor();
      assert.doesNotMatch(await page.locator(".ds-board-toast").innerText(),/DO_NOT_ECHO/);
      assert.equal(await page.evaluate(()=>[...window.timers.values()].filter(t=>t.ms===3000).length),1);
      const running={...target,state:"실행 중",quota_paused:false};
      await tick(page,3000);
      await pending(page,"?key=dsSecTx");
      await answer(page,single(running));
      await page.waitForFunction(()=>document.querySelector('.ds-board-row[data-key="dsSecTx"] .ds-board-state').textContent==="실행 중");
      assert.match(await page.locator(".ds-board-summary").innerText(),/0건/);
      // A later full refresh wins over a late targeted response.
      await tick(page,3000);
      await pending(page,"?key=dsSecTx");
      await page.evaluate(()=>{window.loadDataSyncBoard();});
      await pending(page,"/api/admin/datasync-board");
      const completed={...target,state:"완료",quota_paused:false};
      const fresh=structuredClone(fixture);
      fresh.rows[fresh.rows.findIndex(r=>r.key==="dsSecTx")]=completed;
      await answer(page,fresh,200,1);
      await answer(page,single({...target,state:"실패"}));
      assert.equal(await page.locator(`${rowSelector("dsSecTx")} .ds-board-state`).innerText(),"완료");
      // Bound the selective poll to one minute. All polls are single-row GETs.
      for(let i=0;i<18;i++){
        await tick(page,3000);
        const remaining=await page.evaluate(()=>window.requests.length);
        if(remaining) await answer(page,single(completed));
      }
      await tick(page,6000);
      assert.equal(await page.evaluate(()=>window.requests.length),0);
      assert.equal(await page.evaluate(()=>[...window.timers.values()].filter(t=>t.ms===3000).length),0);
      assert.ok((await page.evaluate(()=>window.intervals)).every(t=>t.ms>=60000));
      // Keyboard activation does not bubble to row scroll, and cancel never POSTs.
      const geo=fixture.rows.find(r=>r.key==="dsSecGeo");
      await page.evaluate(()=>window.accept=false);
      const before=await page.evaluate(()=>window.calls.filter(c=>c.options?.method==="POST").length);
      await page.locator(`${rowSelector("dsSecGeo")} button`).focus();
      await page.keyboard.press("Enter");
      await pending(page,"?key=dsSecGeo");
      await answer(page,single(geo));
      await page.waitForFunction(()=>!document.querySelector('.ds-board-row[data-key="dsSecGeo"] button').disabled);
      assert.equal(await page.evaluate(()=>window.calls.filter(c=>c.options?.method==="POST").length),before);
      assert.equal(await page.evaluate(()=>window.scrollTargets.length),0);
      // 409 is visible and still schedules status reconciliation.
      await page.evaluate(()=>window.accept=true);
      await page.locator(`${rowSelector("dsSecGeo")} button`).click();
      await pending(page,"?key=dsSecGeo");
      await answer(page,single(geo));
      await pending(page,"/action");
      await answer(page,{ok:false,message:"DO_NOT_ECHO_PRIVATE"},409);
      await page.waitForFunction(()=>document.querySelector(".ds-board-toast").textContent.includes("이미 실행 중"));
      assert.doesNotMatch(await page.locator(".ds-board-toast").innerText(),/DO_NOT_ECHO/);
      // Navigation clears timers, aborts requests and prevents a late auth redirect.
      await page.locator(`${rowSelector("dsSecGeo")} button`).click();
      await pending(page,"?key=dsSecGeo");
      await page.evaluate(()=>window.mount.replaceChildren());
      await answer(page,{ok:false},401);
      assert.equal(page.url(),"about:blank");
      assert.equal(await page.evaluate(()=>window.timers.size),0);
      assert.ok((await page.evaluate(()=>window.cleared)).length>0);
      assert.ok((await page.evaluate(()=>window.calls)).every(c=>
        c.url==="/api/admin/datasync-board" || c.url==="/api/admin/datasync-board/action"
        || c.url.startsWith("/api/admin/datasync-board?key=")));
      assert.deepEqual(errors,[]);
      await context.close();
    }
    console.log("PASS offline PC/mobile controls: states, unsupported reasons, >=36px, confirmation, quota/shared warnings, exact allowlisted POST, double-click, no scroll propagation, safe toast, cancel, 409, selective 3s/60s cap, stale response and navigation cleanup; no external calls");
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
