const assert=require("node:assert/strict");
const {chromium}=require("playwright");
const base=process.env.HS2_FIXTURE_ORIGIN;
if(!base)throw Error("Owned SQL HTTP required");
let count=0;const ok=(value,label)=>{assert.ok(value,label);count++;};
async function main(){
 const browser=await chromium.launch({headless:true,executablePath:process.env.HS2_CHROMIUM,args:["--no-sandbox","--disable-gpu"]});
 try{
  for(const [width,start,end] of [[1280,"2027-01-01","2027-01-03"],[390,"2027-01-03","2027-01-05"]]){
   const context=await browser.newContext({viewport:{width,height:950},userAgent:"Mozilla/5.0 Chrome/128.0.0.0 Safari/537.36"});
   const page=await context.newPage(),errors=[];page.on("pageerror",e=>errors.push(e.message));
   await page.goto(base+"/hs2/search/");
   await page.waitForFunction(()=>document.querySelectorAll(".listing-card").length===2);
   const id=await page.evaluate(async()=>{const x=await(await fetch("/hs2/search/api/results")).json();return x.items.find(r=>r.stay_kind==="lodging").public_id;});
   await page.goto(base+`/hs2/details/?public_id=${id}`);
   await page.waitForFunction(()=>document.querySelector("#detail-feedback")?.dataset.state==="ready");
   await page.fill("#quote-check-in",start);await page.fill("#quote-check-out",end);await page.fill("#quote-guests","2");
   let pending=page.waitForResponse(r=>r.url().includes("/quote?"));await page.click("#request-quote");await pending;
   await page.locator("label:has(#quote-ack)").click();
   pending=page.waitForResponse(r=>r.url().endsWith("/confirm-quote"));await page.click("#confirm-quote");await pending;
   await page.waitForSelector("#quote-receipt:visible");
   const link=page.locator("#quote-receipt a[href^='/hs2/bookings/']");
   ok(await link.isVisible(),"Real persisted quote receipt opens bookingrequest");
   await link.click();await page.waitForFunction(()=>document.querySelector("#booking-quote")?.textContent.includes("200,000"));
   ok((await page.locator("#booking-quote").innerText()).includes("200,000"),"Original exactquote amount");
   ok(await page.locator("#request-booking").isDisabled(),"No implicit bookingack");
   await page.locator("label:has(#booking-ack)").click();
   pending=page.waitForResponse(r=>r.url().endsWith("/api/request"));await page.click("#request-booking");
   const created=await pending,body=await created.json();
   ok(created.status()===200&&body.booking.status==="pending_operator","Actual SQL request persisted");
   ok(!body.booking.booking_confirmed&&!body.booking.payment_verified&&body.booking.inventory_held,"Pendinghold notpaid/confirmed");
   const key=body.booking.booking_id,card=page.locator(`.booking-card[data-booking-id="${key}"]`);
   await card.waitFor();ok((await card.innerText()).includes("200,000"),"Server owned cardnonempty");
   ok(await card.locator("[data-action=cancel]").isVisible(),"Consumer cancellation UI");
   await page.click("#operator-view");
   await page.waitForSelector(`[data-booking-id="${key}"] [data-action=approve]`);
   pending=page.waitForResponse(r=>r.url().endsWith(`/operator/${key}/action`));await card.locator("[data-action=approve]").click();
   const approved=await(await pending).json();
   ok(approved.booking.status==="awaiting_payment"&&!approved.booking.payment_verified&&!approved.booking.booking_confirmed,"Operatorapproval notfakepayment");
   await page.click("#consumer-view");
   await page.waitForSelector(`[data-booking-id="${key}"] [data-action=cancel]`);
   ok(await card.locator("[data-action=confirm-payment]").count()===0,"Unconfigured livePG cannotshowPayDonebutton");
   pending=page.waitForResponse(r=>r.url().endsWith(`/consumer/${key}/action`));await card.locator("[data-action=cancel]").click();
   const cancelled=await(await pending).json();
   ok(cancelled.booking.status==="cancelled"&&!cancelled.booking.inventory_held,"Server cancellation releaseshold");
   await page.reload();await page.waitForFunction(()=>document.querySelector("#booking-feedback")?.dataset.state==="ready");
   ok(await page.locator(`[data-booking-id="${key}"]`).count()===1,"Cancellation history persisted");
   ok(await page.locator(`[data-booking-id="${key}"] [data-action=cancel]`).count()===0,"Terminal no revivalcontrol");
   const availability=await page.evaluate(async x=>await(await fetch(`/hs2/details/api/items/${x.id}/quote?check_in=${x.start}&check_out=${x.end}&guests=2`)).json(),{id,start,end});
   ok(availability.ok&&availability.quote.total_krw===200000,"Original calendar seesreleased inventory");
   const receipt=await page.evaluate(async x=>{
    const q=await(await fetch(`/hs2/details/api/items/${x.id}/quote?check_in=${x.start}&check_out=${x.end}&guests=2`)).json();
    return await(await fetch(`/hs2/details/api/items/${x.id}/confirm-quote`,{method:"POST",headers:{"Content-Type":"application/json","X-CSRF-Token":"isolated-consumer-csrf-not-real-session"},body:JSON.stringify({check_in:x.start,check_out:x.end,guests:2,acknowledged:true,request_id:crypto.randomUUID(),expected_source_version:q.quote.source_version})})).json();
   },{id,start,end});
   await page.goto(base+`/hs2/bookings/?receipt_id=${receipt.receipt.receipt_id}`);
   await page.waitForFunction(()=>document.querySelector("#booking-quote")?.textContent.includes("200,000"));
   await page.locator("label:has(#booking-ack)").click();
   pending=page.waitForResponse(r=>r.url().endsWith("/api/request"));await page.click("#request-booking");
   const second=(await(await pending).json()).booking,key2=second.booking_id;
   await page.click("#operator-view");
   await page.waitForSelector(`[data-booking-id="${key2}"] [data-action=reject]`);
   pending=page.waitForResponse(r=>r.url().endsWith(`/operator/${key2}/action`));await page.locator(`[data-booking-id="${key2}"] [data-action=reject]`).click();
   const rejected=(await(await pending).json()).booking;
   ok(rejected.status==="rejected"&&!rejected.inventory_held,"Realoperator rejection UI andslot release");
   await page.route("**/hs2/bookings/api/session",r=>r.fulfill({status:200,contentType:"application/json",body:JSON.stringify({ok:true,can_consumer:false,can_operator:false,payment_available:false})}));
   await page.reload();await page.waitForFunction(()=>document.querySelector("#booking-feedback")?.dataset.state==="error");
   ok(await page.locator("[data-action=approve]").count()===0,"Missingtrustedselectedrole blocksoperatorcontrol");
   await page.unroute("**/hs2/bookings/api/session");
   await page.goto(base+"/hs2/bookings/?view=consumer");await page.waitForFunction(()=>document.querySelector("#booking-feedback")?.dataset.state==="ready");
   ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),"Desktop/mobile nooverflow");
   ok(errors.length===0,"No JSerror "+errors.join(";"));
   await context.close();
  }
 }finally{await browser.close();}
 console.log(`HS2_UI_PASS phase10 ${count} assertions`);
}
main().catch(e=>{console.error(e);process.exit(1)});
