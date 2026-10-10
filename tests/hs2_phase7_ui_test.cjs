const assert=require("node:assert/strict");
const {chromium}=require("playwright");
const base=process.env.HS2_FIXTURE_ORIGIN;
if(!base)throw Error("Owned SQL-backed fixture HTTP required");
let count=0;
const ok=(condition,label)=>{assert.ok(condition,label);count++;};
async function main(){
  const browser=await chromium.launch({headless:true,executablePath:process.env.HS2_CHROMIUM,
    args:["--no-sandbox","--disable-gpu"]});
  try{
    for(const width of [1280,390]){
      const context=await browser.newContext({viewport:{width,height:900},
        userAgent:"Mozilla/5.0 Chrome/128.0.0.0 Safari/537.36"});
      const page=await context.newPage(),errors=[];
      page.on("pageerror",e=>errors.push(e.message));
      page.on("console",m=>{if(m.type()==="error")errors.push(m.text());});
      await page.goto(base+"/hs2/calendar/");
      await page.waitForFunction(()=>document.querySelector("#listing-select")?.options.length>1);
      const meta=await page.evaluate(async()=>await(await fetch("/hs2/calendar/meta")).json());
      const lodging=meta.items.find(r=>r.stay_kind==="lodging"),non=meta.items.find(r=>r.stay_kind==="non_lodging");
      ok(lodging&&non,"Nonempty actual owned approved registrations");
      const load=async id=>{
        const response=page.waitForResponse(r=>r.url().endsWith(`/applications/${id}/prices`)&&r.request().method()==="GET");
        await page.selectOption("#listing-select",id);await response;
        await page.waitForFunction(()=>!document.querySelector("#editor-content").hidden);
      };
      await load(lodging.id);
      ok(await page.locator("#lodging-fields").isVisible(),"Lodging date editor");
      const fillRange=async(start,end)=>{
        await page.fill("#range-start",start);await page.fill("#range-end",end);
      };
      await fillRange("2027-01-01","2027-01-08");
      await page.click('[data-preset="all"]');
      await page.fill("#nightly-amount","150000");
      await page.check("#inclusive-ack");
      const save=async(action)=>{
        const response=page.waitForResponse(r=>r.url().endsWith("/prices")&&r.request().method()==="POST");
        await action();const r=await response;ok(r.status()===200,"Server acknowledges committed save");return(await r.json()).item;
      };
      const saved=await save(()=>page.locator('#price-form button[type="submit"]').click());
      ok(saved.calendar.daily["2027-01-01"]===150000,"All-day bulk rate SQL-backed");
      await page.reload();
      await page.waitForFunction(()=>document.querySelector("#listing-select")?.options.length>1);
      await load(lodging.id);
      const persisted=await page.evaluate(async id=>await(await fetch(`/hs2/calendar/applications/${id}/prices`)).json(),lodging.id);
      ok(persisted.item.calendar.daily["2027-01-07"]===150000,"Reload preserves rate through actual PostgreSQL");
      await fillRange("2027-01-01","2027-01-02");
      await page.fill("#nightly-amount","250000");await page.check("#inclusive-ack");
      await save(()=>page.locator('#price-form button[type="submit"]').click());
      const quote=async(start,end)=>{
        await page.fill("#quote-check-in",start);await page.fill("#quote-check-out",end);
        const response=page.waitForResponse(r=>r.url().includes("/hs2/calendar/quote?"));
        await page.click("#request-quote");const r=await response;
        await page.waitForFunction(()=>!document.querySelector("#request-quote").disabled);
        return {status:r.status(),body:await r.json()};
      };
      const q=await quote("2027-01-01","2027-01-03");
      ok(q.status===200&&q.body.quote.total_krw===400000,"Date override + remaining daily actual total");
      ok(q.body.quote.booking_confirmed===false,"Quote does not claim actual booking");
      ok(!(JSON.stringify(q.body).includes(lodging.id)),"No private application identity");
      ok((await page.locator("#quote-result").innerText()).includes("400,000"),"Real nonempty price DOM");
      await fillRange("2027-01-02","2027-01-03");await page.check("#inclusive-ack");
      const closed=await save(()=>page.click("#close-range"));
      ok(closed.calendar.blocked.includes("2027-01-02"),"Persisted closed date");
      const denied=await quote("2027-01-01","2027-01-03");
      ok(denied.status===409&&denied.body.code==="CALENDAR_UNAVAILABLE","Blocked night rejects full-stay quote");
      ok(!(await page.locator("#quote-result").innerText()).includes("400,000"),"Failed quote clears stale displayed total");
      await page.check("#inclusive-ack");await save(()=>page.click("#open-range"));
      await page.selectOption("#listing-select",non.id);
      await page.waitForFunction(()=>!document.querySelector("#period-fields").hidden);
      ok(await page.locator("#period-fields").isVisible(),"Nonlodging week/month editor");
      await fillRange("2027-01-01","2027-04-01");
      await page.fill("#weekly-amount","400000");await page.fill("#monthly-amount","1100000");
      await page.check("#inclusive-ack");
      await save(()=>page.locator('#price-form button[type="submit"]').click());
      const week=await quote("2027-01-01","2027-01-15");
      ok(week.status===200&&week.body.quote.total_krw===800000,"Exact two-week nonlodging actual quote");
      const month=await quote("2027-01-31","2027-03-31");
      ok(month.status===200&&month.body.quote.total_krw===2200000,"Month-end no-drift exact two-month quote");
      ok(month.body.quote.lines.every(l=>l.unit==="month"),"No implicit 30-day proration");
      const conflict=await page.evaluate(async({id,csrf,source_revision})=>{
        const r=await fetch(`/hs2/calendar/applications/${id}/prices`,{method:"POST",headers:{"Content-Type":"application/json","X-HS2-CSRF":csrf},body:JSON.stringify({version:0,source_revision,command:{start:"2027-01-01",end:"2027-01-02",action:"close",values:{},inclusive:true}})});
        return {status:r.status,body:await r.json()};
      },{id:non.id,csrf:meta.csrf,source_revision:non.source_revision});
      ok(conflict.status===409&&conflict.body.code==="STALE_CALENDAR_REVISION","Concurrent stale write denied");
      ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),"No desktop/mobile horizontal overflow");
      // Expected rejected quote logs are not browser defects; no JS/CSP/asset errors.
      ok(errors.filter(e=>!e.includes("409 (CONFLICT)")).length===0,"No JavaScript/CSP/asset failures: "+errors.join(";"));
      await context.close();
    }
  }finally{await browser.close();}
  console.log(`HS2_UI_PASS phase7 ${count} assertions`);
}
main().catch(e=>{console.error(e);process.exit(1);});
