/* Exercise the real new admin block offline; no auth bypass or provider calls. */
const fs = require("node:fs");
const assert = require("node:assert/strict");
const {execFileSync} = require("node:child_process");
const {chromium} = require("playwright");

const source = fs.readFileSync("static/admin.html", "utf8");
const previous = execFileSync("git", ["show", "HEAD:static/admin.html"], {encoding:"utf8"});
function template(text) {
  const start = text.indexOf("function showDataSync()");
  const begin = text.indexOf("mount.innerHTML = `", start) + "mount.innerHTML = `".length;
  const end = text.indexOf("\n      `;", begin);
  assert.ok(begin > start && end > begin);
  return text.slice(begin, end);
}
const fullTemplate = template(source);
// Existing cards and their text/actions must remain byte-for-byte identical.
const legacyStart = '          <div class="ds-relay-toolbar">';
assert.equal(fullTemplate.slice(fullTemplate.indexOf(legacyStart)),
             template(previous).slice(template(previous).indexOf(legacyStart)));
const begin = source.indexOf("    let dataSyncBoardTimer = null;");
const end = source.indexOf("    function showDataSync()", begin);
const script = source.slice(begin, end);
const css = fs.readFileSync("static/css/main.css", "utf8")
  + [...source.matchAll(/<style>([\s\S]*?)<\/style>/g)].map(m => m[1]).join("\n");
const fixture = JSON.parse(execFileSync("python", ["-c", `
import json
from datetime import datetime,timezone
from datasync_board import build_board
print(json.dumps(build_board({},now=datetime(2026,10,6,3,0,tzinfo=timezone.utc),enabled={})))
`], {encoding:"utf8"}));
const states = ["완료","실행 중","대기","오래됨","일시중단","실패","확인불가"];
fixture.rows.forEach((r, i) => {
  r.state = states[i % states.length];
  r.action = "상세 카드에서 재개 조건 확인";
});
fixture.rows[0].name = '<img src=x onerror="window.BAD=1">';
fixture.rows[0].last_error_summary = '<script>window.BAD=1</script>';

(async () => {
  const browser = await chromium.launch({
    executablePath: execFileSync("which", ["chromium"], {encoding:"utf8"}).trim(),
    args:["--no-sandbox"],
  });
  try {
    for (const width of [1280,390]) {
      const context = await browser.newContext({viewport:{width,height:900}});
      await context.route("**/*", route => route.abort());
      const page = await context.newPage();
      const errors = [];
      page.on("pageerror", e => errors.push(e.message));
      await page.setContent(`<style>${css}</style><main id="mount" style="max-width:1200px;margin:auto;padding:12px"></main>`);
      await page.evaluate(({html,script}) => {
        window.ADMIN_IS_PRODUCTION_ENV = true;
        window.mount = document.getElementById("mount");
        window.calls = [];
        window.requests = [];
        window.fetch = (url, options) => {
          window.calls.push({url,options});
          return new Promise(resolve => window.requests.push(resolve));
        };
        window.intervals = [];
        window.cleared = [];
        window.setInterval = (fn, ms) => {
          window.intervals.push({fn,ms});
          return window.intervals.length;
        };
        window.clearInterval = id => window.cleared.push(id);
        window.mount.innerHTML = window.eval("`" + html + "`");
        window.eval(script + "\nwindow.startDataSyncBoardUpdates=startDataSyncBoardUpdates; window.loadDataSyncBoard=loadDataSyncBoard;");
        window.startDataSyncBoardUpdates();
        window.scrollTargets = [];
        document.querySelectorAll('[id^="dsSec"]').forEach(node => {
          node.scrollIntoView = () => window.scrollTargets.push(node.id);
        });
      }, {html:fullTemplate,script});
      await page.evaluate(body => window.requests.shift()({ok:true,status:200,json:async () => body}), fixture);
      await page.locator(".ds-board-row").first().waitFor();
      assert.equal(await page.locator(".ds-board-row").count(), fixture.rows.length);
      const count = fixture.rows.filter(r=>["실패","오래됨","일시중단"].includes(r.state)).length;
      assert.match(await page.locator(".ds-board-summary").innerText(), new RegExp(`${count}건`));
      assert.match(await page.locator(".ds-board-time").innerText(), /KST/);
      assert.match(await page.locator(".ds-board-row").first().locator("td").nth(6).innerText(), /자동/);
      assert.match(await page.locator('.ds-board-row[data-key="dsSecTxBackfill"]').locator("td").nth(6).innerText(), /수동/);
      assert.match(await page.locator(".ds-board-row").first().locator("td").nth(3).innerText(), /확인 불가/);
      for (let i=0;i<7;i++) {
        const row = page.locator(".ds-board-row").nth(i);
        assert.equal(await row.locator("td").nth(1).innerText(), states[i]);
        const needsAction = ["오래됨","일시중단","실패"].includes(states[i]);
        assert.equal(await row.locator("td").nth(7).innerText(), needsAction ? fixture.rows[i].action : "—");
      }
      assert.equal(await page.locator("#dsBoard img, #dsBoard script").count(), 0);
      assert.equal(await page.evaluate(()=>window.BAD), undefined);
      await page.locator(".ds-board-row").first().click();
      await page.locator(".ds-board-row").nth(1).focus();
      await page.keyboard.press("Enter");
      await page.keyboard.press("Space");
      assert.deepEqual(await page.evaluate(()=>window.scrollTargets), ["dsSecOnbid","dsSecWeeklyDigest","dsSecWeeklyDigest"]);
      assert.ok((await page.evaluate(()=>window.intervals)).every(i=>i.ms>=60000));
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1), false);
      assert.ok(await page.locator(".ds-board-scroll").evaluate(n=>n.scrollWidth>=n.clientWidth));
      if (width===1280) await page.screenshot({path:"/tmp/datasync-board-desktop.jpg",type:"jpeg",quality:75});
      if (width===390) await page.screenshot({path:"/tmp/datasync-board-mobile.jpg",type:"jpeg",quality:75});
      await page.locator(".ds-board-refresh").click();
      await page.evaluate(()=>window.requests.shift()({ok:false,status:503}));
      await page.locator(".ds-board-error.is-visible").waitFor();
      assert.match(await page.locator(".ds-board-error").innerText(), /이전 조회/);
      // Latest request wins.
      await page.evaluate(()=>{window.loadDataSyncBoard();window.loadDataSyncBoard();});
      await page.evaluate(body => window.requests.pop()({ok:true,status:200,json:async()=>body}), fixture);
      await page.evaluate(()=>window.requests.shift()({ok:false,status:500}));
      assert.equal(await page.locator(".ds-board-error.is-visible").count(), 0);
      assert.equal(await page.locator(".ds-board-row").count(), fixture.rows.length);
      await page.evaluate(()=>{window.loadDataSyncBoard();window.mount.replaceChildren();});
      await page.evaluate(()=>window.requests.shift()({ok:false,status:401}));
      assert.deepEqual(errors, []);
      assert.ok((await page.evaluate(()=>window.calls)).every(c=>c.url==="/api/admin/datasync-board"));
      assert.ok((await page.evaluate(()=>window.cleared)).length>=1, "Timer cleaned on navigation");
      await context.close();
    }
    console.log("PASS actual new board: 24 rows and 23 unchanged cards, PC/mobile, seven states, null values, next-run text, advice, click/keyboard, XSS, 60s timer cleanup, failed/stale responses; zero provider calls");
  } finally { await browser.close(); }
})().catch(e=>{console.error(e);process.exit(1);});
