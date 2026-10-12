/* Current native routes; read-only owned Preview plus approved public map hosts.
 * Separate from credential-free offline tests. Never overwrites old evidence. */
const {chromium}=require('playwright'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),cp=require('node:child_process');
const origin='https://'+process.env.REPLIT_DEV_DOMAIN;
const output='generated-artifacts/hs2-rebuild/current-map';
(async()=>{
 fs.mkdirSync(output,{recursive:true});
 const browser=await chromium.launch({executablePath:cp.execFileSync('which',['chromium'],{encoding:'utf8'}).trim(),args:['--no-sandbox']});
 try {
  const context=await browser.newContext({userAgent:'Mozilla/5.0 Chrome/138.0 Safari/537.36'});
  let denied=0;const errors=[],checks=[];
  await context.route('**/*',route=>{
   const r=route.request(),u=new URL(r.url());
   const publicHost=['kakao.com','kakaocdn.net','daumcdn.net','googleapis.com','gstatic.com','daum.net'].some(h=>u.hostname===h||u.hostname.endsWith('.'+h));
   if(!['GET','HEAD'].includes(r.method())||(u.origin!==origin&&!publicHost)){denied++;return route.abort();}
   return route.continue();
  });
  const page=await context.newPage();page.on('pageerror',()=>errors.push('pageerror'));
  await page.goto(origin+'/__development__/status');
  assert.equal(await page.evaluate(()=>JSON.parse(document.body.innerText).production_entrypoint),false);
  const widths=process.env.HS2_MAP_WIDTHS?process.env.HS2_MAP_WIDTHS.split(',').map(Number):[1440];
  for(const width of widths)for(const route of ['/hs2/consumer','/hs2/owner-map/']){
   await page.setViewportSize({width,height:900});await page.goto(origin+route);
   await page.waitForFunction(()=>window.HS2PreviewMap?.state().ready&&document.querySelectorAll('.listing-card').length>=20);
   await page.waitForTimeout(500);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+2),false);
   if(width<800){
    await page.locator('#hs-mobile-menu-toggle').click();
    assert(await page.locator('#hs-main-menu').isVisible());await page.keyboard.press('Escape');
    if(route==='/hs2/consumer'){
     await page.locator('[data-mobile-view="map"]').click();assert(await page.locator('#mapCanvas').isVisible());
     await page.locator('[data-mobile-view="list"]').click();assert(await page.locator('#resultsPane').isVisible());
    } else assert.equal(await page.locator('[data-mobile-view]').count(),0);
   }
   const before=await page.evaluate(()=>{const p=HS2PreviewMap.map().getCenter();return {lat:p.getLat(),lng:p.getLng()};});
   const card=page.locator('.listing-card').first(),selected=await card.getAttribute('data-public-id');
   await card.locator('.listing-title').click();await page.waitForTimeout(1000);
   assert(await page.locator('#selectedDetail').isVisible());
   const after=await page.evaluate(()=>{const p=HS2PreviewMap.map().getCenter();return {lat:p.getLat(),lng:p.getLng(),selected:HS2PreviewMap.state().selected};});
   assert.equal(after.selected,selected);
   if(width>=800) assert(Math.abs(before.lat-after.lat)+Math.abs(before.lng-after.lng)>1e-6);
   if(width>=800) assert.equal(await page.locator('.real-map-marker.is-selected').count(),1);
   const capture=`${route.includes('owner')?'owner':'consumer'}-${width}.jpg`;
   await page.screenshot({path:path.join(output,capture),type:'jpeg',quality:65});
   checks.push({route,width,selected_marker:true,list_to_map_center:width>=800?true:'NOT_CHECKED_HIDDEN_MAP',capture,physical_device:false});
  }
  assert.deepEqual(errors,[]);assert.equal(denied,0);
  fs.writeFileSync(path.join(output,'summary.json'),JSON.stringify({checks,status:'PASS',production_writes:false,actual_toss:false,denied},null,2));
  console.log(JSON.stringify({checks:checks.length,status:'PASS'}));
 } finally {await browser.close();}
})().catch(e=>{console.error(e.name,e.name==='AssertionError'?e.message:'',e.stack?.split('\n').filter(l=>l.includes('hs2_current_map_check.cjs')).join('\n'));process.exitCode=1;});
