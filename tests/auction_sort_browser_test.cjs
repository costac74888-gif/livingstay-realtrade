/* Public-only real HTTP/DOM checks; no accounts, notifications or API collection. */
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
        viewport: { width, height: 900 }, ignoreHTTPSErrors: true, locale: "ko-KR",
        userAgent: "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
      });
      const errors = [];
      page.on("pageerror", error => errors.push(error.message));
      await page.goto(origin + "/auctions");
      await page.locator(".auction-card").first().waitFor();
      assert.equal(await page.locator(".auction-card").count(), 10);
      assert.equal(await page.locator("#auctionSearch, #auctionFilterSummary, #auctionSort, .auction-ranges").count(), 0);
      assert.equal(await page.locator(".auction-order-button").count(), 5);
      const request = async (action, check) => {
        const pending = page.waitForResponse(response => {
          const url = new URL(response.url());
          return url.pathname === "/api/auctions" && check(url.searchParams);
        });
        await action();
        const response = await pending;
        assert.equal(response.status(), 200);
        const data = await response.json();
        await page.waitForFunction(() => !document.querySelector(".auction-loading"));
        return data;
      };
      if (width === 1280) {
        for (const [key, field, values] of [
          ["deadline", "bid_end_at", ["deadline_desc", "deadline"]],
          ["appraisal", "appraisal_price", ["appraisal_asc", "appraisal_desc"]],
          ["price", "min_bid_price", ["price_asc", "price_desc"]],
          ["failed", "failed_count", ["failed_asc", "failed_desc"]],
          ["new", "first_seen_at", ["new", "new_asc"]],
        ]) {
          for (const sort of values) {
            const data = await request(() => page.locator(`[data-sort-key="${key}"]`).click(), params => params.get("sort") === sort && params.get("page") === "1");
            const descending = sort.endsWith("_desc") || sort === "new";
            const numbers = data.items.map(item => item[field]).filter(value => value != null);
            const sorted = [...numbers].sort((a, b) => typeof a === "number" ? (descending ? b - a : a - b) : (descending ? b.localeCompare(a) : a.localeCompare(b)));
            assert.deepEqual(numbers, sorted);
            assert.equal(await page.locator(".auction-order-button[aria-pressed=true]").count(), 1);
            assert.equal(await page.locator(`[data-sort-key="${key}"] .auction-order-arrow`).textContent(), descending ? "↓" : "↑");
          }
        }
        for (const size of [20, 50, 100, 10]) {
          const data = await request(() => page.selectOption("#auctionPageSize", String(size)), params => params.get("page_size") === String(size) && params.get("page") === "1");
          assert.equal(data.page_size, size);
          assert.equal(await page.locator(".auction-card").count(), Math.min(size, data.total));
          assert.equal(data.pages, Math.ceil(data.total / size));
        }
        await request(() => page.locator('[data-page="2"]').click(), params => params.get("page") === "2");
        await request(() => page.locator('[data-sort-key="price"]').click(), params => params.get("page") === "1" && params.get("sort") === "price_asc");
        await page.waitForFunction(() => document.querySelector("#auctionSido").options.length > 1);
        await request(() => page.selectOption("#auctionSido", "경기도"), params => params.get("region") === "경기도");
        assert.ok(await page.locator("#auctionSgg option").count() > 1);
        const district = await page.locator("#auctionSgg option").nth(1).getAttribute("value");
        await request(() => page.selectOption("#auctionSgg", district), params => params.get("region") === district);
        await request(() => page.selectOption("#auctionKind", "압류"), params => params.get("kind") === "압류");
        await request(() => page.selectOption("#auctionStatus", "scheduled"), params => params.get("status") === "scheduled");
        await request(() => page.locator('[data-category="호텔"]').click(), params => params.get("category") === "호텔");
      }
      await request(() => page.locator("#auctionReset").click(), params => params.get("sort") === "deadline" && params.get("page_size") === "10" && !params.has("region") && !params.has("category"));
      assert.equal(await page.locator("#auctionPageSize").inputValue(), "10");
      // Shared header has a separately tracked tablet overflow; check auction content there.
      assert.ok(await page.evaluate(width => width === 768
        ? document.querySelector("main").scrollWidth <= document.querySelector("main").clientWidth + 1
        : document.documentElement.scrollWidth <= innerWidth + 1, width));
      assert.deepEqual(errors, []);
      console.log(`PASS ${width}px: compact toolbar, automatic filters/reset, content fits, no JS errors`);
      await page.close();
    }
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });