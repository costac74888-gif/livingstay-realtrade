const assert=require("node:assert/strict");
const {chromium}=require("playwright");
const base=process.env.HS2_FIXTURE_ORIGIN;
if(!base)throw Error("Owned fixture HTTP required");
let count=0;const ok=(value,label)=>{assert.ok(value,label);count++;};
async function main(){
 const browser=await chromium.launch({headless:true,executablePath:process.env.HS2_CHROMIUM,args:["--no-sandbox","--disable-gpu"]});
 try{
  for(const width of [1280,390]){
   const context=await browser.newContext({viewport:{width,height:950},userAgent:"Mozilla/5.0 Chrome/128.0.0.0 Safari/537.36"});
   const page=await context.newPage(),errors=[];
   page.on("pageerror",e=>errors.push(e.message));
   await page.goto(base+"/hs2/search/");
   const ready=()=>page.waitForFunction(()=>["ready","empty"].includes(document.querySelector("#statusMessage")?.dataset.state));
   await ready();
   await page.waitForSelector('.hs2-marker-toggle[data-layer="stay"]');
   ok(await page.locator('.listing-card[data-layer="stay"]').count()===2,"Actual nonempty owned public SQL rows");
   ok(await page.locator('#min_total').isDisabled(),"No selected-date total filter");
   ok(await page.locator('input[name=layer][value=stay]').isChecked(),"Stay defaultON");
   ok(await page.locator('.hs2-marker-group').count()===1,"Other layers initiallyOFF");
   for(const layer of ["sale","business","auction"]){
    await page.click(`.layer-${layer}`);await ready();
    await page.waitForSelector(`.hs2-marker-toggle[data-layer="${layer}"]`);
    ok(await page.locator(`.listing-card[data-layer="${layer}"]`).count()===2,"Independent source list "+layer);
   }
   ok(await page.locator(".hs2-marker-group").count()===4,"All simultaneous layers");
   ok(await page.locator(".listing-card").count()===8,"No same-id cross-layer loss");
   await page.locator("#mapCanvas").scrollIntoViewIfNeeded();
   const hit=await page.evaluate(()=>[...document.querySelectorAll(".hs2-marker-toggle")].map(el=>{
    const r=el.getBoundingClientRect(),top=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);
    return {layer:el.dataset.layer,hit:top?.closest(".hs2-marker-toggle")===el};
   }));
   ok(hit.length===4&&hit.every(h=>h.hit),"All co-located compact targets unobstructed "+width+" "+JSON.stringify(hit));
   await page.click('.hs2-marker-toggle[data-layer="auction"]');
   ok(await page.locator('.hs2-marker-group[data-layer="auction"] .hs2-marker-choice:visible').count()===2,"Cluster individual selection choices");
   await page.locator('.hs2-marker-group[data-layer="auction"] .hs2-marker-choice').first().press("Escape");
   ok(await page.locator('.hs2-marker-toggle[data-layer="auction"]').getAttribute("aria-expanded")==="false","Escape collapses without layerOFF");
   await page.click('.hs2-marker-toggle[data-layer="auction"]');
   await page.click('.hs2-marker-group[data-layer="auction"] .hs2-marker-choice[data-public-id="42"]');
   await page.waitForFunction(()=>!document.querySelector("#selectedSummary").hidden&&document.querySelector("#selectedSummary").textContent.includes("공매"));
   ok(await page.locator("#selectedSummary").innerText().then(x=>x.includes("공매")),"Typed auction42 selected");
   ok(await page.locator(".hs2-marker-group").count()===4,"Click never turns other layersOFF");
   ok(new URL(page.url()).searchParams.get("selected_layer")==="auction","Typed selection URL");
   const detail=await page.evaluate(async()=>await(await fetch("/hs2/search/api/detail/auction/42?layers=stay,sale,business,auction")).json());
   ok(detail.ok&&detail.item.layer==="auction"&&detail.booking_confirmed===false,"Actual same-origin detail notbooking");
   const all=await page.evaluate(async()=>await(await fetch("/hs2/search/api/results?layers=stay,sale,business,auction")).json());
   ok(all.markers.length===4&&all.markers.every(m=>m.point.lat===37.5&&m.point.lng===127.1),"No altered lat/lng");
   ok(all.markers.find(m=>m.layer==="auction").marker_shape==="square","Original auction square");
   ok(all.items.filter(i=>i.location_precision==="approx").every(i=>i.point.radius_m===500),"Restricted500m semantics");
   ok(!JSON.stringify(all).includes("NEVER_PUBLIC")&&!JSON.stringify(all).includes("37.512345"),"Protected native metadata never serialized");
   await page.evaluate(()=>{
    const original=window.fetch.bind(window);
    window.fetch=async(...args)=>{const r=await original(...args);if(String(args[0]).includes("/api/detail/sale/42?"))await new Promise(done=>setTimeout(done,180));return r;};
   });
   await page.click('.listing-card[data-layer="sale"][data-public-id="42"]');
   await page.click('.listing-card[data-layer="auction"][data-public-id="42"]');
   await page.waitForFunction(()=>!document.querySelector("#selectedSummary").hidden&&document.querySelector("#selectedSummary").textContent.includes("공매"));
   await page.waitForTimeout(230);
   ok((await page.locator("#selectedSummary").innerText()).includes("공매"),"Late sale same-id response cannot overwrite auction");
   await page.click('.layer-auction');await ready();
   ok(await page.locator(".hs2-marker-group").count()===3,"OFF removes onlyselectedlayer");
   ok(await page.locator("#selectedSummary").isHidden(),"OFF clears selected detail");
   ok(await page.locator('input[name=layer][value=sale]').isChecked()&&await page.locator('input[name=layer][value=business]').isChecked(),"Other toggles retained");
   await page.fill("#check_in","2027-01-01");await page.fill("#check_out","2027-01-15");
   ok(await page.locator("#min_total").isEnabled(),"Both dates enable TOTAL filter");
   await page.fill("#min_total","600000");await page.fill("#max_total","600000");
   await page.selectOption("#rooms","0");await page.fill("#min_area","21");await page.selectOption("#guests","2");
   await page.locator('label:has(input[name=options][value=wifi])').click();await page.locator('label:has(input[name=options][value=parking])').click();
   await page.locator('label:has(#instant)').click();await page.locator('label:has(#discount)').click();
   await page.locator('#searchForm button[type=submit]').click();await ready();
   ok(await page.locator('.listing-card[data-layer="stay"]').count()===1,"All actual summary attribute filters");
   ok((await page.locator('.listing-card[data-layer="stay"]').innerText()).includes("600,000"),"Exact14day price notnightly/monthconversion");
   ok(await page.locator('.listing-card[data-layer="sale"]').count()===2,"Stay filters do not reinterpret sale price");
   await page.reload();await ready();
   ok(await page.locator("#rooms").inputValue()==="0"&&await page.locator("#min_total").inputValue()==="600000","Filters restore URL");
   ok(await page.locator('input[name=layer][value=business]').isChecked()&&!(await page.locator('input[name=layer][value=auction]').isChecked()),"Independent layer URL restore");
   await page.route("**/hs2/search/api/results?**",r=>r.fulfill({status:503,contentType:"application/json",body:JSON.stringify({ok:false,code:"SOURCE_FAIL"})}));
   await page.locator('#searchForm button[type=submit]').click();
   await page.waitForFunction(()=>document.querySelector("#statusMessage")?.dataset.state==="error");
   ok(await page.locator("#errorPanel").isVisible(),"Source failure explicit");
   ok(await page.locator(".listing-card").count()===0,"No stale prices onfailednewquery");
   await page.unroute("**/hs2/search/api/results?**");
   await page.click("#retryButton");await ready();
   ok(await page.locator(".listing-card").count()>0,"Actual retry source restored");
   for(const layer of ["stay","sale","business"]){await page.click(`.layer-${layer}`);await ready();}
   ok(await page.locator(".listing-card").count()===0,"Explicit allOFF empty list");
   await page.reload();await ready();
   ok(await page.locator('input[name=layer]:checked').count()===0,"AllOFF survives reload no hidden stayON");
   ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),"No viewport overflow");
   ok(errors.length===0,"No JavaScript errors: "+errors.join(";"));
   await context.close();
  }
 }finally{await browser.close();}
 console.log(`HS2_UI_PASS ${count} assertions`);
}
main().catch(e=>{console.error(e);process.exit(1)});
