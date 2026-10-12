/* Real development route captures; no production/provider mutations.
 * Visual evidence is deliberately separate from functional acceptance. */
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const {chromium}=require('playwright');
const out=path.resolve(process.env.HS2_AUDIT_OUTPUT||'generated-artifacts/hs2-rebuild/preview-final');
const registry=require('./hs2_design_registry.json');
const origin='https://'+process.env.REPLIT_DEV_DOMAIN;
(async()=>{
 fs.mkdirSync(path.join(out,'captures'),{recursive:true});
 const browser=await chromium.launch({executablePath:process.env.HS2_CHROMIUM||'/nix/store/qa9cnw4v5xkxyip6mb9kxqfq1z4x2dx1-chromium-138.0.7204.100/bin/chromium',args:['--no-sandbox']});
 const context=await browser.newContext({locale:'ko-KR',userAgent:'Mozilla/5.0 Chrome/138.0.0.0 Safari/537.36'});
 const page=await context.newPage();
 await page.goto(origin+'/__development__/status');
 const status=await page.evaluate(()=>JSON.parse(document.body.innerText));
 assert.equal(status.production_entrypoint,false);assert.equal(status.actual_toss,false);
 let authenticated=false;
 if(process.env.HS2_PREVIEW_ADMIN_PASSWORD){
  await page.goto(origin+'/hs2/admin/login');
  await page.locator('[name=username]').fill('preview-admin');
  await page.locator('[name=password]').fill(process.env.HS2_PREVIEW_ADMIN_PASSWORD);
  await page.locator('button[type=submit]').click();
  await page.waitForURL('**/hs2/admin/',{timeout:20000});
  authenticated=true;
 }
 const results=[],interactions=[],runtime=[];
 page.on('pageerror',()=>runtime.push({kind:'pageerror',at:new Date().toISOString()}));
 const selected=process.env.HS2_AUDIT_IDS?process.env.HS2_AUDIT_IDS.split(','):null;
 for(const screen of registry.screens.filter(s=>!selected||selected.includes(s.id))){
  for(const width of [360,390,430,1440]){
   const entry={id:screen.id,title:screen.title,kind:screen.kind,width,path:screen.preview_path,
    native:screen.native,observed_at:new Date().toISOString(),functional_pass:false};
   await page.setViewportSize({width,height:900});
   try{
    let r=await page.goto(origin+screen.preview_path,{waitUntil:'domcontentloaded',timeout:30000});
    // Hash-only navigation has no HTTP response. Reload the document instead
    // of inventing a status or treating an absent response as a UI failure.
    if(!r) r=await page.reload({waitUntil:'domcontentloaded',timeout:30000});
    entry.http=r.status();
    await page.waitForTimeout(screen.native?700:150);
    await page.evaluate(()=>Promise.race([document.fonts.ready,new Promise(r=>setTimeout(r,1200))]));
    await page.evaluate(()=> {
      const images=Array.from(document.images);
      images.forEach(i=>i.loading='eager');
      return Promise.race([Promise.all(images.map(i=>i.decode().catch(()=>{}))),new Promise(r=>setTimeout(r,4000))]);
    });
    // Quote responses may replace the first lazy card nodes while decode()
    // awaits them. Check the current nodes, not detached earlier images.
    await page.waitForFunction(()=>{
      const images=Array.from(document.images).filter(i=>i.getBoundingClientRect().width>0&&!i.closest('#mapCanvas,#preview-detail-map,#roadview,#roadviewMiniMap'));
      images.forEach(i=>i.loading='eager');
      return images.every(i=>i.complete&&i.naturalWidth>0);
    },{timeout:15000});
    entry.geometry=await page.evaluate(()=>({
     scrollWidth:document.documentElement.scrollWidth,width:innerWidth,
     overflow:document.documentElement.scrollWidth>innerWidth+2,
     text_length:document.body.innerText.trim().length,
     provider_images_checked:false,
     images:Array.from(document.images).filter(i=>i.getBoundingClientRect().width>0&&!i.closest('#mapCanvas,#preview-detail-map,#roadview,#roadviewMiniMap')).map(i=>({loaded:i.complete&&i.naturalWidth>0})),
    }));
    entry.capture=`captures/${screen.id}-${width}.jpg`;
    await page.screenshot({path:path.join(out,entry.capture),type:'jpeg',quality:65});
    entry.visual_basic_pass=entry.http===200&&!entry.geometry.overflow&&entry.geometry.text_length>30&&entry.geometry.images.every(i=>i.loaded);
    if(screen.id==='C001'){
     await page.waitForFunction(()=>document.querySelectorAll('#listingList .listing-card').length>=20,{timeout:15000});
     const scroll=await page.evaluate(()=>{
      const e=document.querySelector('#listingList');let n=e;
      while(n&&n.scrollHeight<=n.clientHeight+2)n=n.parentElement;
      if(!n)return {possible:false};
      const before=n.scrollTop;n.scrollTop+=160;return {possible:n.scrollTop>before,before,after:n.scrollTop};
     });
     const image=page.locator('#listingList .listing-card img').first();
     const src=await image.getAttribute('src');
     const next=page.locator('.preview-photo-control[aria-label="다음 사진"]').first();
     await next.click();const different=src!==await image.getAttribute('src');
     const swipe=await image.evaluate(img=>{
      const fire=(x,y,type)=>img.dispatchEvent(new TouchEvent(type,{bubbles:true,changedTouches:[
       new Touch({identifier:1,target:img,clientX:x,clientY:y})
      ]}));
      const first=img.getAttribute('src');fire(180,120,'touchstart');fire(180,220,'touchend');
      const vertical_kept_photo=img.getAttribute('src')===first;
      fire(180,120,'touchstart');fire(90,120,'touchend');
      return {vertical_kept_photo,horizontal_changed:img.getAttribute('src')!==first,physical_device:false};
     });
     const priceColors=await page.locator('#listingList .listing-card').evaluateAll(cards=>cards.map(c=>({kind:c.dataset.kind,color:getComputedStyle(c.querySelector('.listing-price')).color})));
     const actionColors=await page.locator('.search-submit').evaluate(e=>({background:getComputedStyle(e).backgroundColor,brand:getComputedStyle(document.body).getPropertyValue('--preview-brand').trim()}));
     interactions.push({id:screen.id,width,scroll,photo_next:different,swipe,actionColors,price_colors:priceColors,
      pass:scroll.possible&&different&&swipe.vertical_kept_photo&&swipe.horizontal_changed&&actionColors.background==='rgb(239, 246, 255)'&&actionColors.brand==='#2563eb'&&priceColors.every(p=>p.color===(p.kind==='lodging'?'rgb(255, 56, 92)':'rgb(37, 99, 235)'))});
    }
   }catch(e){entry.error=e.name;entry.visual_basic_pass=false}
   results.push(entry);
   fs.writeFileSync(path.join(out,'capture-report.partial.json'),JSON.stringify({results,interactions,admin_authenticated:authenticated,runtime},null,2));
  }
 }
 const report={recorded_at:new Date().toISOString(),results,interactions,runtime,admin_authenticated:authenticated,
  summary:{items:new Set(results.map(r=>r.id)).size,captures:results.filter(r=>r.capture).length,
    basic_pass:results.filter(r=>r.visual_basic_pass).length,failed:results.filter(r=>!r.visual_basic_pass).length},
  physical_phone_verified:false,reference_parity_verified:false,functional_acceptance:'SEPARATE'};
 fs.writeFileSync(path.join(out,'capture-report.json'),JSON.stringify(report,null,2));
 console.log(JSON.stringify({summary:report.summary,interactions:interactions.map(({id,width,pass,scroll,photo_next})=>({id,width,pass,scroll,photo_next})),failures:results.filter(r=>!r.visual_basic_pass).map(r=>({id:r.id,width:r.width,http:r.http,error:r.error,geometry:r.geometry}))}));
 await browser.close();
 if(report.summary.failed||interactions.some(r=>!r.pass)||runtime.length)process.exitCode=1;
})().catch(e=>{console.error(e.name);process.exitCode=1});
