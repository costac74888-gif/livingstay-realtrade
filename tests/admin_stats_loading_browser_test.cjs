/* Exercise the real loading functions without admin sign-in or service calls. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const {execFileSync} = require("node:child_process");
const {chromium} = require("playwright");
const html = fs.readFileSync("static/admin.html", "utf8");
function extract(signature) {
  const start=html.indexOf(signature);
  const end=html.indexOf("\n    }",start)+6;
  assert.ok(start>=0 && end>start,signature);
  return html.slice(start,end);
}
const tableCode=extract("async function loadBldFullStats(attempt = 0) {");
const dashboardCode=extract("async function showStats(menuKey) {");
(async()=>{
  const browser=await chromium.launch({
    executablePath:execFileSync("which",["chromium"],{encoding:"utf8"}).trim(),
    args:["--no-sandbox"],
  });
  try {
    const page=await browser.newPage();
    await page.route("**/*",route=>route.abort());
    await page.setContent('<div id="bldFullStats"></div>');
    await page.evaluate(code=>window.eval(code),tableCode);
    await page.evaluate(async()=>{
      window.requests=0;
      window.fetch=async()=>({ok:true,json:async()=>++requests===1
        ? {ok:true,status:"warming",rows:[{type:"전체",building_count:10}]}
        : {ok:true,rows:[{type:"전체",building_count:10,favorites:7}]}});
      await loadBldFullStats();
    });
    assert.match(await page.locator("#bldFullStats").innerText(),/요약을 먼저 표시/);
    await page.waitForFunction(()=>window.requests===2);
    assert.doesNotMatch(await page.locator("#bldFullStats").innerText(),/백그라운드에서 준비/);
    await page.evaluate(async()=>{
      window.fetch=async()=>{throw new Error("offline")};
      await loadBldFullStats();
    });
    assert.match(await page.locator("#bldFullStats").innerText(),/불러오지 못했습니다/);
    assert.equal(await page.getByRole("button",{name:"다시 불러오기"}).count(),1);
    await page.evaluate(async()=>{
      window.fetch=async()=>({ok:true,json:async()=>({ok:true,status:"warming",rows:[]})});
      await loadBldFullStats(12);
      clearTimeout(document.getElementById("bldFullStats")._statsRetryTimer);
    });
    await page.setContent('<div id="grid"></div>');
    await page.evaluate(code=>{
      window.mount=document.getElementById("grid");
      window.destroyStatsCharts=()=>{};
      window.loadPartnerBuildingCounts=()=>{};
      window.renderActionCenter=d=>JSON.stringify(d);
      window.renderDashboardOverview=d=>JSON.stringify(d);
      window.bindActionCenter=()=>{};
      window.bindDashboardOverview=()=>{};
      window.renderStats=()=>{
        window.rendered=true;
        mount.innerHTML='<div id="dashboardActionSlot">waiting</div><div id="dashboardOverviewSlot">waiting</div><input id="keepChartCondition" value="unchanged">';
      };
      window.eval(code);
    },dashboardCode);
    await page.evaluate(async()=>{
      window.fetch=async path=>{
        if(path==="/api/admin/stats" || path==="/api/building-count") {
          return {ok:true,json:async()=>({})};
        }
        return new Promise(resolve=>{
          if(path.endsWith("action-center")) window.resolveAction=resolve;
          else window.resolveOverview=resolve;
        });
      };
      await showStats("stats");
    });
    assert.equal(await page.evaluate(()=>window.rendered),true);
    await page.locator("#keepChartCondition").fill("user edited");
    await page.evaluate(()=>resolveAction({ok:true,json:async()=>({ok:true,total:3})}));
    await page.waitForFunction(()=>document.getElementById("dashboardActionSlot").innerText.includes('"total":3'));
    assert.equal(await page.locator("#keepChartCondition").inputValue(),"user edited");
    await page.evaluate(()=>{
      mount.innerHTML='<div id="otherMenu">different menu</div>';
      resolveOverview({ok:true,json:async()=>({members:{all:5}})});
    });
    await page.waitForTimeout(30);
    assert.equal(await page.locator("#otherMenu").innerText(),"different menu");
    // A pending table response must not repaint a newly selected menu.
    await page.setContent('<div id="bldFullStats"></div>');
    await page.evaluate(()=>{
      window.fetch=()=>new Promise(resolve=>window.resolveTable=resolve);
      window.pendingTable=loadBldFullStats();
      document.body.innerHTML='<div id="otherMenu">table navigation</div>';
      resolveTable({ok:true,json:async()=>({ok:true,rows:[]})});
    });
    await page.evaluate(()=>pendingTable);
    assert.equal(await page.locator("#otherMenu").innerText(),"table navigation");
    console.log("PASS summary/autorefresh, visible retry, independent dashboard panels, preserved inputs and navigation");
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exit(1)});
