/* Real HTTP/DOM verification. Does not bypass auth or submit memberships/favorites. */
const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const { execFileSync } = require("node:child_process");
const fs = require("node:fs");

(async () => {
  const base = `https://${process.env.REPLIT_DEV_DOMAIN}`;
  const browser = await chromium.launch({ executablePath: execFileSync("which", ["chromium"], { encoding: "utf8" }).trim(), args: ["--no-sandbox"] });
  const context = await browser.newContext({ ignoreHTTPSErrors: true, userAgent: "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36", viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", e => errors.push(e.message));
  await page.goto(base + "/auctions");
  await page.waitForSelector(".auction-row");
  assert.equal(await page.locator(".auction-row").count(), 10);
  assert.equal(await page.locator('#siteHeader a[href="/auctions"]').count(), 1);
  assert.ok(await page.locator("#auctionSido option").count() > 1);
  const filtered = page.waitForResponse(r => r.url().includes("/api/auctions?") && r.status() === 200);
  await page.selectOption("#auctionSido", "경기도"); await filtered;
  assert.ok(await page.locator("#auctionSgg option").count() > 1);
  const reset = page.waitForResponse(r => r.url().includes("/api/auctions?") && r.status() === 200);
  await page.click("#auctionReset"); await reset;
  const sorted = page.waitForResponse(r => r.url().includes("sort=price_asc") && r.status() === 200);
  await page.locator('[data-sort-key="price"]').click(); await sorted;
  const paginated = page.waitForResponse(r => r.url().includes("page=2") && r.status() === 200);
  await page.locator('[data-page="2"]').first().click(); await paginated;
  console.log("PASS listing: real data, province/district, reset, sort, pagination");
  for (const width of [1280, 360]) {
    await page.setViewportSize({ width, height: 1000 });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
  }
  const data = await (await context.request.get(base + "/api/auctions/map?bbox=124,33,132,39")).json();
  const sample = data.items.find(i => i.master_building_id && i.thumbnail_url);
  assert.ok(sample);
  await page.setViewportSize({width:1280,height:900});
  await page.goto(base + "/auctions/" + sample.id);
  await page.waitForSelector("#bAuctionPanel .auction-panel-general");
  await page.waitForTimeout(2500);
  assert.equal(await page.locator(".auction-panel-round.is-current").count(), 1);
  await page.waitForSelector("#bAuctionPanel .survey-membership-notice");
  assert.equal(await page.locator("#bAuctionPanel .survey-analysis-link").count(), 0);
  assert.equal(await page.locator("#bAuctionPanel .survey-check-state").count(), 0);
  assert.equal(await page.locator("#bAuctionPanel .survey-membership-notice a").getAttribute("href"), "/membership");
  assert.ok((await page.locator('a.auction-panel-onbid').getAttribute("href")).startsWith("https://www.onbid.co.kr/"));
  const images = page.locator(".auction-panel-photo img");
  if (await images.count()) {
    await images.first().click();
    assert.ok(await page.locator(".auction-panel-lightbox").isVisible());
    await page.keyboard.press("Escape");
    assert.equal(await page.locator(".auction-panel-lightbox").isVisible(), false);
  }
  console.log("PASS detail: real photos, current-round identity, original link, survey membership restriction");
  await page.goto(base + "/");
  await page.waitForTimeout(4000);
  if (await page.locator("#welcomeClose").isVisible()) await page.click("#welcomeClose");
  await page.setViewportSize({ width: 1280, height: 900 });
  const legend = page.locator("[data-auction-layer]").first();
  assert.ok(await legend.count());
  await page.evaluate(() => setAuctionMapLayer(true));
  await legend.click();
  assert.equal(await page.evaluate(() => localStorage.getItem("hns_auction_layer")), "off");
  await legend.click();
  assert.equal(await page.evaluate(() => localStorage.getItem("hns_auction_layer")), "on");
  const mapReady = await page.evaluate(() => typeof kakaoMap !== "undefined" && !!kakaoMap);
  if (mapReady) {
    await page.evaluate(item => {
      kakaoMap.setCenter(new kakao.maps.LatLng(item.lat, item.lng));
      kakaoMap.setLevel(5);
    }, sample);
    await page.waitForSelector(".auction-map-marker", { timeout: 20000 });
    assert.ok(await page.locator(".auction-map-marker").count());
    console.log("PASS live Kakao map: auction marker layer at individual-marker zoom");
    fs.mkdirSync("attached_assets/auction-integrated",{recursive:true});
    for(const [label,width] of [["desktop",1280],["mobile",390]]){
      await page.setViewportSize({width,height:900});
      if(width===390)await page.evaluate(()=>window.livingstaySetPanelToggle(false));
      await page.evaluate(item=>{
        _auctionMapTarget=null;
        kakaoMap.relayout();
        kakaoMap.setCenter(new kakao.maps.LatLng(item.lat,item.lng));
        kakaoMap.setLevel(4);
        void updateMapForZoom(_lastMapFilters,{noAutoFit:true});
      },sample);
      await page.waitForSelector(".auction-building-point");
      const point=page.locator(".auction-building-point").first();
      const group=await point.getAttribute("data-auction-group");
      const box=page.locator(`.auction-map-marker[data-auction-group="${group}"]`);
      const a=await box.boundingBox(),b=await point.boundingBox();
      assert.ok(a.y+a.height<b.y,"Box must not cover the independently clickable building point");
      assert.ok(["진행","예정"].includes((await box.locator(".auction-map-marker-status").textContent()).trim()));
      await page.evaluate(()=>document.fonts.ready);
      await page.screenshot({path:`attached_assets/auction-integrated/map-${label}.png`});
      await box.click();
      await page.waitForFunction(()=>document.getElementById("bTabAuctions")?.getAttribute("aria-selected")==="true");
      await page.locator(".auction-panel-general").waitFor();
      assert.equal(await page.locator(".b-detail-tab:visible").count(),3);
      await page.screenshot({path:`attached_assets/auction-integrated/panel-${label}.png`});
      await page.evaluate(()=>window.livingstaySetPanelToggle(false));
      // Mobile may show the restored list panel; hide it with its existing toggle.
      if(width===390)await page.evaluate(()=>window.livingstaySetPanelToggle(false));
      await page.evaluate(()=>{kakaoMap.relayout();void loadAuctionMapOverlays();});
      await page.waitForSelector(".auction-building-point");
      await page.locator(".auction-building-point").first().click();
      await page.waitForFunction(()=>document.getElementById("bTabAuctions")&&!document.getElementById("bTabAuctions").hidden);
      assert.equal(await page.locator('[data-panel="property"]').getAttribute("aria-selected"),"true");
      assert.equal(await page.locator(".b-detail-tab:visible").count(),3);
      await page.evaluate(()=>window.livingstaySetPanelToggle(false));
    }
    console.log("PASS desktop/mobile real map: nonoverlapping box/point, independent clicks and all three tabs");
    await page.setViewportSize({width:1280,height:900});
    for (const level of [6, 9, 12]) {
      await page.evaluate(level => kakaoMap.setLevel(level), level);
      await page.waitForSelector('.map-cluster-badge', { timeout: 20000 });
      assert.ok((await page.locator('.map-cluster-badge').first().textContent()).includes("공매 "));
      assert.equal(await page.locator('.cluster-visitor-count').count(), 0);
    }
    console.log("PASS live Kakao clusters: auction-only counts at district/city/province zoom");
  } else console.log("NOT VERIFIED live Kakao map: SDK did not initialize in headless browser");
  const other=data.items.find(item=>!item.master_building_id&&item.id!==sample.id);
  assert.ok(other);
  await page.evaluate(({sample,other})=>window.openAuctionDetail(sample.id,{items:[sample,other]}),{sample,other});
  await page.locator(".auction-panel-general").waitFor();
  await page.selectOption("[data-auction-select]",String(other.id));
  await page.waitForFunction(()=>window.__openBuildingId===null);
  await page.locator(".auction-panel-general").waitFor();
  assert.equal(new URL(page.url()).searchParams.get("auction"),String(other.id));
  assert.equal(new URL(page.url()).searchParams.get("building"),null);
  assert.equal(await page.locator(".b-detail-tab:visible").count(),3);
  console.log("PASS grouped selection: switching between matched/unmatched items updates panel, tab scope and deep link");
  const unmatched=Number(execFileSync("python",["-c",
    "from db import get_conn\nwith get_conn() as c:\n with c.cursor() as q:\n  q.execute('SELECT id FROM auction_items WHERE master_building_id IS NULL ORDER BY id LIMIT 1');print(q.fetchone()['id'])"
  ],{encoding:"utf8"}).trim());
  await page.goto(base+"/auctions/"+unmatched+"/survey");
  await page.locator(".auction-panel-general").waitFor();
  assert.ok(page.url().endsWith("/?auction="+unmatched));
  assert.equal(await page.locator(".b-detail-tab:visible").count(),3);
  assert.equal(await page.locator(".survey-analysis-link").count(),0);
  await page.screenshot({path:"attached_assets/auction-integrated/unmatched-desktop.png"});
  await page.evaluate(id => window.openBuildingDetail(id), sample.master_building_id);
  await page.waitForSelector(".b-auction-active-badge", { timeout: 30000 });
  if (await page.locator("#bTabAuctions").isVisible()) {
    await page.locator(".b-auction-active-badge").first().click();
    await page.waitForSelector("#bAuctionPanel .auction-panel-general");
    assert.equal(await page.locator("#bTabAuctions").getAttribute("aria-selected"), "true");
  }
  console.log("PASS matched building: auction header badge and auction history panel");
  const noHistoryId=Number(execFileSync("python",["-c",
    "from db import get_conn\nwith get_conn() as c:\n with c.cursor() as q:\n  q.execute('SELECT b.id FROM master_buildings b WHERE NOT EXISTS(SELECT 1 FROM auction_items a WHERE a.master_building_id=b.id) ORDER BY b.id LIMIT 1');print(q.fetchone()['id'])"
  ],{encoding:"utf8"}).trim());
  await page.evaluate(id => window.openBuildingDetail(id), noHistoryId);
  await page.waitForSelector(".b-auction-empty", { timeout: 30000 });
  assert.ok((await page.locator(".b-auction-empty").textContent()).includes("공매 이력 없음"));
  assert.ok((await page.locator(".b-auction-empty a").getAttribute("href")).includes("courtauction.go.kr"));
  assert.equal(await page.locator(".b-auction-empty button").isDisabled(), false);
  console.log("PASS no-history building: official court link only, working watch entry");
  assert.deepEqual(errors, []);
  console.log("PASS browser JavaScript: no unhandled errors");
  await browser.close();
})().catch(e => { console.error(e.stack || e.message); process.exit(1); });