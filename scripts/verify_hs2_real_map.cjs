/* Live, read-only Preview checks. Never invokes production APIs or payment. */
const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const origin = "https://" + process.env.REPLIT_DEV_DOMAIN;
const out = "generated-artifacts/seongsu-preview";
async function run() {
  const browser = await chromium.launch({
    executablePath: process.env.HS2_CHROMIUM, args: ["--no-sandbox"],
  });
  const results = [], errors = [], failures = [];
  try {
    for (const [name, viewport] of [
      ["pc", { width: 1440, height: 1000 }],
      ["mobile", { width: 390, height: 874 }],
    ]) {
      const page = await browser.newPage({ viewport,
        userAgent: "Mozilla/5.0 Chrome/138.0.0.0 Safari/537.36",
      });
      page.on("pageerror", e => errors.push(e.message));
      page.on("requestfailed", r => failures.push({host: new URL(r.url()).hostname,
        error: r.failure()?.errorText}));
      await page.goto(origin + "/hs2/consumer");
      await page.waitForFunction(() => window.HS2PreviewMap?.state().ready);
      await page.waitForFunction(() =>
        [...document.querySelectorAll("#mapCanvas img")].some(i => i.naturalWidth > 0));
      await page.evaluate(() => document.fonts.ready);
       // The first loaded SDK image can be a logo or an obsolete tile. Wait for
       // actual settled map tiles, not merely naturalWidth on one early image.
       await page.waitForTimeout(2000);
      const initial = await page.evaluate(() => ({
        ...HS2PreviewMap.state(),
        count: document.querySelectorAll(".listing-card").length,
        white: getComputedStyle(document.body).backgroundColor === "rgb(255, 255, 255)",
        titleFont: parseFloat(getComputedStyle(document.querySelector(".listing-title")).fontSize),
        filterFont: parseFloat(getComputedStyle(document.querySelector("#q")).fontSize),
        overflow: document.documentElement.scrollWidth > innerWidth,
        tileCount: [...document.querySelectorAll("#mapCanvas img")].filter(i => i.naturalWidth > 0).length,
        paneWidth: document.querySelector("#resultsPane").getBoundingClientRect().width,
      }));
      assert.equal(initial.markers, 23); assert.equal(initial.count, 23);
      assert.equal(initial.white, true); assert.equal(initial.overflow, false);
      assert(initial.titleFont >= 14 && initial.filterFont >= 14);
      if (name === "pc") assert.equal(initial.paneWidth, 420);
       assert.equal(await page.locator("details.mobile-filter-group").count(), 1);
       if (name === "pc") assert(await page.locator("#kind").isVisible());
      await page.screenshot({path:path.join(out, "real-map-" + name + ".png")});
      await page.locator(".listing-card[data-layer=stay]").first().click();
      await page.locator(".detail-primary").waitFor();
      assert.match(await page.locator(".detail-primary").getAttribute("href"), /^\/hs2\/details\/\?/);
      await page.locator("#detailBack").click();
      await page.locator("[data-layer=sale].layer-button").click();
      await page.waitForFunction(() => HS2PreviewMap.state().markers === 20);
      await page.locator("[data-layer=sale].layer-button").click();
      await page.waitForFunction(() => HS2PreviewMap.state().markers === 23);
      if (name === "mobile") {
        await page.locator("#panelToggle").click();
        assert(await page.locator(".map-workspace").evaluate(el => el.classList.contains("results-collapsed")));
        await page.waitForFunction(() => document.querySelector("#resultsPane").getBoundingClientRect().top
          >= document.querySelector(".map-workspace").getBoundingClientRect().bottom);
        await page.screenshot({path:path.join(out, "real-map-mobile-open.png")});
      }
      await page.locator("#mapTypeTool").click();
      assert.equal(await page.evaluate(() => HS2LegacyMapTools.state().mapType), "skyview");
      await page.locator("#mapTypeTool").click();
      await page.locator("#mapTypeTool").click();
      await page.locator("#measureTool").click();
      await page.evaluate(() => {
        const m = HS2PreviewMap.map();
        kakao.maps.event.trigger(m, "click", {latLng:new kakao.maps.LatLng(37.544,127.052)});
        kakao.maps.event.trigger(m, "click", {latLng:new kakao.maps.LatLng(37.545,127.053)});
      });
      assert.equal(await page.evaluate(() => HS2LegacyMapTools.state().measurePoints), 2);
      await page.locator("#measureReset").click();
      assert.equal(await page.evaluate(() => HS2LegacyMapTools.state().measurePoints), 0);
      await page.locator("#educationTool").click();
      await page.waitForFunction(() => HS2LegacyMapTools.state().poiCount > 0);
      const educationCount = await page.evaluate(() => HS2LegacyMapTools.state().poiCount);
      await page.locator("#convenienceTool").click();
      await page.waitForFunction(() => HS2LegacyMapTools.state().poiCount > 0);
      const convenienceCount = await page.evaluate(() => HS2LegacyMapTools.state().poiCount);
      await page.locator("#subwayTool").click();
      await page.waitForFunction(() => HS2PreviewMap.state().stations > 0);
      const stationCount = await page.evaluate(() => HS2PreviewMap.state().stations);
      results.push({name, ...initial, educationCount, convenienceCount, stationCount,
        tested: ["list_detail_link", "layer_toggle", "actual_map_types", "original_distance_reset",
          "real_education", "real_convenience", "real_stations"]});
      await page.close();
    }
    assert.deepEqual(errors, []);
    fs.writeFileSync(path.join(out,"real-map-checks.json"),JSON.stringify({ok:true,results,errors,failures},null,2));
    console.log(JSON.stringify({ok:true,results,errors,failures}));
  } finally { await browser.close(); }
}
run().catch(e => { console.error(e.message); process.exitCode = 1; });
