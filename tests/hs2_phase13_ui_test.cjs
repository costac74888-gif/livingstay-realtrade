const assert=require("node:assert/strict"),{chromium}=require("playwright");
const base=process.env.HS2_FIXTURE_ORIGIN;if(!base)throw Error("Owned fixture only");
let count=0;function ok(v,label){assert.ok(v,label);count++;}
async function main(){
 const browser=await chromium.launch({headless:true,executablePath:process.env.HS2_CHROMIUM,args:["--no-sandbox","--disable-gpu"]});
 try{for(const width of [1280,390]){
  const context=await browser.newContext({viewport:{width,height:1000},userAgent:"Mozilla/5.0 Chrome/128.0.0.0 Safari/537.36"});
  const page=await context.newPage(),errors=[];page.on("pageerror",e=>errors.push(e.message));
  await page.goto(base+"/hs2/workspace/");
  await page.waitForFunction(()=>document.querySelector("#workspace-feedback")?.dataset.state==="ready");
  if(width===1280){
   const retries=page.locator("#notifications-list button").filter({hasText:"재시도"});
   ok(await retries.count()>0,"Real failed sandbox delivery retry action");
   const response=page.waitForResponse(r=>r.url().includes("/deliveries/")&&r.url().endsWith("/retry"));
   await retries.first().click();ok((await response).ok(),"Owned failed delivery queued not sent");
  }
  for(const [list,key] of [["favorites-list","public-id"],["threads-list","thread-id"],["my-bookings-list","booking-id"],["notifications-list","notification-id"]])
   ok(await page.locator(`#${list} [data-${key}]`).count()>0,"Real nonempty "+list);
  await page.locator("#threads-list [data-thread-id]").first().click();
  await page.waitForFunction(()=>document.querySelectorAll("#messages-list [data-message-id]").length>0);
  const before=await page.locator("#messages-list [data-message-id]").count();
  await page.locator("#message-body").fill("브라우저 실제 저장 <img src=x onerror=alert(1)>");
  await page.click("#send-message");
  await page.waitForFunction(n=>document.querySelectorAll("#messages-list [data-message-id]").length>n,before);
  ok(await page.locator("#messages-list img").count()===0,"Message rendered text only");
  await page.reload();
  await page.waitForFunction(()=>document.querySelector("#workspace-feedback")?.dataset.state==="ready");
  await page.locator("#threads-list [data-thread-id]").first().click();
  await page.waitForFunction(()=>document.querySelector("#messages-list")?.textContent.includes("브라우저 실제 저장"));
  ok(true,"Message persisted refresh");
  await page.route("**/hs2/workspace/api/threads/*/messages?view=consumer",r=>r.request().method()==="POST"?r.fulfill({status:503,contentType:"application/json",body:JSON.stringify({ok:false,code:"TEST_ONLY_FAIL"})}):r.continue());
  await page.locator("#message-body").fill("오류 후 재시도 보존");
  await page.click("#send-message");
  await page.waitForFunction(()=>document.querySelector("#workspace-feedback")?.dataset.state==="error");
  ok(await page.locator("#message-body").inputValue()==="오류 후 재시도 보존","Failed send preserves text");
  await page.unroute("**/hs2/workspace/api/threads/*/messages?view=consumer");
  await page.click("#send-message");
  await page.waitForFunction(()=>document.querySelector("#messages-list")?.textContent.includes("오류 후 재시도 보존"));
  const saved=await page.locator("#favorites-list [data-public-id]").first().getAttribute("data-public-id");
  await page.locator("#favorites-list button").filter({hasText:"저장 해제"}).first().click();
  await page.waitForFunction(()=>document.querySelectorAll("#favorites-list [data-public-id]").length===0);
  await page.goto(base+"/hs2/details/?public_id="+saved);
  await page.waitForFunction(()=>document.querySelector("#save-interest")&&!document.querySelector("#save-interest").disabled);
  await page.click("#save-interest");
  await page.waitForFunction(()=>document.querySelector("#save-interest")?.textContent.includes("해제"));
  await page.click("#start-inquiry");
  await page.waitForURL("**/hs2/workspace/?view=consumer&thread_id=*");
  await page.waitForFunction(()=>document.querySelector("#workspace-feedback")?.dataset.state==="ready");
  ok(await page.locator("#favorites-list [data-public-id]").count()===1,"Actual details save inquiry and reentry");
  await page.locator("#email-enabled").uncheck();await page.locator("#sms-enabled").uncheck();
  await page.click("#save-preferences");
  await page.waitForFunction(()=>document.querySelector("#workspace-feedback")?.textContent.includes("동의를 저장"));
  const pref=await page.evaluate(async()=> (await(await fetch("/hs2/workspace/api/preferences")).json()).preferences);
  ok(!pref.email_enabled&&!pref.sms_enabled&&!pref.live_delivery_enabled,"Real optout no live sending");
  ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),"Responsive nooverflow");
  ok(errors.length===0,"No JS error "+errors.join(";"));
  await page.goto(base+"/hs2/workspace/?view=operator");
  await page.waitForFunction(()=>document.querySelector("#workspace-feedback")?.dataset.state==="ready");
  ok(await page.locator("#threads-list [data-thread-id]").count()>0,"Real approved operator participant view");
  await page.goto(base+"/hs2/workspace/");
  await page.waitForFunction(()=>document.querySelector("#workspace-feedback")?.dataset.state==="ready");
  await page.route("**/hs2/workspace/api/meta?view=consumer",r=>r.fulfill({status:403,contentType:"application/json",body:JSON.stringify({ok:false,code:"VERIFIED_CONSUMER_REQUIRED"})}));
  await page.click("#workspace-refresh");
  await page.waitForFunction(()=>document.querySelector("#workspace-feedback")?.dataset.state==="error");
  ok(await page.locator("#threads-list [data-thread-id]").count()===0,"Session failure clears private records");
  await context.close();
 }}finally{await browser.close();}
 console.log(`HS2_UI_PASS phase13 ${count} assertions`);
}
main().catch(e=>{console.error(e);process.exit(1)});
