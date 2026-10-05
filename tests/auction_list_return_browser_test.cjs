/* Public navigation and visual checks only: no accounts, mutations or API collection. */
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
  fs.mkdirSync("attached_assets/auction-list-return", { recursive: true });
  try {
    for (const width of [390, 1280]) {
      const page = await browser.newPage({ viewport: { width, height: 900 }, ignoreHTTPSErrors: true,
        locale:"ko-KR",userAgent:"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36" });
      const errors = [];
      page.on("pageerror", error => errors.push(error.message));
      await page.goto(origin + "/auctions?page=2&page_size=10&sort=price_desc&status=scheduled&category=생활숙박");
      await page.locator(".auction-row").first().waitFor();
      assert.equal(await page.locator("#auctionCategory").inputValue(), "생활숙박");
      assert.equal(await page.locator("#auctionStatus").inputValue(), "scheduled");
      assert.equal(await page.locator('[aria-current="page"]').textContent(), "2");
      assert.equal(await page.locator('[data-sort-key="price"]').getAttribute("aria-pressed"), "true");
      assert.equal(await page.locator('[data-sort-key="price"] .auction-order-arrow').textContent(), "↓");
      const target = page.locator(".auction-row").nth(8);
      await target.scrollIntoViewIfNeeded();
      const original = { url: page.url(), href: await target.getAttribute("href"), scroll: await page.evaluate(() => scrollY) };
      assert.ok(original.scroll > 0);
      await target.locator(".auction-property").click();
      await page.locator(".auction-panel-general").waitFor();
      assert.equal(new URL(page.url()).searchParams.get("auction_list"), new URL(original.url).pathname + new URL(original.url).search);
      assert.equal(await page.locator("#bTabAuctions").getAttribute("aria-selected"), "true");
      const tabs = await page.locator(".b-detail-tab").allTextContents();
      assert.deepEqual(tabs.map(text => text.trim()), ["부동산정보", "운영정보", "공매정보"]);
      const picture = page.locator("#auctionDetailPhotoHeader .auction-panel-gallery");
      await picture.waitFor();
      const layout = await page.evaluate(() => {
        const photo = document.querySelector("#auctionDetailPhotoHeader").getBoundingClientRect();
        const tabs = document.querySelector(".b-inline-tabs").getBoundingClientRect();
        const style = getComputedStyle(document.querySelector("#bTabAuctions"));
        const nav = getComputedStyle(document.querySelector(".hnav-auctions"));
        return { above: photo.bottom <= tabs.top + 1, tabBackground: style.backgroundColor,
          tabBorder: style.borderTopStyle, navBackground: nav.backgroundColor, navBorder: nav.borderTopStyle };
      });
      assert.ok(layout.above, "Photo is above all three tabs");
      assert.equal(layout.tabBackground, "rgb(61, 89, 72)");
      assert.equal(layout.tabBorder, "solid");
      assert.equal(layout.navBackground, "rgb(61, 89, 72)");
      assert.equal(layout.navBorder, "solid");
      await page.locator("#auctionDetailPhotoHeader [data-photo-index]").first().click();
      assert.ok(await page.locator(".auction-panel-lightbox").isVisible());
      await page.locator("[data-lightbox-close]").click();
      await page.locator("#bTabProperty").click();
      assert.ok(await picture.isVisible());
      await page.locator("#bTabOperations").click();
      assert.ok(await picture.isVisible());
      await page.locator("#bTabAuctions").click();
      await page.evaluate(() => document.fonts.ready);
      await page.screenshot({ path: `attached_assets/auction-list-return/detail-${width}.png`, animations: "disabled" });
      const assertRestored = async () => {
        await page.locator(".auction-row").first().waitFor();
        assert.equal(page.url(), original.url);
        assert.equal(await page.locator("#auctionCategory").inputValue(), "생활숙박");
        assert.equal(await page.locator("#auctionStatus").inputValue(), "scheduled");
        assert.equal(await page.locator('[aria-current="page"]').textContent(), "2");
        assert.equal(await page.locator(".auction-row").nth(8).getAttribute("href"), original.href);
        await page.waitForFunction(y => Math.abs(scrollY - y) < 5, original.scroll);
      };
      await page.locator("[data-auction-panel-back]").click();
      await assertRestored();
      await page.locator(".auction-row").nth(8).click();
      await page.locator(".auction-panel-general").waitFor();
      await page.goBack();
      await assertRestored();

      // Region and district controls must also be reconstructed from list URLs.
      await page.goto(origin + "/auctions?page=1&page_size=20&sort=deadline_desc&region=부산광역시+해운대구&sido=부산광역시&sgg=부산광역시+해운대구");
      await page.waitForFunction(() => document.querySelector("#auctionSgg").value === "부산광역시 해운대구");
      await page.locator(".auction-row").first().waitFor();
      const regionalUrl = page.url();
      await page.locator(".auction-property").first().click();
      await page.locator(".auction-panel-general").waitFor();
      await page.locator("[data-auction-panel-back]").click();
      await page.locator(".auction-row").first().waitFor();
      assert.equal(page.url(), regionalUrl);
      await page.waitForFunction(() => document.querySelector("#auctionSgg").value === "부산광역시 해운대구");
      assert.equal(await page.locator("#auctionSido").inputValue(), "부산광역시");
      assert.equal(await page.locator("#auctionPageSize").inputValue(), "20");
      assert.deepEqual(errors, []);
      console.log(`PASS ${width}px: photo above tabs + lightbox, reference-green auction buttons, page 2 filters/sort/scroll restored with button and browser Back, region/district/page-size restoration`);
      await page.close();
    }
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });