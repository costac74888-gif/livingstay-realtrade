/* Public real-data navigation only; no writes, sign-ins, notifications or collection. */
const { chromium } = require("playwright");
const { execFileSync } = require("node:child_process");
const fs = require("node:fs");
const assert = require("node:assert/strict");

async function main() {
  const browser = await chromium.launch({
    executablePath: execFileSync("which", ["chromium"], { encoding: "utf8" }).trim(),
    args: ["--no-sandbox"],
  });
  const origin = process.env.TEST_BASE_URL || `https://${process.env.REPLIT_DEV_DOMAIN}`;
  const output = "attached_assets/auction-detail-navigation";
  fs.mkdirSync(output, { recursive: true });
  try {
    for (const width of [390, 1280]) {
      const page = await browser.newPage({
        viewport: { width, height: 900 }, ignoreHTTPSErrors: true, locale: "ko-KR",
        userAgent: "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
      });
      const errors = [];
      page.on("pageerror", error => errors.push(error.message));
      await page.goto(origin + "/auctions");
      await page.locator(".auction-row").first().waitFor();
      const items = await page.evaluate(async () => {
        let items = [];
        for (let page = 1; ; page++) {
          const response = await fetch(`/api/auctions?page_size=100&page=${page}`);
          if (!response.ok) throw new Error("Public auction list unavailable");
          const data = await response.json();
          items.push(...data.items);
          if (page >= data.pages) return items;
        }
      });
      const matched = items.find(item => item.master_building_id);
      const unmatched = items.find(item => !item.master_building_id);
      assert.ok(matched, "Exercise a real linked property");
      assert.ok(unmatched, "Exercise a real unmatched property");
      const href = await page.locator(".auction-row").first().getAttribute("data-auction-href");
      assert.ok(new URL(href, origin).searchParams.has("building"));
      await page.locator(".auction-property").first().click();
      await page.locator(".auction-panel-general").waitFor();
      await page.waitForFunction(() => document.querySelector("#bTabAuctions")?.getAttribute("aria-selected") === "true");
      const checkTabs = async () => {
        for (const [id, text] of [["bTabProperty", "부동산정보"], ["bTabOperations", "운영정보"], ["bTabAuctions", "공매정보"]]) {
          assert.equal((await page.locator("#" + id).textContent()).trim(), text);
          assert.ok(await page.locator("#" + id).isVisible());
        }
        assert.equal(await page.locator(".b-detail-tab[aria-selected=true]").count(), 1);
      };
      await checkTabs();
      assert.ok(await page.evaluate(() => Number(window.__openBuildingId) > 0));
      await page.locator("#bTabProperty").click();
      assert.ok(await page.locator("#bPropertyPanel").isVisible());
      assert.equal(await page.locator(".auction-panel-unmatched-tabs").count(), 0);
      await page.locator("#bTabOperations").click();
      assert.ok(await page.locator("#bOperationsPanel").isVisible());
      await page.locator("#bTabAuctions").click();
      assert.ok(await page.locator(".auction-panel-photo img").count() > 0);
      await page.evaluate(() => document.fonts.ready);
      await page.waitForFunction(() => Number(getComputedStyle(document.querySelector("#bAuctionPanel")).opacity) >= .99);
      await page.screenshot({ path: `${output}/matched-${width}.png`, animations: "disabled" });

      await page.evaluate(id => window.openAuctionDetail(id), unmatched.id);
      await page.locator(".auction-panel-general").waitFor();
      await checkTabs();
      assert.equal(await page.evaluate(() => window.__openBuildingId), null);
      assert.equal(await page.locator("#bTabAuctions").getAttribute("aria-selected"), "true");
      assert.equal(new URL(page.url()).searchParams.get("building"), null);
      await page.locator("#bTabProperty").click();
      assert.ok(await page.locator("#bPropertyPanel").isVisible());
      assert.ok((await page.locator("#bPropertyPanel").textContent()).includes("연결되어 있지 않습니다"));
      await page.locator("#bTabOperations").click();
      assert.ok((await page.locator("#bOperationsPanel").textContent()).includes("미신고 또는 폐업을 의미하지 않습니다"));
      await page.locator("#bTabOperations").press("ArrowRight");
      assert.equal(await page.locator("#bTabAuctions").getAttribute("aria-selected"), "true");
      await page.locator("#bTabAuctions").press("Home");
      assert.equal(await page.locator("#bTabProperty").getAttribute("aria-selected"), "true");
      await page.waitForFunction(() => Number(getComputedStyle(document.querySelector("#bPropertyPanel")).opacity) >= .99);
      await page.screenshot({ path: `${output}/unmatched-${width}.png`, animations: "disabled" });
      await page.evaluate(id => window.openAuctionDetail(id), matched.id);
      await page.locator(".auction-panel-general").waitFor();
      assert.equal(await page.evaluate(() => window.__openBuildingId), matched.master_building_id);
      await checkTabs();
      assert.equal(await page.locator("#bTabAuctions").getAttribute("aria-selected"), "true");
      assert.deepEqual(errors, []);
      console.log(`PASS ${width}px: list → existing detail, real photos, three tabs, unmatched information boundaries, keyboard switching and re-entry`);
      await page.close();
    }
  } finally {
    await browser.close();
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });