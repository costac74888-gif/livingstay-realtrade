/* Real legend and admin renderer with offline fixtures; no sign-in bypass. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const {execFileSync} = require("node:child_process");
const {chromium} = require("playwright");
const main = fs.readFileSync("static/js/main.js", "utf8");
const index = fs.readFileSync("static/index.html", "utf8");
const css = fs.readFileSync("static/css/main.css", "utf8");
const admin = fs.readFileSync("static/admin.html", "utf8");
const loadStart = main.indexOf("async function loadBuildingCountLabel(){");
const loadEnd = main.indexOf("\n}\n", loadStart) + 2;
const adminStart = admin.indexOf("async function loadBldFullStats() {");
const adminEnd = admin.indexOf("\n    }", adminStart) + 6;
assert.ok(loadStart > 0 && loadEnd > loadStart && adminEnd > adminStart);

(async () => {
  const browser = await chromium.launch({
    executablePath:execFileSync("which", ["chromium"], {encoding:"utf8"}).trim(),
    args:["--no-sandbox"],
  });
  try {
    for (const width of [390, 768, 1280, 1920]) {
      const page = await browser.newPage({viewport:{width,height:800}});
      await page.route("**/*", route => route.abort());
      await page.setContent(`<style>${css}</style>`);
      await page.evaluate(html => {
        const template = document.createElement("template");
        template.innerHTML = html;
        document.body.append(template.content.querySelector(".map-legend"));
      }, index);
      await page.evaluate(code => {window.eval(code);}, main.slice(loadStart, loadEnd));
      assert.equal(await page.locator('.lg[data-lodging-type="미분류"]').isVisible(), false);
      for (const show of [false, true, false]) {
        await page.evaluate(async show => {
          window.fetch = async () => ({ok:true,json:async () => ({
            count:85617,tx_count:19094,auction_building_count:1234,
            show_unclassified_legend:show,
            by_type:{"생활":4263,"관광":1388,"일반":28691,"에어비앤비":8423,
              "농어촌민박":34505,"캠핑":4808,"한옥":2387,"복합":1193,"준공전":395,"미분류":292},
          })});
          await loadBuildingCountLabel();
        }, show);
        assert.equal(await page.locator('.lg[data-lodging-type="미분류"]').isVisible(), show);
        assert.match(await page.locator('.lg[data-lodging-type="에어비앤비"]').innerText(), /외도민업/);
        assert.equal(await page.locator("[data-auction-layer] .lg-count").innerText(), "1,234");
        assert.equal(await page.locator("[data-auction-layer] .lg-count").count(), 1);
        const ys = await page.locator('[data-legend-slide="legend"] > .lg:not([hidden])')
          .evaluateAll(nodes => nodes.map(n => n.getBoundingClientRect().top));
        assert.ok(Math.max(...ys) - Math.min(...ys) < 1, `Legend wrapped at ${width}px`);
        const bounds = await page.locator(".map-legend").boundingBox();
        assert.ok(bounds.x >= 0 && bounds.x + bounds.width <= width + 1);
        await page.locator('[data-legend-slide="legend"]').evaluate(el => {el.scrollLeft=el.scrollWidth;});
        const accessible = await page.locator("[data-auction-layer]").evaluate(el => {
          const rect=el.getBoundingClientRect(), parent=el.parentElement.getBoundingClientRect();
          return rect.right <= parent.right+1 && rect.left >= parent.left-1;
        });
        assert.equal(accessible, true);
      }
      await page.close();
    }
    const page = await browser.newPage();
    await page.route("**/*", route => route.abort());
    await page.setContent('<div id="bldFullStats"></div>');
    await page.evaluate(code => {window.eval(code);}, admin.slice(adminStart, adminEnd));
    await page.evaluate(async () => {
      window.fetch = async () => ({json:async () => ({ok:true,rows:[
        {type:"전체",building_count:10,auction_building_count:2},
        {type:"생활",building_count:7,auction_building_count:2},
        {type:"일반",building_count:3,auction_building_count:0},
      ]})});
      await loadBldFullStats();
    });
    const texts = await page.locator("#bldFullStats").innerText();
    assert.match(texts, /공매건물/);
    assert.equal(await page.locator('td[title*="현재 공개 공매"]').count(), 3);
    assert.deepEqual(await page.locator('td[title*="현재 공개 공매"]').allTextContents(), ["2","2","0"]);
    console.log("PASS real legend: four widths, role visibility, counts, single row, scroll access; admin counts including zero");
  } finally {
    await browser.close();
  }
})().catch(error => {console.error(error);process.exit(1);});
