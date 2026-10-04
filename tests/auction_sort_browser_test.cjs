/* Public-only checks: no accounts, notifications, external API collection or DB writes. */
const { chromium } = require("playwright");
const { execFileSync } = require("node:child_process");
const assert = require("node:assert/strict");

async function main() {
  const browser = await chromium.launch({
    executablePath: execFileSync("which", ["chromium"], { encoding: "utf8" }).trim(),
    args: ["--no-sandbox"],
  });
  const origin = process.env.TEST_BASE_URL || `https://${process.env.REPLIT_DEV_DOMAIN}`;
  try {
    for (const width of [390, 768, 1280]) {
      const page = await browser.newPage({
        viewport: { width, height: 900 },
        ignoreHTTPSErrors: true,
        locale: "ko-KR",
        userAgent: "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
      });
      const errors = [];
      page.on("pageerror", error => errors.push(error.message));
      await page.goto(origin + "/auctions");
      await page.locator(".auction-card").first().waitFor();
      assert.equal(await page.locator('input[type="range"]').count(), 0);
      for (const [sort, field, descending] of [
        ["ratio_asc", "min_bid_ratio", false],
        ["ratio_desc", "min_bid_ratio", true],
        ["failed_asc", "failed_count", false],
        ["failed_desc", "failed_count", true],
      ]) {
        const pending = page.waitForResponse(response => {
          const url = new URL(response.url());
          return url.pathname === "/api/auctions" && url.searchParams.get("sort") === sort;
        });
        await page.locator(`[data-sort="${sort}"]`).click();
        const response = await pending;
        assert.equal(response.status(), 200);
        const url = new URL(response.url());
        for (const key of ["ratio_min", "ratio_max", "failed_min"]) {
          assert.equal(url.searchParams.has(key), false, `hidden filter ${key}`);
        }
        assert.equal(url.searchParams.get("page"), "1");
        const data = await response.json();
        assert.ok(data.ok && data.items.length);
        const values = data.items.map(item => item[field]).filter(value => value != null);
        assert.deepEqual(values, [...values].sort((a, b) => descending ? b - a : a - b));
        assert.equal(await page.locator("#auctionSort").inputValue(), sort);
        assert.equal(await page.locator(`[data-sort="${sort}"]`).getAttribute("aria-pressed"), "true");
        await page.waitForFunction(() => !document.querySelector(".auction-loading"));
      }
      const changed = page.waitForResponse(r => new URL(r.url()).searchParams.get("sort") === "new");
      await page.selectOption("#auctionSort", "new");
      await changed;
      assert.equal(await page.locator('[data-sort][aria-pressed="true"]').count(), 0);
      const reset = page.waitForResponse(r => {
        const url = new URL(r.url());
        return url.pathname === "/api/auctions" && url.searchParams.get("sort") === "deadline";
      });
      await page.locator("#auctionReset").click();
      await reset;
      assert.equal(await page.locator("#auctionSort").inputValue(), "deadline");
      await page.waitForFunction(() => !document.querySelector(".auction-loading"));
      // The pre-existing shared desktop header overflows at tablet widths;
      // verify this change's auction content there, without hiding that separate issue.
      assert.ok(await page.evaluate(width => width === 768
        ? document.querySelector("main").scrollWidth <= document.querySelector("main").clientWidth + 1
        : document.documentElement.scrollWidth <= innerWidth + 1, width));
      assert.deepEqual(errors, []);
      if (width === 390) {
        await page.evaluate(() => document.fonts.ready);
        await page.screenshot({ path: "attached_assets/auction-phase2/numeric-sort-mobile.png" });
      }
      console.log(`PASS ${width}px: four numeric sorts, no hidden ranges, dropdown sync, reset, auction content fits, no JS errors`);
      await page.close();
    }
  } finally {
    await browser.close();
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; });