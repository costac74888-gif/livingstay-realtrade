/* Current running owned Preview. No application writes except administrator
 * login. Password/cookies never logged, persisted or included in assets. */
const fs=require('node:fs'),path=require('node:path'),cp=require('node:child_process');
const {chromium}=require('playwright');
const out='generated-artifacts/hs2-integrated-preview';
const manifest=JSON.parse(fs.readFileSync('scripts/hs2_design_registry.json'));
const origin=`https://${process.env.REPLIT_DEV_DOMAIN}`;
const report={origin,actual_running_preview:true,function_completion:false,
              records:[],runtimeErrors:[],blocked:[],admin_verified:false,links:[],
              visual_approval:'자동 배치·메뉴검사 및 대표 화면 육안 확인; 사용자 최종 승인 별도'};
let cursor=0;
async function main(){
 fs.mkdirSync(`${out}/bundle/captures`,{recursive:true});
 fs.mkdirSync(`${out}/bundle/pages`,{recursive:true});
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
   const options={userAgent:'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36'};
   const context=await browser.newContext(options);
   const adminContext=await browser.newContext({...options,storageState:state});
   const guard=route=>{
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
   };
   await context.route('**/*',guard);
   await adminContext.route('**/*',guard);
   const publicPage=await context.newPage(),adminPage=await adminContext.newPage();let active;
   for(const page of [publicPage,adminPage]) page.on('pageerror',e=>report.runtimeErrors.push({id:active?.screen.id,error:e.message.replace(/https?:\/\/\S+/g,'[URL]').slice(0,180)}));
  while(cursor<jobs.length){
   active=jobs[cursor++];const {screen,width}=active;
    console.log(JSON.stringify({checking:screen.id,width}));
    const page=screen.role==='관리자'?adminPage:publicPage;
   const name=`${screen.id}-${width===1440?'web':'mobile'}`;
   const record={id:screen.id,kind:screen.kind,role:screen.role,width,title:screen.title,
     path:screen.preview_path,native:screen.native,alias_of:screen.alias_of,
     capture:`captures/${name}.jpg`,function_connection:screen.function_connection};
   try{
    await page.setViewportSize({width,height:width===1440?1000:874});
    const response=await page.goto(origin+screen.preview_path,{waitUntil:'domcontentloaded',timeout:45000});
    record.http=response?.status() ?? await page.evaluate(async()=>(
      await fetch(location.href,{method:'HEAD'})).status);
     if(!screen.native)await page.locator('#hs-design-page > *').first().waitFor({state:'attached',timeout:15000});
    await page.waitForTimeout(350);
    await page.evaluate(()=>Promise.race([document.fonts.ready,new Promise(r=>setTimeout(r,3000))]));
    await page.evaluate(()=>Promise.all([...document.images].map(i=>i.complete?Promise.resolve():new Promise(r=>{i.onload=r;i.onerror=r;setTimeout(r,2000)}))));
    if(screen.native && /consumer|owner-map|details/.test(screen.preview_path)) await page.waitForTimeout(1300);
     await page.evaluate(()=>Promise.race([
       new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))),
       new Promise(resolve=>setTimeout(resolve,250))]));
     // Native fetches can replace an initially styled skeleton after fonts
     // are ready. Wait for a short quiet DOM interval before checking styles.
     await page.evaluate(()=>new Promise(resolve=>{
       let quiet;
       const observer=new MutationObserver(()=>arm());
       const finish=()=>{clearTimeout(quiet);observer.disconnect();resolve();};
       const arm=()=>{clearTimeout(quiet);quiet=setTimeout(finish,500);};
       observer.observe(document.body,{childList:true,subtree:true});
       arm();setTimeout(finish,4000);
     }));
     await page.waitForFunction(()=>{
       const excluded='#mapCanvas,#preview-detail-map,#roadview,#roadviewMiniMap,.hs2-map-canvas,script,style,[hidden],.sr-only,[data-price],.hs-price,.listing-price,.detail-price,.preview-basis-price,.hs2-map-marker';
       return [...document.body.querySelectorAll('*')].every(e=>{
        if(!(e instanceof HTMLElement)||e.closest(excluded)||!e.getBoundingClientRect().width)return true;
        if(![...e.childNodes].some(n=>n.nodeType===3&&n.textContent.trim())&&!e.matches('input,select,textarea'))return true;
        const c=getComputedStyle(e);
        return c.visibility==='hidden'||(c.color==='rgb(0, 0, 0)'&&parseFloat(c.fontSize)>=16);
       });
     },undefined,{timeout:5000});
     const mobileMenu=page.locator('#hs-mobile-menu-toggle');
     if(width===390 && await mobileMenu.count()){
      await mobileMenu.click();
      const nav=page.locator('#hs-main-menu');
      record.menu_open=await nav.isVisible();
      await page.keyboard.press('Escape');
      record.menu_closed=!(await nav.isVisible());
     }
    record.metrics=await page.evaluate(()=>{
     const excluded='#mapCanvas,#preview-detail-map,#roadview,#roadviewMiniMap,.hs2-map-canvas,script,style,[hidden],.sr-only';
      const painted=e=>{
       for(let d=e.closest('details:not([open])');d;d=d.parentElement?.closest('details:not([open])')){
        if(!d.querySelector(':scope > summary')?.contains(e))return false;
       }
       return true;
      };
      const all=[...document.body.querySelectorAll('*')].filter(e=>e instanceof HTMLElement && !e.closest(excluded)&&painted(e)
       && e.getBoundingClientRect().width>0 && e.getBoundingClientRect().height>0 && getComputedStyle(e).visibility!=='hidden');
     const text=all.filter(e=>[...e.childNodes].some(n=>n.nodeType===3&&n.textContent.trim())||e.matches('input:not([type=hidden]),select,textarea'));
     const links=[...document.querySelectorAll('a[href]')].filter(a=>a.getBoundingClientRect().width&&a.getBoundingClientRect().height).map(a=>a.getAttribute('href'));
      const controls=all.filter(e=>e.matches('a[href],button,input:not([type=hidden]),select,textarea,summary')&&!e.closest(excluded));
      const occluded=controls.filter(e=>{
       const r=e.getBoundingClientRect(),x=r.x+r.width/2,y=r.y+r.height/2;
       if(x<0||y<0||x>=innerWidth||y>=innerHeight)return false;
       for(let p=e.parentElement;p&&p!==document.body;p=p.parentElement){
        const cs=getComputedStyle(p),b=p.getBoundingClientRect();
        if((['auto','scroll','hidden'].includes(cs.overflowX)&&(x<b.left||x>b.right))||
           (['auto','scroll','hidden'].includes(cs.overflowY)&&(y<b.top||y>b.bottom)))return false;
       }
       const hit=document.elementFromPoint(x,y);
       return hit&&!e.contains(hit)&&!hit.contains(e)&&getComputedStyle(e).pointerEvents!=='none';
      }).map(e=>({tag:e.tagName,id:e.id,text:e.textContent.trim().slice(0,60)})).slice(0,15);
      const clipped=text.filter(e=>{
       if(e.matches('input,textarea,select'))return false;
       const css=getComputedStyle(e);
       return e.clientWidth>0&&e.scrollWidth>e.clientWidth+3&&
        !['auto','scroll'].includes(css.overflowX)&&!e.closest('.hs-table-wrap,.table-wrap,.data-table-wrap');
      }).map(e=>({tag:e.tagName,class:e.className,text:e.textContent.slice(0,40)})).slice(0,15);
     return {width:innerWidth,scrollWidth:document.documentElement.scrollWidth,
       small:text.filter(e=>parseFloat(getComputedStyle(e).fontSize)<16).map(e=>({tag:e.tagName,class:e.className,size:getComputedStyle(e).fontSize})).slice(0,12),
       colored:text.filter(e=>getComputedStyle(e).color!=='rgb(0, 0, 0)'&&!e.closest('[data-price],.hs-price,.listing-price,.detail-price,.preview-basis-price,.hs2-map-marker')).map(e=>({tag:e.tagName,class:e.className,color:getComputedStyle(e).color})).slice(0,12),
       textLength:document.body.innerText.length,renderedTitle:document.querySelector('h1')?.textContent,
       brokenImages:[...document.images].filter(i=>i.getBoundingClientRect().width&&i.complete&&!i.naturalWidth).length,
        links,height:document.documentElement.scrollHeight,occluded,clipped,
        headerHeight:document.querySelector('.hs-live-header')?.getBoundingClientRect().height,
        mapStatus:document.querySelector('#mapStatus')?.textContent,
        mapReady:window.HS2PreviewMap?.state?.().ready};
    });
     await page.screenshot({path:`${out}/bundle/${record.capture}`,fullPage:true,type:'jpeg',quality:85,animations:'disabled',timeout:15000});
     if(width===1440){
      const snapshot=await page.evaluate(()=>{
       const doc=document.documentElement.cloneNode(true);
       doc.querySelectorAll('script,input[type=hidden],meta[http-equiv="Content-Security-Policy"]').forEach(e=>e.remove());
       doc.querySelectorAll('form').forEach(e=>{e.removeAttribute('action');e.removeAttribute('method');});
       doc.querySelectorAll('*').forEach(e=>[...e.attributes].forEach(a=>{
        if(/^on/i.test(a.name)||/nonce|csrf/i.test(a.name))e.removeAttribute(a.name);
       }));
       // A sanitized rendered snapshot, not an auth/API-capable application.
       return '<!doctype html>'+doc.outerHTML;
      });
      fs.writeFileSync(`${out}/bundle/pages/${screen.id}.html`,snapshot);
      record.html_snapshot=`pages/${screen.id}.html`;
     }
    record.status=record.http===200 && record.metrics.scrollWidth<=width && !record.metrics.small.length
        && !record.metrics.colored.length && !record.metrics.brokenImages
        && (record.metrics.textLength>80 ||
            (record.metrics.textLength>40 && Boolean(record.metrics.renderedTitle)))
        && !record.metrics.occluded.length && !record.metrics.clipped.length
        && record.menu_open!==false && record.menu_closed!==false
        && !(width===390&&record.metrics.headerHeight>110)
       ? '기본 화면 검사 통과' : '보완 필요';
   }catch(e){record.status='실패';record.error=String(e).replace(/https?:\/\/\S+/g,'[URL]').slice(0,220);}
   report.records.push(record);
    if(ids || report.records.length%40===0){
    fs.writeFileSync(`${out}/capture-report.partial.json`,JSON.stringify(report,null,2));
    console.log(JSON.stringify({captured:report.records.length,total:jobs.length,issues:report.records.filter(r=>r.status!=='기본 화면 검사 통과').length}));
   }
  }
  await context.close();
   await adminContext.close();
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
