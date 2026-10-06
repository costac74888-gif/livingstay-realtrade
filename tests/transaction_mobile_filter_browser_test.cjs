/* Read-only layout regression: preserve the search controls and mobile type. */
const { chromium } = require("playwright");
const { execFileSync } = require("node:child_process");
const assert = require("node:assert/strict");
const origin = process.env.TEST_BASE_URL || `https://${process.env.REPLIT_DEV_DOMAIN}`;

async function main() {
  const browser = await chromium.launch({
    executablePath: execFileSync("which", ["chromium"], { encoding: "utf8" }).trim(),
    args: ["--no-sandbox"],
  });
  try {
    for (const width of [360, 390, 430, 520, 1280]) {
      const page = await browser.newPage({
        viewport: { width, height: 900 }, ignoreHTTPSErrors: true,
        userAgent: "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
      });
      await page.route("**/api/**", route => route.request().method() === "GET"
        ? route.continue() : route.abort());
      await page.goto(origin + "/transactions", { waitUntil: "domcontentloaded" });
      await page.evaluate(() => document.fonts.ready);
      const geometry = await page.evaluate(() => {
        const box = selector => {
          const el = document.querySelector(selector);
          const r = el.getBoundingClientRect();
          return { left: r.left, right: r.right, top: r.top, width: r.width,
            fontSize: parseFloat(getComputedStyle(el).fontSize) };
        };
        return {
          controls: ["#selSiDo", "#selSggNm", "#selUmdNm", "#selLodgingType",
            "#selYear", "#selTransactionScope"].map(box),
          building: box("#inputQ"), button: box("#btnSearch"),
          grid: box(".tx-filter-grid"),
          scroll: document.documentElement.scrollWidth,
        };
      });
      assert.ok(geometry.scroll <= width + 2, `${width}: viewport overflow`);
      if (width <= 520) {
        for (let i = 0; i < 6; i += 2) {
          const [left, right] = geometry.controls.slice(i, i + 2);
          assert.ok(Math.abs(left.top - right.top) < 2, `${width}: paired row ${i}`);
          assert.ok(left.right < right.left, `${width}: column overlap`);
          assert.ok(Math.abs(left.width - right.width) < 2, `${width}: uneven columns`);
          assert.ok(left.fontSize >= 16 && right.fontSize >= 16, "Preserve readable text");
        }
        for (const control of [geometry.building, geometry.button]) {
          assert.ok(Math.abs(control.width - geometry.grid.width) < 2, "Full-width search");
        }
        assert.ok(geometry.building.top > geometry.controls[5].top, "Search follows conditions");
        assert.ok(geometry.button.top > geometry.building.top, "Button follows search");
      } else {
        assert.ok(geometry.controls.every(x => Math.abs(x.top - geometry.controls[0].top) < 2),
          "Desktop stays a single row");
      }
      console.log(`PASS ${width}px transaction filter`);
      await page.close();
    }
  } finally {
    await browser.close();
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
