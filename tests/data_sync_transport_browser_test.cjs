/* Real admin template/CSS/render code, offline response fixtures only.
   No sign-in bypass, database writes, notifications or provider calls. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const {execFileSync} = require("node:child_process");
const {chromium} = require("playwright");

const source = fs.readFileSync("static/admin.html", "utf8");
const css = fs.readFileSync("static/css/main.css", "utf8")
  + [...source.matchAll(/<style>([\s\S]*?)<\/style>/g)].map(m => m[1]).join("\n");
const start = source.indexOf("function showDataSync()");
const templateStart = source.indexOf("mount.innerHTML = `", start) + "mount.innerHTML = `".length;
const templateEnd = source.indexOf("\n      `;", templateStart);
const initStart = source.indexOf("document.querySelectorAll('[id^=\"dsSec\"]')", templateEnd);
const initEnd = source.indexOf('document.getElementById("brhubSyncRunBtn").addEventListener', initStart);
const statusStart = source.indexOf("async function loadPublicApiRelayStatus() {");
const statusEnd = source.indexOf("async function loadDataSyncBanner()", statusStart);
const scopeStart = source.indexOf("const DATA_SYNC_SCOPE_GUIDES =");
const scopeEnd = source.indexOf("async function loadPendingCompletion()", scopeStart);
assert.ok(templateStart > start && templateEnd > templateStart && initEnd > initStart);
const fixture = JSON.parse(execFileSync("python", ["-c", `
import os,json,tempfile
from pathlib import Path
from unittest.mock import patch
import public_api_client as relay
from data_sync_transport import data_sync_transport_status
with tempfile.TemporaryDirectory() as d, patch.object(relay,'_STATUS_DIR',Path(d)), patch.dict(os.environ,{'RELAY_ENABLED':'1','RELAY_USE_BLDG_HUB':'1','RELAY_USE_RTMS':'0','RELAY_USE_ONBID':'0'}):
 relay._record_status('bldg_hub')
 relay._record_status('rtms','RELAY_FORBIDDEN')
 print(json.dumps(dict(ok=True,**data_sync_transport_status())))
`], {encoding:"utf8"}));

(async () => {
  const browser = await chromium.launch({
    executablePath: execFileSync("which", ["chromium"], {encoding:"utf8"}).trim(),
    args:["--no-sandbox"],
  });
  try {
    for (const width of [1280, 390]) {
      const context = await browser.newContext({viewport:{width,height:900}});
      await context.route("**/*", route => route.abort());
      const page = await context.newPage();
      const errors = [];
      page.on("pageerror", error => errors.push(error.message));
      await page.setContent(`<style>${css}</style><main id="mount" style="max-width:1100px;margin:auto;padding:12px"></main>`);
      await page.evaluate(({template,init,status,scope}) => {
        window.ADMIN_IS_PRODUCTION_ENV = true;
        window.calls = [];
        window.fetch = value => {
          window.calls.push(value);
          return new Promise(resolve => {window.finishFetch = resolve;});
        };
        window.eval(status);
        window.eval(scope + "\nwindow.applyDataSyncScopeGuides = applyDataSyncScopeGuides;");
        document.getElementById("mount").innerHTML = window.eval("`" + template + "`");
        window.eval(init);
      }, {
        template:source.slice(templateStart, templateEnd),
        init:source.slice(initStart, initEnd),
        status:source.slice(statusStart, statusEnd),
        scope:source.slice(scopeStart, scopeEnd),
      });
      assert.equal(await page.locator(".ds-section-routes").count(), 23);
      assert.equal(await page.locator(".ds-route-badge.is-pending").count(), 23);
      await page.evaluate(body => window.finishFetch({ok:true,json:async () => body}), fixture);
      await page.locator("#dsSecBrhub .ds-route-badge").filter({hasText:"중계 ON"}).waitFor();
      assert.match(await page.locator("#dsSecTx .ds-section-routes").innerText(), /실거래 · 중계 OFF/);
      assert.match(await page.locator("#dsSecTx .ds-section-routes").innerText(), /건축HUB.*중계 ON/);
      for (const id of ["dsSecOnbid", "dsSecRealty", "dsSecStores", "dsSecZip"]) {
        assert.equal(await page.locator(`#${id} .ds-route-badge`).innerText(), "직접 연결");
      }
      assert.equal(await page.locator("#dsSecLodgingStaging .ds-route-badge").innerText(), "파일·승인");
      assert.equal(await page.locator("#dsSecLodging .ds-route-badge").innerText(), "사용 중지");
      assert.equal(await page.locator("#dsSecBackup .ds-route-badge").innerText(), "내부 처리");
      assert.equal(await page.locator(".ds-route-badge.is-unknown").count(), 0);
      assert.match(await page.locator("#publicApiRelayStatus").innerText(), /온비드 중계: 꺼짐/);
      const onbidOn = JSON.parse(JSON.stringify(fixture));
      onbidOn.services.onbid.enabled = true;
      onbidOn.sections.dsSecOnbid.routes[0].enabled = true;
      await page.click("#publicApiRelayRefresh");
      await page.evaluate(body => window.finishFetch({ok:true,json:async()=>body}), onbidOn);
      await page.locator("#dsSecOnbid .ds-route-badge.is-on").waitFor();
      assert.equal(await page.locator("#dsSecOnbid .ds-route-badge").innerText(), "중계 ON");
      assert.match(await page.locator("#publicApiRelayStatus").innerText(), /온비드 중계: 켜짐/);
      assert.match(await page.locator("#dsSecTx .ds-route-badge").first().getAttribute("aria-label"), /RELAY_FORBIDDEN/);
      assert.match(await page.locator("#dsSecBrhub .ds-route-badge").getAttribute("title"), /DB 반영/);
      assert.ok(await page.locator("#lodgingSyncRunBtn").isDisabled(), "Legacy scope lock retained");
      assert.ok(await page.locator("#dsSecLodgingStaging").evaluate(
        node => node.classList.contains("ds-scope-locked"),
      ), "Development-only staging lock retained");
      const overflow = await page.locator(".ds-route-badge").evaluateAll(nodes => nodes.some(node => {
        const r = node.getBoundingClientRect();
        return r.left < -1 || r.right > innerWidth + 1;
      }));
      assert.equal(overflow, false, `Badge overflow at ${width}px`);

      // Unknown response is not OFF, even after a prior successful snapshot.
      await page.click("#publicApiRelayRefresh");
      await page.evaluate(() => window.finishFetch({ok:false}));
      await page.locator(".ds-route-badge.is-unknown").first().waitFor();
      assert.equal(await page.locator(".ds-route-badge.is-unknown").count(), 23);
      assert.equal(await page.locator(".ds-route-badge.is-on").count(), 0);
      // Two overlapping requests: ignore the older completion.
      await page.evaluate(() => {window.loadPublicApiRelayStatus();window.oldFinish = window.finishFetch;});
      await page.evaluate(() => {window.loadPublicApiRelayStatus();});
      await page.evaluate(body => window.finishFetch({ok:true,json:async () => body}), fixture);
      await page.locator("#dsSecBrhub .ds-route-badge.is-on").waitFor();
      await page.evaluate(() => window.oldFinish({ok:false}));
      assert.equal(await page.locator("#dsSecBrhub .ds-route-badge").innerText(), "중계 ON");
      // Malformed enabled flag must not be shown as OFF.
      const malformed = structuredClone(fixture);
      delete malformed.sections.dsSecBrhub.routes[0].enabled;
      await page.evaluate(() => {window.loadPublicApiRelayStatus();});
      await page.evaluate(body => window.finishFetch({ok:true,json:async () => body}), malformed);
      await page.locator("#dsSecBrhub .ds-route-badge.is-unknown").waitFor();
      // Navigating away while a response is in flight is safe.
      await page.evaluate(() => {
        window.loadPublicApiRelayStatus();
        document.getElementById("mount").replaceChildren();
      });
      await page.evaluate(body => window.finishFetch({ok:true,json:async () => body}), fixture);
      assert.deepEqual(errors, []);
      assert.ok((await page.evaluate(() => window.calls)).every(url => url === "/api/admin/public-api-relay/status"));
      await context.close();
    }
    console.log("PASS 23 actual admin headings: desktop/mobile, mixed routes, scope locks, failure/unknown, stale responses and navigation; zero external calls");
  } finally {
    await browser.close();
  }
})().catch(error => {console.error(error);process.exit(1);});
