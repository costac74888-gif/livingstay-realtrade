/* Real public UI checks. Never signs in, purchases or submits survey requests. */
const {chromium}=require("playwright");
const {execFileSync}=require("node:child_process");
const assert=require("node:assert/strict");

(async()=>{
  const base=process.env.TEST_BASE_URL || `https://${process.env.REPLIT_DEV_DOMAIN}`;
  const building=process.env.TEST_BUILDING_ID || "2654";
  const browser=await chromium.launch({
    executablePath:execFileSync("which",["chromium"],{encoding:"utf8"}).trim(),
    args:["--no-sandbox"],
  });
  try {
    for (const width of [390,1280]) {
      const page=await browser.newPage({viewport:{width,height:900},ignoreHTTPSErrors:true,
        userAgent:"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"});
      const errors=[];
      page.on("pageerror",error=>errors.push(error.message));
      await page.goto(`${base}/?building=${building}`,{waitUntil:"domcontentloaded"});
      await page.locator("#bTabOperations").waitFor({state:"visible"});
      await page.locator("#bTabOperations").click();
      await page.locator("#bAdminCard").waitFor({state:"visible"});
      const placement=await page.locator("#bOperationsPanel").evaluate(panel=>{
        const ids=[...panel.children].map(node=>node.id);
        return {reservation:ids.indexOf("bReservationCard"),admin:ids.indexOf("bAdminCard"),tourism:ids.indexOf("bTourismDataCard"),
          official:ids.indexOf("bApprovedRosterOperatingCard"),partner:ids.indexOf("bLodgingOperatorCard"),
          disclaimer:ids.indexOf("bOperatorInfoDisclaimer")};
      });
      assert.equal(placement.admin,placement.reservation+1);
      assert.equal(placement.tourism,placement.admin+1);
      assert.equal(placement.official,placement.tourism+1);
      assert.equal(placement.partner,placement.official+1);
      assert.equal(placement.disclaimer,placement.partner+1);
      assert.equal(await page.locator("#bPropertyPanel #bAdminCard").count(),0);
      await page.locator("#bApprovedRosterOperatingCard .b-membership-notice").waitFor({state:"visible"});
      await page.locator("#bApprovedRosterOperatingBody .b-membership-preview").waitFor({state:"visible"});
      const masks=page.locator("#bApprovedRosterOperatingBody .b-membership-mask");
      assert.equal(await masks.count(),10);
      assert.ok((await masks.allTextContents()).every(value=>value==="멤버십 회원 전용"));
      assert.equal(await page.locator("#bApprovedRosterOperatingBody .camp-detail-block").count(),0);
      assert.equal(await page.locator("#bApprovedRosterOperatingBody .b-membership-mark").count(),1);
      assert.ok(!(await page.locator("#bApprovedRosterOperatingBody").textContent()).includes("🔒"));
      const colors=await page.evaluate(()=>[
        getComputedStyle(document.querySelector(".hnav-auctions")).backgroundColor,
        getComputedStyle(document.querySelector(".map-legend [data-auction-layer] i")).backgroundColor
      ]);
      assert.deepEqual(colors,["rgb(61, 89, 72)","rgb(61, 89, 72)"]);
      const response=await page.request.get(`${base}/api/building/${building}`);
      const payload=await response.json();
      assert.deepEqual(payload.operating_records,[]);
      assert.equal(payload.operating_info,null);
      assert.equal(payload.operating_primary,null);
      assert.equal(payload.membership_access.required,true);
      assert.ok(Array.isArray(payload.lodgings));
      await page.locator("#bApprovedRosterOperatingCard").scrollIntoViewIfNeeded();
      await page.screenshot({path:`attached_assets/membership-preview-${width}.png`,animations:"disabled"});
      await page.locator("#bApprovedRosterOperatingBody a").click();
      await page.waitForURL("**/membership");
      await page.locator("#membershipApp [data-login]").waitFor();
      assert.match(await page.locator("#membershipApp").textContent(),/입금 확인 후/);
      assert.equal(await page.locator('form[action*="checkout"],button[data-purchase]').count(),0);
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth));
      assert.deepEqual(errors,[]);
      console.log(`PASS ${width}px: official preview → operating partner; masked placeholders only, protected API, non-lock mark, green auction nav/legend and membership CTA`);
      await page.close();
    }
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});