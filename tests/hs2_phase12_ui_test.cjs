const assert=require("node:assert/strict");
const {chromium}=require("playwright");
const base=process.env.HS2_FIXTURE_ORIGIN;
if(!base)throw Error("Owned fixture only");
let assertions=0;function ok(v,label){assert.ok(v,label);assertions++;}
async function main(){
 const browser=await chromium.launch({headless:true,executablePath:process.env.HS2_CHROMIUM,args:["--no-sandbox","--disable-gpu"]});
 try{
  for(const width of [1280,390]){
   const context=await browser.newContext({viewport:{width,height:950},userAgent:"Mozilla/5.0 Chrome/128.0.0.0 Safari/537.36"});
   const page=await context.newPage(),errors=[];page.on("pageerror",e=>errors.push(e.message));
   await page.goto(base+"/hs2/dashboard/");
   await page.waitForFunction(()=>document.querySelector("#dashboard-feedback")?.dataset.state==="ready");
   const d=await page.evaluate(async()=> (await(await fetch("/hs2/dashboard/api/overview")).json()).dashboard);
   ok(d.counts.published_rooms===2&&d.counts.bookings_confirmed_active===(width===1280?1:0),"Exact real approved public rows and capture state");
   ok(d.finance.sandbox_capture_krw===250000&&d.finance.live_capture_krw===0&&!d.finance.actual_money_executed,"Sandbox evidence notcash");
   for(const selector of ["#dashboard-summary","#dashboard-finance","#dashboard-applications","#dashboard-bookings","#dashboard-contracts"])
    ok((await page.locator(selector).innerText()).length>10,"Actual nonempty DOM "+selector);
   ok(await page.locator("#dashboard-legacy-links a").count()===8,"All legacywork preserved");
   ok(await page.locator("#dashboard-work-links a").count()===7,"Real workbench URLs");
   const application=d.applications.items[1];
   await page.goto(base+application.manage_uri);
   await page.waitForFunction(t=>document.querySelector("#title")?.value===t,application.title);
   ok(await page.locator("#title").inputValue()===application.title,"Correct own application deep entry, notfirstrecord");
   await page.goto(base+application.calendar_uri);
   await page.waitForFunction(id=>document.querySelector("#listing-select")?.value===id,application.application_id);
   ok(await page.locator("#listing-select").inputValue()===application.application_id,"Correct own calendar deep entry");
   await page.goto(base+"/hs2/dashboard/");
   await page.waitForFunction(()=>document.querySelector("#dashboard-feedback")?.dataset.state==="ready");
   if(width===1280){
    const result=await page.evaluate(async id=>await(await fetch(`/hs2/finance/api/consumer/${id}/cancel`,{method:"POST",headers:{"Content-Type":"application/json","X-CSRF-Token":"isolated-consumer-csrf-not-real-session"},body:JSON.stringify({acknowledged:true})})).json(),d.contracts.items[0].contract_id);
    ok(result.contract.booking_cancelled===true,"Real financial cancellation committed");
    await page.click("#refresh-dashboard");
    await page.waitForFunction(()=>document.querySelector("#dashboard-feedback")?.dataset.state==="ready"&&document.querySelector("#dashboard-bookings")?.textContent.includes("취소"));
    const updated=await page.evaluate(async()=> (await(await fetch("/hs2/dashboard/api/overview")).json()).dashboard);
    ok(updated.finance.active_stay_krw===0&&updated.finance.refund_review_krw===250000,"Committed changed ledger refresh");
   }
   ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),"Responsive nooverflow");
   await page.route("**/hs2/dashboard/api/overview",r=>r.fulfill({status:200,contentType:"application/json",body:JSON.stringify({ok:true,dashboard:{}})}));
   await page.click("#refresh-dashboard");
   await page.waitForFunction(()=>document.querySelector("#dashboard-feedback")?.dataset.state==="error");
   ok(await page.locator("#dashboard-contracts [data-contract-id]").count()===0,"Malformed ledger is error not staleorzero");
   await page.unroute("**/hs2/dashboard/api/overview");
   await page.route("**/hs2/dashboard/api/session",r=>r.fulfill({status:200,contentType:"application/json",body:JSON.stringify({ok:true,can_operator:false,context_id:null})}));
   await page.click("#refresh-dashboard");
   await page.waitForFunction(()=>document.querySelector("#dashboard-feedback")?.dataset.state==="forbidden");
   ok(await page.locator("#dashboard-applications [data-application-id]").count()===0,"Unapproved role gets noownrecords");
   ok(errors.length===0,"No JS error "+errors.join(";"));
   await context.close();
  }
 }finally{await browser.close();}
 console.log(`HS2_UI_PASS phase12 ${assertions} assertions`);
}
main().catch(e=>{console.error(e);process.exit(1)});
