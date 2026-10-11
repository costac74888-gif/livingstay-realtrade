const assert=require("node:assert/strict"),{chromium}=require("playwright");
const base=process.env.HS2_FIXTURE_ORIGIN;if(!base)throw Error("Owned fixture only");
let count=0;function ok(v,label){assert.ok(v,label);count++;}
async function main(){
 const browser=await chromium.launch({headless:true,executablePath:process.env.HS2_CHROMIUM,args:["--no-sandbox","--disable-gpu"]});
 try{for(const width of [320,390]){
  const ctx=await browser.newContext({viewport:{width,height:920},userAgent:"Mozilla/5.0 Chrome/128.0.0.0 Safari/537.36"});
  const page=await ctx.newPage(),errors=[];page.on("pageerror",e=>errors.push(e.message));
  await page.goto(base+"/hs2/search/mobile/");
  await page.waitForSelector("#listingList .listing-card");
  ok(await page.locator(".results-pane").isVisible()&&!await page.locator(".map-pane").isVisible(),"List default, not cramped split");
  const before=await page.evaluate(()=>fetch("/hs2/search/api/results").then(r=>r.json()).then(r=>r.items.map(x=>[x.layer,x.id])));
  await page.locator("#mobile-map-btn").click();
  ok(await page.locator(".map-pane").isVisible()&&!await page.locator(".results-pane").isVisible(),"Map only");
  await page.waitForSelector('.hs2-marker-toggle[data-layer="stay"]');
  const pressed=await page.locator("#mobile-map-btn").getAttribute("aria-pressed");ok(pressed==="true","Accessible pane state");
  await page.setViewportSize({width:1280,height:920});
  await page.waitForFunction(()=>!document.querySelector(".results-pane").hidden&&!document.querySelector(".map-pane").hidden);
  ok(await page.locator(".map-pane").isVisible()&&await page.locator(".results-pane").isVisible(),"Desktop restores both original panes");
  await page.setViewportSize({width,height:920});
  // Viewport protocol completion precedes the asynchronous matchMedia handler.
  await page.waitForFunction(()=>document.querySelector(".results-pane").hidden&&!document.querySelector(".map-pane").hidden);
  ok(await page.locator(".map-pane").isVisible()&&!await page.locator(".results-pane").isVisible(),"Mobile choice survives breakpoint");
  await page.locator("#mobile-list-btn").click();
  const after=await page.evaluate(()=>fetch("/hs2/search/api/results").then(r=>r.json()).then(r=>r.items.map(x=>[x.layer,x.id])));
  ok(JSON.stringify(before)===JSON.stringify(after),"Switch preserves exact server data");
  ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),"Mobile search nooverflow");
  for(const path of ["/hs2/consumer","/hs2/listings/","/hs2/calendar/","/hs2/bookings/","/hs2/finance/","/hs2/dashboard/","/hs2/workspace/","/hs2/help/"]){
   await page.goto(base+path);await page.waitForTimeout(500);
   ok(await page.locator("body").innerText().then(x=>x.length>80),"Actual body "+path);
   ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),"Whole mobile nooverflow "+path);
  }
  await page.evaluate(()=>fetch("/hs2/listings-fixture/identity",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({admin:true})}));
  await page.goto(base+"/hs2/admin/");await page.waitForFunction(()=>document.querySelector("#admin-feedback")?.dataset.state==="ready");
  ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),"Admin at minimum mobile width");
  ok(errors.length===0,"Whole mobile has no JS exception");
  await ctx.close();
 }}finally{await browser.close();}
 console.log(`HS2_UI_PASS phase16 ${count} assertions`);
}
main().catch(e=>{console.error(e);process.exit(1)});
