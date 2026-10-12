/* Presentation-only capture. No POST, production database or private API access. */
const fs=require('node:fs'),path=require('node:path'),cp=require('node:child_process');
const {chromium}=require('playwright');
const output='generated-artifacts/hs2-full-design';
const manifest=JSON.parse(fs.readFileSync(`${output}/screen-manifest.json`));
const origin=`https://${process.env.REPLIT_DEV_DOMAIN}`;
const report={screens:[],errors:[],blocked:[],capture_only_not_function_pass:true};
let cursor=0;
async function main(){
 fs.mkdirSync(`${output}/bundle/captures`,{recursive:true});
 fs.mkdirSync(`${output}/bundle/screens`,{recursive:true});
 fs.mkdirSync(`${output}/bundle/maps`,{recursive:true});
 const browser=await chromium.launch({executablePath:cp.execSync('command -v chromium').toString().trim(),args:['--no-sandbox']});
 const selected=process.env.HS2_CAPTURE_IDS?.split(',');
 const jobs=manifest.screens.filter(s=>!selected||selected.includes(s.id)).flatMap(s=>[1440,390].map(width=>({screen:s,width})));
 async function worker(){
  const context=await browser.newContext({userAgent:'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36'});
  await context.route('**/*',route=>{
   const req=route.request(),u=new URL(req.url());
   if(!['GET','HEAD'].includes(req.method()) || (u.origin===origin&&!u.pathname.startsWith('/__mockup/')&&u.pathname!='/hs2/owner-map/')){
    report.blocked.push(req.method()+' '+u.pathname);return route.abort();
   }
   return route.continue();
  });
  const page=await context.newPage();
  let current;
  page.on('pageerror',e=>report.errors.push({id:current?.screen.id,error:e.message.split('\n')[0].replace(/https?:\/\/\S+/g,'[URL]')}));
  while(cursor<jobs.length){
   current=jobs[cursor++];const {screen,width}=current;
   const name=`${screen.id}-${width===1440?'web':'mobile'}`;
   const record={id:screen.id,width,name,path:`/__mockup/preview/hs2-complete/Suite?screen=${screen.id}`,capture:`captures/${name}.jpg`};
   try{
    await page.setViewportSize({width,height:width===1440?1000:874});
    await page.goto(origin+record.path,{waitUntil:'domcontentloaded',timeout:45000});
    await page.locator(`[data-screen-id="${screen.id}"]`).waitFor({timeout:20000});
    await page.evaluate(()=>Promise.race([document.fonts.ready,new Promise(r=>setTimeout(r,4000))]));
    if(await page.locator('[data-map-status]').count()){
     try{await page.locator('[data-map-status="ready"]').first().waitFor({timeout:15000});record.map='live-ready';}
     catch{record.map='external-not-ready';}
    }
    await page.evaluate(()=>Promise.all([...document.images].map(i=>i.complete?Promise.resolve():new Promise(r=>{i.onload=r;i.onerror=r;setTimeout(r,3000)}))));
    await page.screenshot({path:`${output}/bundle/${record.capture}`,fullPage:true,type:'jpeg',quality:88,animations:'disabled'});
    record.metrics=await page.evaluate(()=>{
     const root=document.querySelector('[data-screen-id]');
     const all=[...root.querySelectorAll('*')].filter(e=>e instanceof HTMLElement&&e.getBoundingClientRect().width&&e.getBoundingClientRect().height&& !e.closest('.hs2-map-canvas'));
     const text=all.filter(e=>[...e.childNodes].some(n=>n.nodeType===3&&n.textContent.trim())||['INPUT','SELECT','TEXTAREA'].includes(e.tagName));
     return {viewport:innerWidth,scrollWidth:document.documentElement.scrollWidth,
      small:text.filter(e=>parseFloat(getComputedStyle(e).fontSize)<16).map(e=>({tag:e.tagName,class:e.className,size:getComputedStyle(e).fontSize})).slice(0,12),
      colored:text.filter(e=>getComputedStyle(e).color!=='rgb(0, 0, 0)'&&!e.closest('[data-price],.hs-price,.price,.lodging-price,.home-price,.hs2-map-marker')).map(e=>({tag:e.tagName,class:e.className,color:getComputedStyle(e).color})).slice(0,12),
      textLength:root.innerText.length,title:root.querySelector('h1,h2')?.textContent,
      mapMarkers:root.querySelectorAll('.hs2-map-marker').length,
      screenshotHeight:document.documentElement.scrollHeight};
    });
    record.layoutStatus=record.metrics.scrollWidth<=width && !record.metrics.small.length && !record.metrics.colored.length && record.metrics.textLength>80?'기본 디자인 검사 통과 · 검토 대기':'보완 필요';
    const maps=page.locator('.hs2-map-canvas');
    for(let i=0;i<await maps.count();i++){
     const box=await maps.nth(i).boundingBox();
     if(box&&box.width&&box.height) await maps.nth(i).screenshot({path:`${output}/bundle/maps/${name}-${i}.png`});
    }
    const html=await page.evaluate(({name})=>{
     const root=document.querySelector('[data-screen-id]').cloneNode(true);
     root.querySelectorAll('script,iframe').forEach(n=>n.remove());
     root.querySelectorAll('*').forEach(n=>{
      [...n.attributes].filter(a=>a.name.startsWith('on')).forEach(a=>n.removeAttribute(a.name));
      if(n.tagName==='INPUT'&&n.type==='password') n.setAttribute('value','');
     });
     root.querySelectorAll('.hs2-map-canvas').forEach((n,i)=>{
      n.innerHTML=`<img alt="정적 지도 캡처 · 확대/이동 불가" src="../maps/${name}-${i}.png" style="width:100%;height:100%;object-fit:cover">`;
     });
     root.querySelectorAll('img').forEach(n=>{
      if(n.getAttribute('src')?.startsWith('/__mockup/images/hs2-unified/')) n.setAttribute('src','../assets/'+n.getAttribute('src').split('/').pop());
      n.removeAttribute('srcset');n.setAttribute('loading','eager');
     });
     root.querySelectorAll('a[href]').forEach(n=>{
      const href=n.getAttribute('href');
      if(href.includes('screen=')){
       const id=new URL(href,location.origin).searchParams.get('screen');
       n.setAttribute('href',id+'.html');
      } else if(href.includes('/hs2-complete/Catalog')) n.setAttribute('href','../index.html');
      else if(href.startsWith('/')||href.startsWith('javascript:')) n.setAttribute('href','../index.html');
     });
     let css='';
     for(const sheet of document.styleSheets)try{
      for(const rule of sheet.cssRules) if(!rule.cssText.startsWith('@import')) css+=rule.cssText.replaceAll('/__mockup/images/hs2-complete/','../assets/')+'\n';
     }catch{}
     return {body:root.outerHTML,css};
    },{name});
    fs.writeFileSync(`${output}/bundle/screens/${name}.json`,JSON.stringify(html));
    if(width===1440) fs.writeFileSync(`${output}/bundle/screens/${screen.id}.json`,JSON.stringify(html));
   }catch(e){record.layoutStatus='캡처 실패';record.error=e.message.split('\n')[0].replace(/https?:\/\/\S+/g,'[URL]');}
   report.screens.push(record);
   if(report.screens.length%30===0){
    fs.writeFileSync(`${output}/capture-report.partial.json`,JSON.stringify(report,null,2));
    console.log(`Captured ${report.screens.length}/${jobs.length}`);
   }
  }
  await context.close();
 }
 await Promise.all(Array.from({length:4},worker));
 await browser.close();
 report.screens.sort((a,b)=>a.id.localeCompare(b.id)||b.width-a.width);
 fs.writeFileSync(`${output}/${selected?'preflight-report':'capture-report'}.json`,JSON.stringify(report,null,2));
 console.log(JSON.stringify({captured:report.screens.length,failed:report.screens.filter(s=>s.error).length,needs:report.screens.filter(s=>s.layoutStatus!=='기본 디자인 검사 통과 · 검토 대기').length,errors:report.errors.length,blocked:report.blocked.length}));
 if(report.screens.some(s=>s.error)||report.errors.length||report.blocked.length)process.exitCode=1;
}
main().catch(e=>{console.error(e.message.replace(/https?:\/\/\S+/g,'[URL]'));process.exitCode=1});
