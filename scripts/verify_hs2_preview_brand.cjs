/* Read-only visual checks against the owned development Preview. */
const {chromium}=require("playwright");
const assert=require("node:assert/strict"),fs=require("node:fs");
const origin="https://"+process.env.REPLIT_DEV_DOMAIN;
const out="generated-artifacts/seongsu-preview";
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.HS2_CHROMIUM,args:["--no-sandbox"]});
 const context=await browser.newContext({userAgent:"Mozilla/5.0 Chrome/138.0.0.0 Safari/537.36"});
 const errors=[],blocked=[];
 await context.route("**/*",route=>{
  const u=new URL(route.request().url());
  const mapHosts=["dapi.kakao.com","map.kakao.com","rv.map.kakao.com","fonts.googleapis.com","fonts.gstatic.com"];
  const hostAllowed=u.origin===origin||mapHosts.includes(u.hostname)||/\.daumcdn\.net$|\.kakaocdn\.net$/.test(u.hostname);
  if(["data:","blob:"].includes(u.protocol))return route.continue();
  if(hostAllowed&&["GET","HEAD"].includes(route.request().method()))return route.continue();
  blocked.push({host:u.hostname,method:route.request().method()});return route.abort();
 });
 const page=await context.newPage();page.on("pageerror",e=>errors.push(e.message));
 const results=[];
 try{
  await page.goto(origin+"/__development__/seongsu/");
  const data=await page.evaluate(async()=>{
   const status=await(await fetch("/__development__/status")).json();
   const catalog=await(await fetch("/__development__/seongsu/catalog")).json();
   return {status,id:catalog.items[0].public_id};
  });
  assert.equal(data.status.database,"owned_ephemeral");
  assert.equal(data.status.actual_toss,false);
  const routes=[
   ["/hs2/consumer","map"],["/hs2/details/?public_id="+data.id,"detail"],
   ["/hs2/dashboard/","dashboard"],["/hs2/listings/?new=1"],["/hs2/bookings/"],
   ["/hs2/finance/"],["/hs2/calendar/"],["/hs2/workspace/"],["/hs2/help/"],
   ["/__development__/legacy-capabilities/"],["/__development__/seongsu/"],
   ["/__development__/seongsu/admin-role"],
  ];
  for(const width of [1440,390]){
   await page.setViewportSize({width,height:width===390?874:1000});
   for(const [path,mode] of routes){
    await page.goto(origin+path);
    if(mode==="map")await page.waitForFunction(()=>window.HS2PreviewMap?.state().ready);
    if(mode==="detail")await page.waitForFunction(()=>window.HS2DetailMap?.ready);
    if(mode==="dashboard")await page.waitForFunction(()=>document.querySelector("#dashboard-feedback")?.dataset.state==="ready");
    await page.evaluate(()=>Promise.race([document.fonts.ready,new Promise(resolve=>setTimeout(resolve,3000))]));
    await page.waitForTimeout(mode==="map"?1800:250);
    await page.mouse.move(0,0);
    const state=await page.evaluate(()=>{
     const blue=[...document.querySelectorAll("body *")].filter(e=>
      e instanceof HTMLElement&&!e.closest("#mapCanvas,#preview-detail-map,#roadview,#roadviewMiniMap,script,style")&&
      [...e.childNodes].some(n=>n.nodeType===3&&n.textContent.trim())&&e.getBoundingClientRect().height>0
     ).filter(e=>{const m=getComputedStyle(e).color.match(/[\d.]+/g);return m&&+m[2]>+m[0]+18&&+m[2]>+m[1]+8;})
      .map(e=>({tag:e.tagName,class:e.className,text:e.textContent.trim().slice(0,35)}));
     const logo=document.querySelector(".preview-brand-logo");
     const primary=[...document.querySelectorAll(".search-submit,.search-button,.primary-button,.primary-action,.detail-primary,.preview-register-link")]
      .filter(e=>e.getBoundingClientRect().height>0)
      .map(e=>({label:e.textContent.trim().slice(0,35),background:getComputedStyle(e).backgroundColor,color:getComputedStyle(e).color}));
      return {blue,primary,brand:getComputedStyle(document.body).getPropertyValue("--preview-brand").trim(),
      logo_loaded:!!logo?.complete&&logo.naturalWidth>0,
      favicon:document.querySelector('link[rel="icon"]')?.getAttribute("href"),
      share_image:document.querySelector('meta[property="og:image"]')?.getAttribute("content"),
      overflow:document.documentElement.scrollWidth>innerWidth};
    });
    assert.deepEqual(state.blue,[],path+" blue text");
    assert(state.logo_loaded,path+" original logo");
    assert(state.favicon?.endsWith("brand-icon.png"),path+" original favicon");
    assert(state.share_image?.endsWith("brand-icon.png"),path+" share image");
    assert.equal(state.overflow,false,path+" overflow");
    assert.equal(state.brand,"#596044",path+" approved main color");
    for(const button of state.primary){
     assert.equal(button.background,"rgb(89, 96, 68)",path+" olive action "+button.label);
     assert.equal(button.color,"rgb(255, 255, 255)",path+" white action label "+button.label);
    }
    if(mode==="map"){
     await page.locator(".search-submit").hover();
     await page.waitForTimeout(250);
     assert.equal(await page.locator(".search-submit").evaluate(e=>getComputedStyle(e).backgroundColor),"rgb(70, 77, 53)");
     await page.mouse.move(0,0);
     await page.waitForTimeout(200);
    }
    results.push({path,width,status:"PASS"});
    console.log(JSON.stringify({path,width,status:"PASS"}));
    if(mode)await page.screenshot({path:out+`/review-${mode}-${width}.png`,fullPage:mode!=="map"});
   }
  }
  const fetched=await page.evaluate(async()=>Promise.all(["brand-logo.png","brand-icon.png"].map(async name=>{
   const r=await fetch("/__development__/seongsu/map-assets/"+name);
   const bytes=new Uint8Array(await r.arrayBuffer());
   const hash=new Uint8Array(await crypto.subtle.digest("SHA-256",bytes));
   return [...hash].map(b=>b.toString(16).padStart(2,"0")).join("");
  })));
  const crypto=require("node:crypto");
  const originals=["attached_assets/HOME_STAY_logo_3_BlackWhite_OnBlack_1791718519754.png",
   "attached_assets/앱로고home_stay_share_1791718522426.png"];
  assert.deepEqual(fetched,originals.map(p=>crypto.createHash("sha256").update(fs.readFileSync(p)).digest("hex")));
  assert.deepEqual(errors,[]);assert.deepEqual(blocked,[]);
  const report={ok:true,results,original_asset_bytes:true,blue_application_text:false,
   main_color_approved:true,main_color:"#596044",actual_toss:false,production_data:false,errors,blocked};
  fs.writeFileSync(out+"/brand-checks.json",JSON.stringify(report,null,2));
  console.log(JSON.stringify(report));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
