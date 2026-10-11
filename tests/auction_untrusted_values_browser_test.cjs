/* Exercise both flagged HTML sinks with hostile, entirely synthetic API data. */
const {chromium}=require("playwright");
const {execFileSync}=require("node:child_process");
const assert=require("node:assert/strict");

(async()=>{
  const base=process.env.TEST_BASE_URL;
  assert.ok(base,"Owned test origin required");
  const attack=`"><img data-untrusted src=x onerror="window.__auctionXss=1"><script>window.__auctionXss=1</script>&'`;
  const browser=await chromium.launch({
    executablePath:execFileSync("which",["chromium"],{encoding:"utf8"}).trim(),
    args:["--no-sandbox"],
  });
  try{
    for(const width of [1280,390]){
      const context=await browser.newContext({
        viewport:{width,height:900},
        userAgent:"Mozilla/5.0 Chrome/138.0.0.0 Safari/537.36",
      });
      const page=await context.newPage(),errors=[];
      page.on("pageerror",e=>errors.push(e.message));
      await page.addInitScript(()=>{window.__auctionXss=0;});
      const fulfill=(route,body)=>route.fulfill({
        status:200,contentType:"application/json",body:JSON.stringify(body),
      });
      await page.route("**/api/regions",route=>fulfill(route,{
        [attack]:{count:1,sgg:{["district "+attack]:{count:1}}},
      }));
      await page.route("**/api/auctions?*",route=>fulfill(route,{
        ok:true,total:1,page:1,pages:1,items:[{
          id:101,title:attack,address_road:attack,address_jibun:attack,
          management_no:attack,usage_name:attack,status:attack,
          bid_start_at:attack,bid_end_at:attack,min_bid_amount:10000,
        }],
      }));
      await page.goto(base+"/auctions");
      await page.locator(".auction-row").waitFor();
      assert.equal(await page.locator(".auction-row").count(),1);
      assert.ok((await page.locator("#auctionResults").innerText()).includes(attack));
      await page.locator("#auctionSido").selectOption(attack);
      await page.waitForFunction(()=>document.getElementById("auctionSgg").options.length===2);
      assert.equal(await page.locator("#auctionSgg option").last().textContent(),"district "+attack);
      await page.locator(".auction-row").waitFor();
      assert.equal(await page.locator("[data-untrusted]").count(),0);
      assert.equal(await page.evaluate(()=>window.__auctionXss),0);
      assert.ok((await page.locator(".auction-title").getAttribute("href")).startsWith("/?"));
      assert.deepEqual(errors,[]);
      console.log(`PASS ${width}px escaped auction rows and district option labels: no injected DOM/script`);
      await context.close();
    }
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
