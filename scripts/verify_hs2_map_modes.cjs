/* Owned Preview browser checks. External traffic limited to the existing read-only map/font SDK. */
const {chromium}=require("playwright"),assert=require("node:assert/strict"),fs=require("node:fs");
const origin="https://"+process.env.REPLIT_DEV_DOMAIN,out="generated-artifacts/map-modes";
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.HS2_CHROMIUM,args:["--no-sandbox"]});
 const errors=[],blocked=[],results=[];
 try {
  for(const width of [1440,390]){
   const context=await browser.newContext({viewport:{width,height:width===390?844:980},userAgent:"Mozilla/5.0 Chrome/138.0.0.0 Safari/537.36"});
   await context.route("**/*",route=>{
    const u=new URL(route.request().url());
    if(["data:","blob:"].includes(u.protocol)||u.origin===origin||
      ["dapi.kakao.com","map.kakao.com","rv.map.kakao.com","fonts.googleapis.com","fonts.gstatic.com"].includes(u.hostname)||
      /\.daumcdn\.net$|\.kakaocdn\.net$/.test(u.hostname))return route.continue();
    blocked.push(u.origin);return route.abort();
   });
   const page=await context.newPage();page.on("pageerror",e=>errors.push(e.message));
   await page.goto(origin+"/hs2/consumer");
   await page.waitForFunction(()=>window.HS2PreviewMap?.state().ready&&document.querySelector("#searchForm").getAttribute("aria-busy")==="false");
   let state=await page.evaluate(()=>HS2PreviewMap.state());
   assert.equal(state.mode,"consumer");assert.deepEqual(state.itemLayers,["stay"]);
   assert.deepEqual(state.layers,["stay"]);assert.equal(state.facilityMarkers,0);
   for(const k of ["sale","business","auction","facility"])assert.equal(await page.locator(`[data-layer="${k}"].layer-button`).isVisible(),false);
   const consumer=await page.evaluate(async()=> (await fetch("/hs2/search/api/consumer-results?layers=sale,business,auction")).json());
   assert(consumer.ok);assert(consumer.items.length>=12);assert(consumer.items.every(r=>r.layer==="stay"));
   assert(!JSON.stringify(consumer.items).includes("application_id"));
   await page.screenshot({path:`${out}/consumer-${width}.png`});
   results.push({width,case:"consumer only stays, server enforces scope, no facility/non-stay controls",pass:true});
   await page.locator("#ownerModeLink").click();
   await page.waitForFunction(()=>window.HS2PreviewMap?.state().ready&&HS2PreviewMap.state().facilities.connected&&
     document.querySelector("#searchForm").getAttribute("aria-busy")==="false");
   state=await page.evaluate(()=>HS2PreviewMap.state());
   assert.equal(state.mode,"owner");assert.deepEqual([...state.layers].sort(),["auction","business","facility","sale","stay"]);
   assert.deepEqual([...state.itemLayers].sort(),["auction","business","sale","stay"]);
    assert.equal(state.facilities.total,84954);assert.equal(state.facilities.map_connectable,84358);
    assert.equal(state.facilities.without_coordinates,596);
    assert.equal(state.facilities.reference_count,85617);
    assert.equal(state.facilities.reference_count_verified,true);
    assert.equal(state.facilities.source,"production_readonly_public_field_snapshot");
    assert.equal(state.facilities.live_connection,false);
   assert(state.facilityMarkers>0&&state.facilityMarkers<200);
   for(const k of ["stay","sale","business","auction","facility"])assert(await page.locator(`[data-layer="${k}"].layer-button`).isVisible());
   for(const k of ["stay","sale","business","auction","facility"]){
    const r=await page.locator(`[data-layer="${k}"].layer-button`).boundingBox();
    assert(r.y+r.height<= (width===390?844:980),"All five owner controls must fit in the first viewport");
   }
   assert(await page.evaluate(()=>[...document.querySelectorAll(".layer-button")].every(b=>{
    const r=b.getBoundingClientRect(),hit=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);
    const count=b.querySelector(".layer-counter").getBoundingClientRect();
    return (hit===b||b.contains(hit))&&count.bottom<=b.closest(".map-tool-rail").getBoundingClientRect().bottom;
   })),"All owner controls and counts must be actually exposed, not clipped");
   await page.waitForFunction(()=>HS2PreviewMap.state().facilityMarkers>0);
   const initialMarkers=state.facilityMarkers, initialLevel=await page.evaluate(()=>HS2PreviewMap.map().getLevel());
   await page.screenshot({path:`${out}/owner-${width}.png`});
   results.push({width,case:"owner actual snapshot + all four listings, national bounded clusters",pass:true,facilities:state.facilities});
   await page.locator('[data-layer="sale"].layer-button').click();
   await page.waitForFunction(()=>document.querySelector("#searchForm").getAttribute("aria-busy")==="false");
   assert(!(await page.evaluate(()=>HS2PreviewMap.state().itemLayers)).includes("sale"));
   await page.locator('[data-layer="facility"].layer-button').click();
   await page.waitForFunction(()=>HS2PreviewMap.state().facilityMarkers===0);
   await page.locator("#consumerModeLink").click();
   await page.waitForFunction(()=>window.HS2PreviewMap?.state().ready&&document.querySelector("#searchForm").getAttribute("aria-busy")==="false");
   assert.deepEqual((await page.evaluate(()=>HS2PreviewMap.state())).layers,["stay"]);
   await page.locator("#ownerModeLink").click();
   await page.waitForFunction(()=>window.HS2PreviewMap?.state().ready&&document.querySelector("#searchForm").getAttribute("aria-busy")==="false");
   state=await page.evaluate(()=>HS2PreviewMap.state());
   assert(!state.layers.includes("sale")&&!state.layers.includes("facility"));
   await page.reload();
   await page.waitForFunction(()=>window.HS2PreviewMap?.state().ready&&document.querySelector("#searchForm").getAttribute("aria-busy")==="false");
   assert(!(await page.evaluate(()=>HS2PreviewMap.state().layers)).includes("facility"));
   results.push({width,case:"owner independent selections survive return/reload; consumer cannot inherit",pass:true});
   await page.locator('[data-layer="facility"].layer-button').click();
   await page.waitForFunction(()=>HS2PreviewMap.state().facilityMarkers>0);
   if(await page.locator("#panelToggle").getAttribute("aria-expanded")==="true")
     await page.locator("#panelToggle").click();
   const clickable=await page.evaluate(()=>{
    for(const b of document.querySelectorAll(".real-facility-marker")){
     const r=b.getBoundingClientRect(),hit=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);
     if(hit===b || b.contains(hit))return b.dataset.facilityId;
    }
    return null;
   });
   assert(clickable,"At least one actual facility cluster must be clickable");
   await page.locator(`[data-facility-id="${clickable}"]`).click();
   await page.waitForFunction(level=>HS2PreviewMap.map().getLevel()<level,initialLevel);
   await page.waitForTimeout(700);
   const clusterSum=await page.evaluate(()=>[...document.querySelectorAll(".real-facility-marker")].reduce((n,b)=>n+Number(b.dataset.count),0));
   assert.equal(clusterSum,(await page.evaluate(()=>HS2PreviewMap.state().facilities)).viewport_count);
   if(await page.locator("#panelToggle").getAttribute("aria-expanded")==="false")
     await page.locator("#panelToggle").click();
   await page.locator("#facilityDirectory").evaluate(el=>el.open=true);
   await page.waitForSelector(".facility-directory-item");
   const directory=await page.evaluate(async()=> (await fetch("/__development__/map-modes/facilities?mode=owner&view=directory&q=농어촌")).json());
    assert(directory.total>0);
    const missing=await page.evaluate(async()=> (await fetch("/__development__/map-modes/facilities?mode=owner&view=directory&coordinates=missing")).json());
    assert.equal(missing.total,596);assert(missing.items.every(r=>r.point===null));
   assert(directory.items.every(r=>!Object.hasOwn(r,"application_id")&&!Object.hasOwn(r,"public_id")));
   const invalid=await page.evaluate(async()=> (await fetch("/__development__/map-modes/facilities?mode=consumer")).status);
   assert.equal(invalid,403);
   await page.locator("#facilityQuery").fill("성수");await page.locator("#facilityDirectoryForm button").click();
   await page.waitForTimeout(300);
    await page.locator("#facilityQuery").fill("");
    await page.locator("#facilityCoordinates").selectOption("missing");
    await page.locator("#facilityDirectoryForm button").click();
    await page.waitForFunction(()=>document.querySelector("#facilityDirectoryResults")?.textContent.includes("좌표 미확인"));
   results.push({width,case:"cluster zoom + exact counts, full facility directory incl no coordinates, no listing linkage",pass:true,initialMarkers});
   const ui=await page.evaluate(()=>{
    const bad=[];
    for(const el of document.querySelectorAll("body *")) {
     if(el.closest("#mapCanvas")||!el.getClientRects().length||!getComputedStyle(el).visibility.includes("visible"))continue;
     const direct=[...el.childNodes].some(n=>n.nodeType===3&&n.textContent.trim());
     if(!direct)continue;
     const s=getComputedStyle(el);
     if(parseFloat(s.fontSize)<16||s.color!=="rgb(0, 0, 0)")bad.push({tag:el.tagName,text:el.textContent.slice(0,45),size:s.fontSize,color:s.color});
    }
    return {bad,overflow:document.documentElement.scrollWidth>innerWidth,map:document.querySelector("#mapCanvas").getBoundingClientRect().height};
   });
   assert.deepEqual(ui.bad,[]);assert.equal(ui.overflow,false);assert(ui.map>=160);
   results.push({width,case:"black application text >=16px, no horizontal overflow, usable original map",pass:true,mapHeight:ui.map});
   await context.close();
  }
  assert.deepEqual(errors,[]);assert.deepEqual(blocked,[]);
  fs.writeFileSync(out+"/browser-checks.json",JSON.stringify({ok:true,results,errors,blocked},null,2));
  console.log("PASS",results.length,"map-mode scenarios at 1440/390");
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
