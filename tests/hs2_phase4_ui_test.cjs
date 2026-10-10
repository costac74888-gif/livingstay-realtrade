/* Actual private Chromium + signed session mode API, never live OAuth/accounts. */
const assert = require("node:assert/strict");
const {chromium} = require("playwright");
const origin = process.env.HS2_FIXTURE_ORIGIN;

async function run() {
  assert(origin && /^http:\/\/127\.0\.0\.1:\d+$/.test(origin));
  assert.throws(() => require("node:https").get("https://example.com"));
  const browser = await chromium.launch({executablePath: process.env.HS2_CHROMIUM,
    args:["--no-sandbox","--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1"]});
  let assertions = 2;
  try {
    for (const width of [1280,390]) {
      const page = await browser.newPage({viewport:{width,height:900},
        userAgent:"Mozilla/5.0 Chrome/138.0.0.0 Safari/537.36"});
      const errors = [], outside = [];
      page.on("pageerror", e => errors.push(e.message));
      let posts = 0;
      page.on("request", r => { if(r.url().endsWith("/hs2/api/email-login")) posts++; });
      await page.route("**/*", r => {
        const u = new URL(r.request().url());
        if(u.origin !== origin){ outside.push(u.origin); return r.abort(); }
        if(!u.pathname.startsWith("/hs2/")) return r.abort();
        return r.continue();
      });
      await page.goto(origin + "/hs2/mode");
      await page.waitForFunction(() => document.querySelector("#sessionBadge").textContent.includes("로그아웃"));
      assert(await page.locator("#emailLoginForm").isVisible());
      assert.equal(await page.locator("#kakaoLoginLink").getAttribute("href"), "/auth/kakao/start");
      assert((await page.locator("body").textContent()).includes("개발"));
      assert((await page.evaluate(() => document.documentElement.scrollWidth)) <= width); assertions += 4;
      await page.locator("#loginEmail").fill("business@example.test");
      await page.locator("#loginPassword").fill("wrong");
      await page.locator("#emailLoginButton").click();
      await page.waitForFunction(() => !document.querySelector("#feedback").hidden);
      assert((await page.locator("#feedback").textContent()).includes("확인"));
      assert((await page.locator("#sessionBadge").textContent()).includes("로그아웃")); assertions += 2;
      await page.locator("#loginPassword").fill("Synthetic-only-123!");
      await page.locator("#emailLoginButton").focus();
      await page.keyboard.press("Enter");
      await page.waitForFunction(() => document.querySelectorAll(".business-choice").length === 2);
      assert.equal(await page.locator(".business-choice").count(), 2);
      assert(await page.locator("#emailAuthPanel").isHidden());
      assert.equal(await page.locator("#loginPassword").inputValue(), ""); assertions += 3;
      await page.locator(".business-choice").last().click();
      await page.waitForFunction(() => document.querySelector("#currentBusinessName").textContent.includes("B"));
      assert((await page.locator("#currentModeName").textContent()).includes("사업자"));
      assert.equal(await page.locator(".business-choice").last().getAttribute("aria-pressed"), "true"); assertions += 2;
      await page.locator(".business-choice").first().focus();
      await page.keyboard.press("Enter");
      await page.waitForFunction(() => document.querySelector("#currentBusinessName").textContent.includes("A"));
      assert.equal(await page.locator(".business-choice").first().getAttribute("aria-pressed"), "true"); assertions++;
      await page.locator("#consumerModeButton").click();
      await page.waitForFunction(() => document.querySelector("#currentModeName").textContent.includes("일반회원"));
      assert.equal(await page.locator("#consumerModeButton").getAttribute("aria-pressed"), "true"); assertions++;
      // Controlled upstream error, not a successful mocked login.
      await page.route("**/hs2/api/mode", async r => {
        if(r.request().method() === "POST")
          return r.fulfill({status:503,contentType:"application/json",
            body:JSON.stringify({ok:false,message:"모드 확인 실패"})});
        return r.continue();
      });
      await page.locator(".business-choice").last().click();
      await page.waitForFunction(() => document.querySelector("#feedback").textContent.includes("실패"));
      assert((await page.locator("#currentModeName").textContent()).includes("일반회원")); assertions++;
      await page.unroute("**/hs2/api/mode");
      await page.locator("#logoutButton").click();
      await page.waitForFunction(() => document.querySelector("#sessionBadge").textContent.includes("로그아웃"));
      assert(await page.locator("#emailLoginForm").isVisible());
      assert.equal(await page.locator(".business-choice:visible").count(), 0); assertions += 2;
      await page.route("**/hs2/api/mode", r => r.fulfill({
        status:503,contentType:"application/json",body:'{"ok":false,"message":"계정 확인 불가"}'}));
      await page.reload();
      await page.locator("#unavailablePanel").waitFor({state:"visible"});
      assert(await page.locator("#retryButton").isVisible());
      await page.unroute("**/hs2/api/mode");
      await page.locator("#retryButton").click();
      await page.waitForFunction(() => document.querySelector("#sessionBadge").textContent.includes("로그아웃"));
      assert(await page.locator("#emailLoginForm").isVisible()); assertions += 2;
      assert.equal(posts, 2);
      assert.deepEqual(errors, []);
      assert.deepEqual(outside, []);
      assert.equal(await page.evaluate(() => localStorage.length + sessionStorage.length), 0); assertions += 4;
      await page.close();
    }
  } finally { await browser.close(); }
  console.log(`HS2_UI_PASS phase4 ${assertions} assertions; desktop/mobile, signed API, no real OAuth/accounts.`);
}
run().catch(e => { console.error(e.stack); process.exitCode = 1; });
