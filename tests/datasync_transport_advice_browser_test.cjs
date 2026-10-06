/* Real board UI, synthetic saved evidence, network blocked on every viewport. */
const fs = require("node:fs");
const assert = require("node:assert/strict");
const {execFileSync} = require("node:child_process");
const {chromium} = require("playwright");
const source = fs.readFileSync("static/admin.html", "utf8");
const start = source.indexOf("function showDataSync()");
const begin = source.indexOf("mount.innerHTML = `", start) + "mount.innerHTML = `".length;
const end = source.indexOf("\n      `;", begin);
const html = source.slice(begin, end);
const script = source.slice(source.indexOf("    let dataSyncBoardTimer = null;"), start);
const css = [...source.matchAll(/<style>([\s\S]*?)<\/style>/g)].map(m => m[1]).join("\n");
const fixture = JSON.parse(execFileSync("python", ["-c", `
import json
from datetime import datetime,timezone,timedelta
from datasync_board import build_board
now=datetime(2026,10,6,4,tzinfo=timezone.utc)
def rec(error):
 return {"value":json.dumps({"state":"failed","error":error,"finished_at":now.isoformat()}),"updated_at":now}
meta={"brhub_sync_status":rec("ConnectionError"),"title_info_sync_status":rec("timeout"),"tx_sync_status":rec("timeout")}
snapshot={"bldg_hub":{"enabled":False},"rtms":{"enabled":True,"last_success_at":(now-timedelta(hours=1)).isoformat(),"last_error_code":"UPSTREAM_TIMEOUT","last_error_at":now.isoformat()}}
print(json.dumps(build_board(meta,now=now,enabled={"rtms":True},relay_snapshot=snapshot)))
`], {encoding:"utf8"}));

(async () => {
  const browser = await chromium.launch({
    executablePath:execFileSync("which", ["chromium"], {encoding:"utf8"}).trim(),
    args:["--no-sandbox"],
  });
  try {
    for (const width of [1280,390]) {
      const context = await browser.newContext({viewport:{width,height:1000}});
      await context.route("**/*", route=>route.abort());
      const page = await context.newPage();
      const errors = [];
      page.on("pageerror", e=>errors.push(e.message));
      await page.setContent(`<style>${css}</style><main id="mount" style="max-width:1200px;margin:auto;padding:12px"></main>`);
      await page.evaluate(({html,script,fixture})=>{
        window.ADMIN_IS_PRODUCTION_ENV = true;
        window.mount = document.getElementById("mount");
        window.calls = []; window.intervals = []; window.scrollTargets = []; window.panelScrolls = 0;
        window.fetch = async url => {
          window.calls.push(url);
          return {ok:true,status:200,json:async()=>fixture};
        };
        window.setInterval = (fn,ms)=>{window.intervals.push(ms);return window.intervals.length;};
        window.clearInterval = ()=>{};
        window.mount.innerHTML = window.eval("`"+html+"`");
        document.querySelectorAll('[id^="dsSec"]').forEach(n=>{
          n.scrollIntoView=()=>window.scrollTargets.push(n.id);
        });
        document.querySelector(".ds-board-guidance").scrollIntoView=()=>window.panelScrolls++;
        window.eval(script+"\nwindow.startDataSyncBoardUpdates=startDataSyncBoardUpdates;window.updateDataSyncBoardRow=updateDataSyncBoardRow;");
        window.startDataSyncBoardUpdates();
      }, {html,script,fixture});
      await page.locator(".ds-board-row").first().waitFor();
      assert.equal(await page.locator(".ds-board-row").count(),24);
      assert.deepEqual(await page.locator(".ds-board-table th").allTextContents(),
        ["데이터","상태","마지막 성공","오늘 호출 / 한도","연결 방식","연결 판단","다시 실행","지금 할 일"]);
      assert.match(await page.locator(".ds-board-review-count").innerText(), /중계 전환 검토 2건/);
      assert.match(await page.locator(".ds-board-relay-error-count").innerText(), /중계 오류 3건/);
      const observation = await page.locator(".ds-board-relay-observation").innerText();
      for (const text of ["이 웹 서버", "건축HUB", "실거래", "마지막 성공", "마지막 오류 코드", "정기 실행 서버 설정은 별도 확인 필요"]) assert.ok(observation.includes(text), text);
      const title = page.locator('.ds-board-row[data-key="dsSecTitle"]');
      const badge = title.locator("button.ds-board-advice-badge");
      assert.equal(await badge.evaluate(n=>getComputedStyle(n).backgroundColor),"rgb(255, 242, 214)");
      assert.ok(await badge.evaluate(n=>n.getBoundingClientRect().height>=36));
      assert.equal(await page.locator('.ds-board-row[data-key="dsSecTx"] .ds-board-advice-badge').evaluate(n=>getComputedStyle(n).backgroundColor),"rgb(253, 233, 230)");
      await badge.click();
      const panel = page.locator(".ds-board-guidance");
      assert.equal(await panel.getAttribute("aria-hidden"),"false");
      assert.equal(await panel.locator("li").count(),5);
      const guidance = await panel.innerText();
      for (const text of ["직접 연결", "외부 API 응답 시간 초과", "연속 횟수 미확인", "RELAY_USE_BLDG_HUB", "RELAY_ENABLED", "Scheduled deployment", "자동으로 직접 호출로 되돌아가는 기능은 없습니다"]) assert.ok(guidance.includes(text),text);
      assert.deepEqual(await page.evaluate(()=>window.scrollTargets),[]);
      assert.equal(await page.evaluate(()=>window.panelScrolls),1);
      await panel.locator("button").click();
      assert.equal(await panel.getAttribute("aria-hidden"),"true");
      await title.locator(".ds-board-name").click();
      assert.equal(await panel.getAttribute("aria-hidden"),"false");
      assert.deepEqual(await page.evaluate(()=>window.scrollTargets),["dsSecTitle"]);
      await title.focus(); await page.keyboard.press("Enter");
      assert.deepEqual(await page.evaluate(()=>window.scrollTargets),["dsSecTitle","dsSecTitle"]);
      const updated = structuredClone(fixture.rows.find(r=>r.key==="dsSecTitle"));
      updated.transport_advice.verdict="직접 유지";
      updated.transport_advice.reason='안전한 문구 <img src=x onerror="window.BAD=1">';
      updated.transport_advice.steps=[];
      await page.evaluate(row=>window.updateDataSyncBoardRow(row),updated);
      assert.match(await page.locator(".ds-board-review-count").innerText(),/1건/);
      assert.match(await panel.innerText(),/직접 유지/);
      assert.equal(await page.locator("#dsBoard img, #dsBoard script").count(),0);
      assert.equal(await page.evaluate(()=>window.BAD),undefined);
      assert.equal(await page.locator(".ds-board-guidance input, .ds-board-guidance select, .ds-board-guidance a").count(),0);
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
      assert.ok((await page.evaluate(()=>window.intervals)).every(ms=>ms>=60000));
      assert.deepEqual(await page.evaluate(()=>window.calls),["/api/admin/datasync-board"]);
      assert.deepEqual(errors,[]);
      await page.screenshot({path:`/tmp/datasync-advice-${width}.jpg`,type:"jpeg",quality:75});
      await context.close();
    }
    console.log("PASS phase 3 offline desktop/mobile: 24 rows, verdict colors, counts, local scope, 5-step manual guidance, row/keyboard navigation, >=36px advice button, targeted update, XSS, no settings form/probes");
  } finally { await browser.close(); }
})().catch(e=>{console.error(e);process.exit(1);});
