/* Read-only browser checks against the explicitly owned development server.
 * Never contact operational endpoints or initiate booking/payment/delivery. */
const {chromium}=require('playwright');
const fs=require('node:fs'),cp=require('node:child_process');
const assert=require('node:assert/strict');
const origin=`https://${process.env.REPLIT_DEV_DOMAIN}`;
const results=[];
async function run(){
 const browser=await chromium.launch({executablePath:cp.execSync('command -v chromium').toString().trim(),args:['--no-sandbox']});
 const context=await browser.newContext({userAgent:'Mozilla/5.0 Chrome/138.0 Safari/537.36'});
 await context.route('**/*',route=>{
  const r=route.request(),u=new URL(r.url());
  if(!['GET','HEAD'].includes(r.method()))return route.abort();
  if(u.origin===origin&&!/^\/(hs2\/|__development__\/|__mockup\/images\/)/.test(u.pathname)&&u.pathname!='/static/home_stay_share.png')return route.abort();
  return route.continue();
 });
 const page=await context.newPage();
 for(const width of [390,768,1024,1440]){
  await page.setViewportSize({width,height:1000});
  for(const path of ['/hs2/consumer','/hs2/owner-map/']){
   await page.goto(origin+path,{waitUntil:'domcontentloaded'});
   await page.locator('.listing-card').first().waitFor({state:'attached'});
   await page.waitForFunction(()=>window.HS2PreviewMap?.state?.().ready===true,undefined,{timeout:15000});
   assert(await page.locator('.hs-live-header').evaluate(e=>e.getBoundingClientRect().height)<=90);
   assert.equal(await page.locator('.hs-live-header a[href="/hs2/admin/"]').count(),0);
   if(width<=1000){
    await page.locator('#hs-mobile-menu-toggle').click();
    assert(await page.locator('#hs-main-menu').isVisible());
    assert(await page.locator('#hs-main-menu a').count()>5);
    await page.keyboard.press('Escape');
    assert(!(await page.locator('#hs-main-menu').isVisible()));
   }
   if(width<=800){
    await page.locator('button[data-mobile-view="list"]').click();
    assert(await page.locator('#resultsPane').isVisible());
    assert(!(await page.locator('.map-tool-rail').isVisible()));
    await page.locator('button[data-mobile-view="map"]').click();
    assert(!(await page.locator('#resultsPane').isVisible()));
    assert(await page.locator('.map-tool-rail').isVisible());
    const rail=await page.locator('.map-tool-rail').boundingBox();
    assert(rail.width>=width-30&&rail.height<=120,'지도 도구는 넓고 낮은 가로 영역이어야 합니다');
    assert(rail.y>600,'지도 도구가 검색·목록 전환을 덮으면 안 됩니다');
    assert(await page.locator('#mapCanvas').evaluate(e=>e.getBoundingClientRect().height)>200);
    await page.locator('button[data-mobile-view="list"]').click();
   }
   if(path==='/hs2/consumer'){
    await page.locator('.listing-card').first().click();
    assert(await page.locator('#selectedDetail').isVisible());
   }
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
   results.push({path,width,passed:true,mapReady:true});
   console.log(JSON.stringify(results[results.length-1]));
  }
 }
 // Navigation is verified by real anchor click, not just an HTTP HEAD.
 await page.setViewportSize({width:390,height:874});
 await page.goto(origin+'/hs2/consumer');
 await page.locator('#hs-mobile-menu-toggle').click();
 await page.locator('#hs-main-menu a[href="/hs2/owner-map/"]').click();
 assert.equal(new URL(page.url()).pathname,'/hs2/owner-map/');
 await page.locator('#hs-mobile-menu-toggle').click();
 await page.locator('#hs-main-menu a[href="/hs2/calendar/"]').first().click();
 assert.equal(new URL(page.url()).pathname,'/hs2/calendar/');
 results.push({navigation:'사용자→임대인→요금·달력',passed:true});
 await browser.close();
 fs.writeFileSync('generated-artifacts/hs2-integrated-preview/interaction-report.json',JSON.stringify({results,actualAccountAndPayment:false},null,2));
 console.log(JSON.stringify({passed:results.length,failed:0}));
}
run().catch(e=>{console.error(e.message);process.exit(1)});
