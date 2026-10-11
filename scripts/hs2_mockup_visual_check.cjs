/* Read-only checks against the explicitly synthetic development Preview.
 * No login mutation, quote confirmation, booking, payment or provider request.
 */
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const { chromium } = require("playwright");

async function main() {
  assert(process.env.REPLIT_DEV_DOMAIN, "Development domain required");
  const origin = `https://${process.env.REPLIT_DEV_DOMAIN}`;
  const directory = path.resolve("generated-artifacts/mockup-comparison");
  await fs.mkdir(directory, { recursive: true });
  const browser = await chromium.launch({
    executablePath: process.env.HS2_CHROMIUM,
    headless: true, args: ["--no-sandbox", "--disable-gpu"],
  });
  const results = [], errors = [], blocked = [];
  try {
    for (const width of [1440, 390]) {
      const context = await browser.newContext({
        viewport: { width, height: 950 },
        userAgent: "Mozilla/5.0 Chrome/138.0.0.0 Safari/537.36",
      });
      await context.route("**/*", route => {
        const url = new URL(route.request().url());
        if (url.origin === origin || ["data:", "blob:"].includes(url.protocol))
          return route.continue();
        blocked.push(url.origin);
        return route.abort();
      });
      const page = await context.newPage();
      page.on("pageerror", error => errors.push(error.message));
      await page.goto(`${origin}/__development__/status`);
      const status = JSON.parse(await page.locator("body").innerText());
      assert(status.synthetic_data_only && status.database === "owned_ephemeral"
        && !status.actual_toss && !status.external_delivery
        && !status.production_entrypoint, "Not a synthetic Preview");
      let detailURL;
      for (const route of ["/hs2/consumer", "/hs2/search/", "/hs2/search/mobile/"]) {
        await page.goto(origin + route);
        await page.locator(".listing-card").first().waitFor();
        const measured = await page.evaluate(() => ({
          overflow: document.documentElement.scrollWidth > innerWidth + 1,
          brand: document.querySelector(".brand-name")?.textContent,
          heading: getComputedStyle(document.querySelector("h1")).color,
          button: getComputedStyle(document.querySelector(".search-button")).backgroundColor,
          card: getComputedStyle(document.querySelector(".listing-card")).backgroundColor,
          cards: document.querySelectorAll(".listing-card").length,
        }));
        assert(!measured.overflow, `${route} ${width}: horizontal clipping`);
        assert.equal(measured.brand, "HOME & STAY");
        assert(measured.cards > 0, "Nonempty rendered cards required");
        const cardRGB = measured.card.match(/\d+/g)?.map(Number);
        assert(cardRGB?.length === 3 && cardRGB.every(value => value >= 248 && value <= 255),
          `${route} ${width}: reference white/off-white cards (${measured.card})`);
        const headingRGB = measured.heading.match(/\d+/g)?.map(Number);
        assert(headingRGB?.length === 3 && headingRGB[2] > headingRGB[1]
          && headingRGB[1] > headingRGB[0], "Reference blue heading hierarchy");
        // Verify explicit design tokens, independently of functional PASS.
        assert.equal(measured.button, "rgb(178, 138, 49)", "Reference gold search");
        const mode = width === 390 ? "mobile" : "desktop";
        const name = route.includes("/search/mobile") ? "switch-search"
          : route.includes("/search/") ? "map-search" : "consumer";
        await page.screenshot({ path: path.join(directory, `${name}-${mode}.png`), fullPage: true });
        results.push({ route, width, ...measured });
        if (route === "/hs2/search/") {
          await page.locator(".listing-card").first().click();
          const link = page.locator('a[href^="/hs2/details/"]').first();
          await link.waitFor({ state: "visible" });
          detailURL = await link.getAttribute("href");
        }
        if (route === "/hs2/search/mobile/" && width === 390) {
          await page.locator("#mobile-map-btn").click();
          assert.equal(await page.locator("#mobile-map-btn").getAttribute("aria-pressed"), "true");
          await page.screenshot({ path: path.join(directory, "map-switch-mobile.png"), fullPage: true });
        }
      }
      assert(detailURL, "Real detail entry required");
      await page.goto(origin + detailURL);
      await page.locator("#detail-content").waitFor({ state: "visible" });
      assert.equal(await page.locator(".detail-tabs a").count(), 3);
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
        "Detail must not clip horizontally");
      await page.screenshot({ path: path.join(directory,
        `detail-${width === 390 ? "mobile" : "desktop"}.png`), fullPage: true });
      results.push({ route: "/hs2/details/", width, tabs: 3 });
      await context.close();
    }
    assert.deepEqual(errors, [], "Browser runtime errors");
    assert.deepEqual(blocked, [], "Unexpected external browser requests");
    await fs.writeFile(path.join(directory, "visual-check.json"),
      JSON.stringify({ passed: true, results, errors, blocked, actual_provider_validation: false }, null, 2));
    console.log(`DESIGN_CHECK_PASS: ${results.length} route/viewport checks; captures ${directory}`);
  } finally {
    await browser.close();
  }
}
main().catch(error => { console.error(error.message); process.exitCode = 1; });
