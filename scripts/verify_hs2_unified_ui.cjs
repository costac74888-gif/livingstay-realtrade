/* Read-only HTTPS development Preview checks; original Kakao SDK, never fake tiles. */
const {chromium}=require("playwright"),assert=require("node:assert/strict"),fs=require("node:fs");
const origin="https://"+process.env.REPLIT_DEV_DOMAIN, out="generated-artifacts/unified-preview";
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.HS2_CHROMIUM,args:["--no-sandbox"]});
 const context=await browser.newContext({userAgent:"Mozilla/5.0 Chrome/138.0.0.0 Safari/537.36"});
 await context.route("**/*",route=>{
  const u=new URL(route.request().url());
  const allowed=u.origin===origin || ["dapi.kakao.com","map.kakao.com","rv.map.kakao.com","fonts.googleapis.com","fonts.gstatic.com"].includes(u.hostname)
   || /\.daumcdn\.net$|\.kakaocdn\.net$/.test(u.hostname);
  return allowed&&["GET","HEAD"].includes(route.request().method()) ? route.continue() : route.abort();
 });
 const page=await context.newPage(),errors=[],results=[];
 page.on("pageerror",e=>errors.push(e.message));fs.mkdirSync(out,{recursive:true});
 try {
  await page.goto(origin+"/hs2/consumer");
  const source=await page.evaluate(async()=>({
   status:await(await fetch("/__development__/status")).json(),
   catalog:await(await fetch("/__development__/seongsu/catalog")).json()}));
  assert.equal(source.status.database,"owned_ephemeral");assert.equal(source.status.actual_toss,false);
  const id=source.catalog.items.find(r=>r.category==="lodging").public_id;
  const routes=[
   ["/hs2/consumer","consumer"],["/hs2/details/?public_id="+id,"detail"],
   ["/hs2/owner-map/","owner"],["/hs2/dashboard/","dashboard"],
   ["/hs2/calendar/","calendar"],["/hs2/bookings/","booking"],
   ["/hs2/workspace/","chat"],["/hs2/listings/?new=1","registration"],
   ["/hs2/finance/","finance"],["/hs2/admin/login","admin-login"]
  ];
  for(const width of [1440,390]){
   await page.setViewportSize({width,height:width===390?874:1000});
   for(const [path,name] of routes){
    await page.goto(origin+path);
    if(["consumer","owner"].includes(name))await page.waitForFunction(()=>window.HS2PreviewMap?.state().ready);
    if(name==="detail")await page.waitForFunction(()=>window.HS2DetailMap?.ready);
    await page.waitForTimeout(450);
    const unreadable=await page.evaluate(()=>[...document.querySelectorAll("body *")]
     .filter(e=>e instanceof HTMLElement&&!e.closest("#mapCanvas,#preview-detail-map,#roadview,#roadviewMiniMap,script,style")&&
      e.getBoundingClientRect().height>0&&[...e.childNodes].some(n=>n.nodeType===3&&n.textContent.trim()))
     .filter(e=>parseFloat(getComputedStyle(e).fontSize)<16||getComputedStyle(e).color!=="rgb(0, 0, 0)")
     .map(e=>({tag:e.tagName,class:e.className})));
    assert.deepEqual(unreadable,[],name+" readable black application text");
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,name+" page overflow");
    const logo=page.locator(".preview-brand-logo").first();
    assert(await logo.count(),name+" logo");
    const rect=await logo.boundingBox();assert(rect.x>=0&&rect.x+rect.width<=width,name+" unclipped logo");
    assert.equal(await page.locator('.header-action[href="/hs2/admin/"]').count(),0);
    if(["consumer","owner"].includes(name)){
     assert.equal(await page.locator(".mobile-filter-group").isVisible(),false);
     assert.equal(await page.locator("#previewDateHelpers").isVisible(),false);
     if(name==="consumer"){
      assert.equal(await page.locator("#facilityDirectory").isVisible(),false);
      assert.equal(await page.locator('[data-layer="sale"]').isVisible(),false);
      const geometry=await page.evaluate(()=>({pane:document.querySelector("#resultsPane").getBoundingClientRect().width,
       cols:getComputedStyle(document.querySelector("#listingList")).gridTemplateColumns.split(" ").length}));
      if(width===1440){assert.equal(geometry.cols,2);assert(geometry.pane<width/2);}
     }
    }
    if(name==="detail"){
     assert.match(await page.locator("#reservation-base-rate").textContent(),/원\/일/);
     assert.equal(await page.locator("#stay-type").isVisible(),false);
    }
    await page.screenshot({path:out+`/${name}-${width}.png`,fullPage:!["consumer","owner"].includes(name)});
    results.push({name,width,status:"PASS"});
   }
  }
  assert.deepEqual(errors,[]);
  fs.writeFileSync(out+"/visual-checks.json",JSON.stringify({status:"PASS",results,
   real_map_provider:"existing_kakao_maps",actual_toss:"NOT_RUN",production_accounts_connected:false},null,2));
  console.log(JSON.stringify({status:"PASS",screens:results.length,real_map_provider:"existing_kakao_maps"}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
