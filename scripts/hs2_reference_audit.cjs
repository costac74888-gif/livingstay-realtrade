/* Public reference observation only. Never sign in or copy competitor assets. */
const {chromium}=require('playwright');
const fs=require('fs'),path=require('path');
const out=path.resolve(process.env.HS2_REFERENCE_OUTPUT||'generated-artifacts/hs2-rebuild/reference');
const pages=[
 ['33m2-main','https://33m2.co.kr/main'],
 ['33m2-search','https://web.33m2.co.kr/guest/search'],
 ['33m2-host','https://web.33m2.co.kr/ko/host/main'],
 ['33m2-rooms','https://web.33m2.co.kr/guest/room?propertyTypes=OFFICETEL'],
 ['33m2-contract','https://web.33m2.co.kr/guest/contract'],
 ['33m2-chat','https://web.33m2.co.kr/guest/chat'],
 ['33m2-detail','https://web.33m2.co.kr/guest/room/112540'],
 ['33m2-owner-rooms','https://web.33m2.co.kr/host/room'],
 ['33m2-owner-contract','https://web.33m2.co.kr/host/contract'],
 ['33m2-owner-chat','https://web.33m2.co.kr/host/chat'],
 ['airbnb-main','https://www.airbnb.co.kr/'],
 ['airbnb-search','https://www.airbnb.co.kr/s/Seoul--South-Korea/homes'],
 ['airbnb-host','https://www.airbnb.co.kr/hosting'],
 ['airbnb-detail','https://www.airbnb.co.kr/rooms/23403028'],
];
(async()=>{
 fs.mkdirSync(out,{recursive:true});
 const browser=await chromium.launch({headless:true,executablePath:process.env.HS2_CHROMIUM||'/nix/store/qa9cnw4v5xkxyip6mb9kxqfq1z4x2dx1-chromium-138.0.7204.100/bin/chromium',args:['--no-sandbox']});
 const results=[];
 for(const [id,url] of pages.filter(([id])=>!process.env.HS2_REFERENCE_IDS||process.env.HS2_REFERENCE_IDS.split(',').includes(id))) for(const width of [360,390,430,1440]){
  const page=await browser.newPage({viewport:{width,height:900},locale:'ko-KR',
   userAgent:'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'});
  const item={id,url,width,observed_at:new Date().toISOString(),authenticated:false};
  try{
   const response=await page.goto(url,{waitUntil:'domcontentloaded',timeout:45000});
   await page.waitForTimeout(4000);
   item.status=response?.status();item.final_url=page.url();
   item.observation=await page.evaluate(()=>({
    title:document.title,text:document.body.innerText.slice(0,5500),
    links:Array.from(document.querySelectorAll('a[href]')).slice(0,60).map(a=>({label:a.innerText,url:a.href})),
    styles:Array.from(document.querySelectorAll('button,h1,h2,input,a')).filter(e=>e.getBoundingClientRect().width>0).slice(0,45).map(e=>{
     const s=getComputedStyle(e),r=e.getBoundingClientRect();return {text:e.innerText.slice(0,60),font:s.fontFamily,size:s.fontSize,weight:s.fontWeight,color:s.color,background:s.backgroundColor,radius:s.borderRadius,width:r.width,height:r.height}
    })
   }));
   item.scroll_observation=await page.evaluate(()=>{
     const scrolls=Array.from(document.querySelectorAll('*')).filter(e=>{
       const s=getComputedStyle(e);return /(auto|scroll)/.test(s.overflowY)&&e.scrollHeight>e.clientHeight+20&&e.clientHeight>100
     }).slice(0,6);
     return scrolls.map(e=>{const before=e.scrollTop;e.scrollTop+=150;const after=e.scrollTop;e.scrollTop=before;return {tag:e.tagName,role:e.getAttribute('role'),height:e.clientHeight,scroll_height:e.scrollHeight,before,after,programmatic_scroll:after>before}});
   });
   item.capture=`${id}-${width}.jpg`;
   await page.screenshot({path:path.join(out,item.capture),type:'jpeg',quality:65});
  }catch(e){item.error=e.message}
  results.push(item);await page.close();
 }
 await browser.close();
 fs.writeFileSync(path.join(out,'observations.json'),JSON.stringify(results,null,2));
 console.log(JSON.stringify(results.map(({id,width,status,error,final_url})=>({id,width,status,error,final_url}))));
})().catch(e=>{console.error(e);process.exitCode=1});
