const assert=require("node:assert/strict");
const {chromium}=require("playwright");
const base=process.env.HS2_FIXTURE_ORIGIN;
if(!base)throw Error("Owned SQL HTTP required");
let count=0;const ok=(value,label)=>{assert.ok(value,label);count++;};
async function main(){
 const browser=await chromium.launch({headless:true,executablePath:process.env.HS2_CHROMIUM,args:["--no-sandbox","--disable-gpu"]});
 try{
  for(const width of [1280,390]){
   const context=await browser.newContext({viewport:{width,height:950},userAgent:"Mozilla/5.0 Chrome/128.0.0.0 Safari/537.36"});
   const page=await context.newPage(),errors=[];page.on("pageerror",e=>errors.push(e.message));
   await page.goto(base+"/hs2/search/");
   await page.waitForFunction(()=>document.querySelectorAll(".listing-card").length===2);
   const catalog=await page.evaluate(async()=>await(await fetch("/hs2/search/api/results")).json());
   const stay=catalog.items.find(r=>r.stay_kind==="lodging"),non=catalog.items.find(r=>r.stay_kind==="non_lodging");
   ok(stay&&non,"Actual SQL public items");
   await page.click(`.listing-card[data-public-id="${stay.public_id}"]`);
   await page.waitForSelector(".detail-open-link");
   await page.click(".detail-open-link");
   await page.waitForFunction(()=>document.querySelector("#detail-feedback")?.dataset.state==="ready");
   ok((await page.locator("#detail-title").innerText()).includes("숙박"),"Search selects same public detail");
   ok((await page.locator("#capacity").innerText()).includes("2"),"Disclosed capacity");
   ok((await page.locator("#minimum-stay").innerText()).includes("1"),"Lodging minimum");
   ok(await page.locator("#confirm-quote").isDisabled(),"No receipt without currentquote");
   ok(!await page.locator("#quote-receipt").isVisible(),"No fake confirmation");
   const quote=async(start,end,guests="2")=>{
    await page.fill("#quote-check-in",start);await page.fill("#quote-check-out",end);await page.fill("#quote-guests",guests);
    const pending=page.waitForResponse(r=>r.url().includes("/hs2/details/api/items/")&&r.url().includes("/quote?"));
    await page.click("#request-quote");const response=await pending;
    await page.waitForFunction(()=>!document.querySelector("#request-quote").disabled);
    return {status:response.status(),body:await response.json()};
   };
   let result=await quote("2027-01-01","2027-01-03");
   ok(result.status===200&&result.body.quote.total_krw===200000,"Actual selected two-night total");
   ok((await page.locator("#quote-total").innerText()).includes("200,000"),"ExacttotalDOM");
   ok(await page.locator("#quote-lines").innerText().then(x=>x.includes("100,000")),"Real linebreakdown");
   ok(await page.locator("#confirm-quote").isDisabled(),"Acknowledgment required");
   await page.locator("label:has(#quote-ack)").click();
   const confirm=page.waitForResponse(r=>r.url().endsWith("/confirm-quote"));
   await page.click("#confirm-quote");const receiptResponse=await confirm,receiptBody=await receiptResponse.json();
   await page.waitForSelector("#quote-receipt:visible");
   ok(receiptResponse.status()===200,"Server committed own quote receipt");
   ok(receiptBody.receipt.booking_confirmed===false&&receiptBody.receipt.inventory_held===false,"Not booking/hold/payment");
   ok((await page.locator("#quote-receipt").innerText()).includes("예약"),"Explicit receipt boundary");
   ok((await page.locator("#receipt-expiry").innerText()).length>0,"Actualexpiry visible");
   const check=await page.evaluate(async id=>await(await fetch("/hs2/details/api/receipts/"+id)).json(),receiptBody.receipt.receipt_id);
   ok(check.ok&&check.receipt.quote.total_krw===200000,"Own persisted receipt API");
   await page.fill("#quote-guests","1");
   ok(await page.locator("#quote-receipt").isHidden(),"Inputchange clears receipt immediately");
   ok(await page.locator("#confirm-quote").isDisabled(),"Inputchange clears quote ack");
   ok(!(await page.locator("#quote-total").innerText()).includes("200,000"),"No stale price after changedguest");
   result=await quote("2027-01-01","2027-01-03","3");
   ok(result.status===400,"Actual overcapacity rejected");
   ok(!(await page.locator("#quote-total").innerText()).includes("200,000"),"Rejectedcapacity notoldprice");
   await page.goto(base+`/hs2/details/?public_id=${non.public_id}&check_in=2027-01-01&check_out=2027-01-15&guests=2`);
   await page.waitForFunction(()=>document.querySelector("#detail-feedback")?.dataset.state==="ready");
   ok((await page.locator("#minimum-stay").innerText()).includes("7"),"Nonlodging minimum7");
   result=await quote("2027-01-01","2027-01-15");
   ok(result.body.quote.total_krw===600000,"Exact two weeks");
   result=await quote("2027-01-31","2027-02-28");
   ok(result.body.quote.total_krw===1000000&&result.body.quote.lines[0].unit==="month","Anchoredmonth not30days");
   result=await quote("2027-01-01","2027-01-09");
   ok(result.status===400,"No partialweek conversion");
   await page.route("**/hs2/details/api/session",r=>r.fulfill({status:200,contentType:"application/json",body:JSON.stringify({ok:true,can_confirm_quote:false,csrf_token:null,booking_confirmed:false,inventory_held:false})}));
   await page.goto(base+`/hs2/details/?public_id=${stay.public_id}`);
   await page.waitForFunction(()=>document.querySelector("#detail-feedback")?.dataset.state==="ready");
   await quote("2027-01-01","2027-01-03");
   await page.locator("label:has(#quote-ack)").click();
   ok(await page.locator("#confirm-quote").isDisabled(),"No consumer session no protectedconfirm");
   await page.unroute("**/hs2/details/api/session");
   await page.reload();await page.waitForFunction(()=>document.querySelector("#detail-feedback")?.dataset.state==="ready");
   await page.evaluate(()=>{
    const original=fetch.bind(window);
    window.fetch=async(...args)=>{const r=await original(...args);if(String(args[0]).includes("/quote?"))await new Promise(done=>setTimeout(done,180));return r;};
   });
   await page.fill("#quote-check-in","2027-01-01");await page.fill("#quote-check-out","2027-01-03");await page.fill("#quote-guests","2");
   const pending=page.waitForResponse(r=>r.url().includes("/quote?"));
   await page.click("#request-quote");await pending;await page.fill("#quote-guests","1");await page.waitForTimeout(220);
   ok(!(await page.locator("#quote-total").innerText()).includes("200,000"),"Late quote ignored afterinputchanges");
   ok(await page.locator("#confirm-quote").isDisabled(),"Late response cannot enable receipt");
   ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),"Responsive nooverflow");
   ok(errors.length===0,"No browsererror "+errors.join(";"));
   await context.close();
  }
 }finally{await browser.close();}
 console.log(`HS2_UI_PASS phase9 ${count} assertions`);
}
main().catch(e=>{console.error(e);process.exit(1)});
