const assert = require("node:assert/strict");
const {chromium} = require("playwright");
const origin = process.env.HS2_FIXTURE_ORIGIN;

async function run() {
  assert(origin && /^http:\/\/127\.0\.0\.1:\d+$/.test(origin));
  const browser = await chromium.launch({executablePath:process.env.HS2_CHROMIUM,
    args:["--no-sandbox","--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1"]});
  let checks = 0;
  try {
    for(const width of [1280,390]) {
      const page = await browser.newPage({viewport:{width,height:950}});
      const errors=[],outside=[];
      page.on("pageerror",e=>errors.push(e.message));
      await page.route("**/*",r=>{
        const u=new URL(r.request().url());
        if(u.origin!==origin){outside.push(u.origin);return r.abort();}
        if(!u.pathname.startsWith("/hs2/"))return r.abort();
        return r.continue();
      });
      await page.goto(origin+"/hs2/consumer");
      await page.waitForFunction(()=>document.querySelectorAll(".listing-card").length===3);
      assert(await page.locator("#min_total").isDisabled());
      assert(await page.locator("#max_total").isDisabled());
      assert(await page.locator("#rooms").isDisabled());
      assert(await page.locator("#guests").isDisabled());
      assert.equal(await page.locator(".listing-card").count(),3);checks+=5;
      await page.waitForFunction(()=>document.querySelector("#mapCanvas").dataset.fixtureMap==="true");
      assert(!((await page.locator("body").textContent()).includes("NEVER_PUBLIC")));
      assert((await page.evaluate(()=>document.documentElement.scrollWidth))<=width);checks+=2;
      const prices = await page.locator(".listing-card").allTextContents();
      assert(prices.every(t=>!t.includes("0원")));checks++;
      await page.locator("#check_in").fill("2026-11-01");
      await page.locator("#check_out").fill("2026-11-08");
      assert(await page.locator("#min_total").isEnabled());checks++;
      await page.locator("#min_total").fill("220000");
      await page.locator("#max_total").fill("250000");
      await page.locator(".search-button").click();
      await page.waitForFunction(()=>document.querySelectorAll(".listing-card").length===1);
      assert((await page.locator(".listing-card").textContent()).includes("240,000"));
      assert(new URL(page.url()).searchParams.get("min_total")==="220000");checks+=2;
      await page.locator(".listing-card").focus();await page.keyboard.press("Enter");
      assert(await page.locator("#selectedSummary").isVisible());
      assert.equal(await page.locator(".listing-card").getAttribute("aria-pressed"),"true");checks+=2;
      await page.reload();
      await page.waitForFunction(()=>document.querySelectorAll(".listing-card").length===1);
      assert.equal(await page.locator("#min_total").inputValue(),"220000");checks++;
      await page.locator("#kind").selectOption("non_lodging");
      await page.locator(".search-button").click();
      await page.locator("#emptyPanel").waitFor({state:"visible"});
      assert.equal(await page.locator(".listing-card").count(),0);checks++;
      await page.route("**/hs2/api/consumer/search?*",r=>r.fulfill({
        status:503,contentType:"application/json",body:'{"ok":false,"message":"검색 장애 검증"}'}));
      await page.locator(".search-button").click();
      await page.locator("#errorPanel").waitFor({state:"visible"});
      assert.equal(await page.locator("#min_total").inputValue(),"220000");checks++;
      await page.unroute("**/hs2/api/consumer/search?*");
      await page.locator("#kind").selectOption("all");
      const retry = page.waitForResponse(r=>r.url().includes("/hs2/api/consumer/search?") && r.status()===200);
      await page.locator("#retryButton").click();
      await retry;
      await page.waitForFunction(()=>document.querySelector("#errorPanel").hidden);
      assert.equal(await page.locator(".listing-card").count(),0);checks++;
      await page.locator(".search-button").click();
      await page.waitForFunction(()=>document.querySelectorAll(".listing-card").length===1);
      assert(await page.locator("#errorPanel").isHidden());checks++;
      await page.locator("#check_in").fill("");
      await page.locator("#check_out").fill("");
      assert(await page.locator("#min_total").isDisabled());
      assert.equal(await page.locator("#min_total").inputValue(),"");checks+=2;
      assert.deepEqual(errors,[]);assert.deepEqual(outside,[]);checks+=2;
      await page.close();
    }
  } finally {await browser.close();}
  console.log(`HS2_UI_PASS phase5 ${checks} assertions; real query/DOM/selection, selected-period total, protected metadata, owned SDK interface.`);
}
run().catch(e=>{console.error(e.stack);process.exitCode=1;});
