/* Current running owned Preview. No application writes except administrator
 * login. Password/cookies never logged, persisted or included in assets. */
const fs=require('node:fs'),path=require('node:path'),cp=require('node:child_process');
const {chromium}=require('playwright');
const out='generated-artifacts/hs2-integrated-preview';
const manifest=JSON.parse(fs.readFileSync('scripts/hs2_design_registry.json'));
const origin=`https://${process.env.REPLIT_DEV_DOMAIN}`;
const report={origin,actual_running_preview:true,function_completion:false,
              records:[],runtimeErrors:[],blocked:[],admin_verified:false,links:[]};
let cursor=0;
async function main(){
 fs.mkdirSync(`${out}/bundle/captures`,{recursive:true});
 const browser=await chromium.launch({executablePath:cp.execSync('command -v chromium').toString().trim(),args:['--no-sandbox']});
 const initial=await browser.newContext({userAgent:'Mozilla/5.0 Chrome/138.0.0.0 Safari/537.36'});
 const login=await initial.newPage();
 await login.goto(origin+'/hs2/admin/login',{waitUntil:'domcontentloaded'});
 const password=process.env.HS2_PREVIEW_ADMIN_PASSWORD;
 if(password) {
  const status=await login.evaluate(async password=>{
   const csrf=document.querySelector('input[name="csrf"]').value;
   const r=await fetch('/hs2/admin/login',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({username:'preview-admin',password,csrf})});
   return r.status;
  },password);
  report.admin_login_status=status;report.admin_verified=status===200;
 }
 // Keep session only in memory; never save authenticated storageState.
 const state=await initial.storageState();
 await initial.close();
 const ids=process.env.HS2_CAPTURE_IDS?.split(',');
 const jobs=manifest.screens.filter(s=>!ids||ids.includes(s.id))
     .flatMap(screen=>[1440,390].map(width=>({screen,width})));
 async function worker(){
  const context=await browser.newContext({storageState:state,userAgent:'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36'});
  await context.route('**/*',route=>{
   const req=route.request(),u=new URL(req.url());
   if(!['GET','HEAD'].includes(req.method())){
    report.blocked.push(req.method()+' '+u.pathname);return route.abort();
   }
   // Do not allow pages to contact real operational/auth/PG endpoints.
   if(u.origin===origin && !u.pathname.startsWith('/hs2/')
       && !u.pathname.startsWith('/__development__/') && !u.pathname.startsWith('/__mockup/images/')
       && u.pathname !== '/static/home_stay_share.png') {
    report.blocked.push(req.method()+' '+u.pathname);return route.abort();
   }
   return route.continue();
  });
  const page=await context.newPage();let active;
  page.on('pageerror',e=>report.runtimeErrors.push({id:active?.screen.id,error:e.message.replace(/https?:\/\/\S+/g,'[URL]').slice(0,180)}));
  while(cursor<jobs.length){
   active=jobs[cursor++];const {screen,width}=active;
   const name=`${screen.id}-${width===1440?'web':'mobile'}`;
   const record={id:screen.id,kind:screen.kind,role:screen.role,width,title:screen.title,
     path:screen.preview_path,native:screen.native,alias_of:screen.alias_of,
     capture:`captures/${name}.jpg`,function_connection:screen.function_connection};
   try{
    await page.setViewportSize({width,height:width===1440?1000:874});
    const response=await page.goto(origin+screen.preview_path,{waitUntil:'domcontentloaded',timeout:45000});
    record.http=response?.status() ?? await page.evaluate(async()=>(
      await fetch(location.href,{method:'HEAD'})).status);
    await page.waitForTimeout(350);
    await page.evaluate(()=>Promise.race([document.fonts.ready,new Promise(r=>setTimeout(r,3000))]));
    await page.evaluate(()=>Promise.all([...document.images].map(i=>i.complete?Promise.resolve():new Promise(r=>{i.onload=r;i.onerror=r;setTimeout(r,2000)}))));
    if(screen.native && /consumer|owner-map|details/.test(screen.preview_path)) await page.waitForTimeout(1300);
    record.metrics=await page.evaluate(()=>{
     const excluded='#mapCanvas,#preview-detail-map,#roadview,#roadviewMiniMap,.hs2-map-canvas,script,style,[hidden],.sr-only';
     const all=[...document.body.querySelectorAll('*')].filter(e=>e instanceof HTMLElement && !e.closest(excluded)
       && e.getBoundingClientRect().width>0 && e.getBoundingClientRect().height>0 && getComputedStyle(e).visibility!=='hidden');
     const text=all.filter(e=>[...e.childNodes].some(n=>n.nodeType===3&&n.textContent.trim())||e.matches('input:not([type=hidden]),select,textarea'));
     const links=[...document.querySelectorAll('a[href]')].filter(a=>a.getBoundingClientRect().width&&a.getBoundingClientRect().height).map(a=>a.getAttribute('href'));
     return {width:innerWidth,scrollWidth:document.documentElement.scrollWidth,
       small:text.filter(e=>parseFloat(getComputedStyle(e).fontSize)<16).map(e=>({tag:e.tagName,class:e.className,size:getComputedStyle(e).fontSize})).slice(0,12),
       colored:text.filter(e=>getComputedStyle(e).color!=='rgb(0, 0, 0)'&&!e.closest('[data-price],.hs-price,.listing-price,.detail-price,.preview-basis-price,.hs2-map-marker')).map(e=>({tag:e.tagName,class:e.className,color:getComputedStyle(e).color})).slice(0,12),
       textLength:document.body.innerText.length,renderedTitle:document.querySelector('h1')?.textContent,
       brokenImages:[...document.images].filter(i=>i.getBoundingClientRect().width&&i.complete&&!i.naturalWidth).length,
       links,height:document.documentElement.scrollHeight};
    });
    await page.screenshot({path:`${out}/bundle/${record.capture}`,fullPage:true,type:'jpeg',quality:85,animations:'disabled'});
    record.status=record.http===200 && record.metrics.scrollWidth<=width && !record.metrics.small.length
       && !record.metrics.colored.length && !record.metrics.brokenImages && record.metrics.textLength>80
       ? '기본 화면 검사 통과' : '보완 필요';
   }catch(e){record.status='실패';record.error=String(e).replace(/https?:\/\/\S+/g,'[URL]').slice(0,220);}
   report.records.push(record);
   if(report.records.length%40===0){
    fs.writeFileSync(`${out}/capture-report.partial.json`,JSON.stringify(report,null,2));
    console.log(JSON.stringify({captured:report.records.length,total:jobs.length,issues:report.records.filter(r=>r.status!=='기본 화면 검사 통과').length}));
   }
  }
  await context.close();
 }
 await Promise.all(Array.from({length:4},worker));
 const verify=await browser.newContext({storageState:state});
 const linkPage=await verify.newPage();
 await linkPage.goto(origin+'/hs2/stays/profile-c023/',{waitUntil:'domcontentloaded'});
 const urls=[...new Set(report.records.flatMap(r=>r.metrics?.links||[]))]
   .map(h=>new URL(h,origin)).filter(u=>u.origin===origin && u.pathname.startsWith('/hs2/'));
 for(const url of urls){
  const status=await linkPage.evaluate(async path=>{
   try{return (await fetch(path,{method:'HEAD',redirect:'manual'})).status;}catch{return -1;}
  },url.pathname+url.search);
  report.links.push({path:url.pathname+url.search,status});
 }
 await verify.close();
 await browser.close();
 report.records.sort((a,b)=>a.id.localeCompare(b.id)||b.width-a.width);
 report.summary={captures:report.records.length,issues:report.records.filter(r=>r.status!=='기본 화면 검사 통과').length,
    runtimeErrors:report.runtimeErrors.length,admin_verified:report.admin_verified,
    deadLinks:report.links.filter(l=>l.status>=400||l.status===-1).length};
 fs.writeFileSync(`${out}/${ids?'capture-recheck-report':'capture-report'}.json`,JSON.stringify(report,null,2));
 console.log(JSON.stringify(report.summary));
}
main().catch(e=>{console.error(String(e).replace(/https?:\/\/\S+/g,'[URL]').slice(0,200));process.exit(1)});
