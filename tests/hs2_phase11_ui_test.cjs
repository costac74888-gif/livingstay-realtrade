const assert=require("node:assert/strict");
const {chromium}=require("playwright");
const base=process.env.HS2_FIXTURE_ORIGIN;
if(!base)throw Error("Owned fixture only");
let assertions=0;function ok(v,label){assert.ok(v,label);assertions++;}
async function main(){
 const browser=await chromium.launch({headless:true,executablePath:process.env.HS2_CHROMIUM,args:["--no-sandbox","--disable-gpu"]});
 try{
  for(const [width,start,end] of [[1280,"2027-01-01","2027-01-03"],[390,"2027-01-03","2027-01-05"]]){
   const context=await browser.newContext({viewport:{width,height:950},userAgent:"Mozilla/5.0 Chrome/128.0.0.0 Safari/537.36"});
   const page=await context.newPage(),errors=[];page.on("pageerror",e=>errors.push(e.message));
   await page.goto(base+"/hs2/finance/");
   await page.waitForFunction(()=>document.querySelector("#finance-feedback")?.dataset.state==="ready");
   const booking=await page.evaluate(async dates=>{
    async function get(p){return await(await fetch(p)).json();}
    async function post(p,b,csrf){return await(await fetch(p,{method:"POST",headers:{"Content-Type":"application/json","X-CSRF-Token":csrf},body:JSON.stringify(b)})).json();}
    const id=(await get("/hs2/search/api/results")).items.find(r=>r.stay_kind==="lodging").public_id;
    const selection={check_in:dates.start,check_out:dates.end,guests:2};
    const q=(await get(`/hs2/details/api/items/${id}/quote?check_in=${dates.start}&check_out=${dates.end}&guests=2`)).quote;
    const receipt=(await post(`/hs2/details/api/items/${id}/confirm-quote`,{...selection,request_id:crypto.randomUUID(),acknowledged:true,expected_source_version:q.source_version},"isolated-consumer-csrf-not-real-session")).receipt;
    const b=(await post("/hs2/bookings/api/request",{receipt_id:receipt.receipt_id,request_id:crypto.randomUUID(),acknowledged:true},"isolated-consumer-csrf-not-real-session")).booking;
    return (await post(`/hs2/bookings/api/operator/${b.booking_id}/action`,{action:"approve",revision:b.revision},"isolated-booking-operator-csrf-not-real-session")).booking;
   },{start,end});
   ok(booking.status==="awaiting_payment","Actual booking held andapproved");
   await page.goto(base+`/hs2/finance/?booking_id=${booking.booking_id}`);
   await page.waitForFunction(()=>document.querySelector("#finance-preview")?.textContent.includes("250,000"));
   const preview=await page.locator("#finance-preview").innerText();
   ok(preview.includes("200,000")&&preview.includes("50,000")&&preview.includes("250,000"),"Exact stay/deposit/payable BEFORE explicit consent");
   ok(await page.locator("#create-financial-contract").isDisabled(),"No automatic financialack");
   await page.locator("label:has(#finance-ack)").click();
   let response=page.waitForResponse(r=>r.url().endsWith("/api/contracts"));
   await page.click("#create-financial-contract");
   const created=await(await response).json(),contract=created.contract;
   ok(contract.status==="awaiting_payment"&&!contract.payment_verified&&!contract.booking_confirmed,"Financial terms notfakepaid");
   ok(contract.terms.host_payout_krw===200000&&contract.terms.deposit_krw===50000&&contract.terms.platform_fee_krw===0,"Initial platformzero; deposit not hostrevenue");
   await page.waitForSelector(`[data-contract-id="${contract.contract_id}"]`);
   await page.reload();await page.waitForFunction(()=>document.querySelector("#finance-feedback")?.dataset.state==="ready");
   ok(await page.locator(`article[data-contract-id="${contract.contract_id}"]`).count()===1,"Committed contract reentry");
   const records=await page.evaluate(async()=>await(await fetch("/hs2/finance/api/consumer")).json());
   const captured=records.contracts.find(c=>c.status==="captured");
   ok(!!captured||width===390,"Owned signed provider evidence exists, notbrowser paidflag");
   if(captured){
    await page.click("#finance-operator-view");
    await page.waitForSelector(`article[data-contract-id="${captured.contract_id}"] [data-action=release-review]`);
    await page.locator("label:has(#finance-ack)").click();
    response=page.waitForResponse(r=>r.url().endsWith(`/operator/${captured.contract_id}/release-review`));
    await page.locator(`article[data-contract-id="${captured.contract_id}"] [data-action=release-review]`).click();
    const reviewed=(await(await response).json()).contract;
    ok(reviewed.actual_money_executed===false&&reviewed.events.length===1,"Release-review UI doesnotpay before due date");
    await page.click("#finance-consumer-view");
    await page.waitForSelector(`article[data-contract-id="${captured.contract_id}"] [data-action=cancel]`);
    await page.locator("label:has(#finance-ack)").click();
    const card=page.locator(`article[data-contract-id="${captured.contract_id}"]`);
    response=page.waitForResponse(r=>r.url().endsWith(`/consumer/${captured.contract_id}/cancel`));
    await card.locator("[data-action=cancel]").click();
    const cancelled=(await(await response).json()).contract;
    ok(cancelled.booking_cancelled&&!cancelled.booking_confirmed&&cancelled.refund_krw===250000,"UI paidcancel has exact full refundREVIEW");
    ok(cancelled.actual_money_executed===false,"No live refund/transfer assertion");
   }
   await page.click("#finance-operator-view");
   await page.waitForSelector("#finance-list article[data-contract-id]");
   ok(await page.locator("#finance-list").innerText()!=="","Actual operator financialDOM nonempty");
   ok(await page.locator("[data-action=execute]").count()===0,"No fakeworking settlementaction");
   await page.click("#finance-consumer-view");
   await page.waitForFunction(()=>document.querySelector("#finance-feedback")?.dataset.state==="ready");
   const session=await page.evaluate(async()=>await(await fetch("/hs2/finance/api/session")).json());
   ok(session.sandbox===true&&session.actual_execution_available===false,"Clear trusted sandbox/livegate");
   await page.route("**/hs2/finance/api/session",r=>r.fulfill({status:200,contentType:"application/json",body:JSON.stringify({ok:true,can_consumer:false,can_operator:false,sandbox:true,provider_available:false,actual_execution_available:false})}));
   await page.reload();await page.waitForFunction(()=>document.querySelector("#finance-feedback")?.dataset.state==="error");
   ok(await page.locator("[data-action=cancel]").count()===0,"No selected trustedrole no financialauthority");
   ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),"Desktop/mobile nooverflow");
   ok(errors.length===0,"No JS error "+errors.join(";"));
   await context.close();
  }
 }finally{await browser.close();}
 console.log(`HS2_UI_PASS phase11 ${assertions} assertions`);
}
main().catch(e=>{console.error(e);process.exit(1)});
