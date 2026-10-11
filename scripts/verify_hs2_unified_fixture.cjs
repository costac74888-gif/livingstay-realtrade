/* The owned harness supplies exactly one loopback origin and no real keys. */
const {chromium}=require("playwright"), assert=require("node:assert/strict"), fs=require("node:fs");
const origin=process.env.HS2_FIXTURE_ORIGIN, out="generated-artifacts/unified-preview";
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.HS2_CHROMIUM,args:["--no-sandbox"]});
 const context=await browser.newContext({userAgent:"Mozilla/5.0 Chrome/138.0.0.0 Safari/537.36"});
 await context.route("**/*",route=>{
  const url=new URL(route.request().url());
  return url.origin===origin ? route.continue() : route.abort();
 });
 const page=await context.newPage();
 const errors=[];page.on("pageerror",e=>errors.push(e.message));fs.mkdirSync(out,{recursive:true});
 try {
  await page.goto(origin+"/hs2/admin/login");
  const status=await page.evaluate(async()=> (await fetch("/__development__/status")).json());
  assert.equal(status.database,"owned_ephemeral");assert.equal(status.actual_toss,false);
  const denied=await page.evaluate(async()=> (await fetch("/hs2/admin/")).status);assert.equal(denied,403);
  await page.locator('[name="username"]').fill("preview-admin");
  await page.locator('[name="password"]').fill("synthetic-auth-fixture-only");
  await Promise.all([page.waitForURL("**/hs2/admin/"),page.locator("#admin-login-form button").click()]);
  for(const width of [1440,390]){
   await page.setViewportSize({width,height:1000});
   await page.goto(origin+"/hs2/admin/");
   await page.waitForTimeout(400);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
   await page.screenshot({path:out+`/admin-isolated-${width}.png`,fullPage:true});
  }
  const registration=await page.evaluate(async()=>{
   const api=async(path,body,csrf)=>{
    const r=await fetch(path,{method:body===undefined?"GET":"POST",headers:{
     "X-HS2-CSRF":csrf||"",...(body instanceof FormData?{}:{"Content-Type":"application/json"})},
     ...(body===undefined?{}:{body:body instanceof FormData?body:JSON.stringify(body)})});
    const data=await r.json();if(!r.ok)throw Error(path+":"+r.status+":"+data.code);return data;
   };
   const meta=await api("/hs2/listings/meta"), form=new FormData();
   form.append("file",await (await fetch("/__development__/seongsu/assets/interior-1.jpg")).blob(),"synthetic.jpg");
   const photo=await api("/hs2/listings/photos",form,meta.csrf);
   const created=await api("/hs2/listings/applications",{workflow_id:meta.references[0].workflow_id,payload:{
    title:"[가상] 올리브 통합 검사",space_label:"UNIFIED-"+Date.now(),space_scope:"unit",stay_kind:"lodging",
    rooms:1,area_m2:"25",guests:2,options:["wifi"],nightly:80000,weekly:null,monthly:null,min_stay:1,
    instant:false,discount:false,photos:[photo.id],responsibility:true,public_summary:true,disclosure:"limited"}},meta.csrf);
   const submitted=await api("/hs2/listings/applications/"+created.item.id+"/submit",{revision:created.item.revision},meta.csrf);
   const admin=await api("/hs2/listings/admin/meta");
   const approved=await api("/hs2/listings/admin/applications/"+created.item.id+"/review",{
    revision:submitted.item.revision,decision:"approve",note:"격리 가상 등록",rights:true,disclosure:true},admin.csrf);
   const publicResult=await api("/hs2/search/api/results?layers=stay");
   return {draft:created.item.status,submitted:submitted.item.status,approved:approved.item.status,
    published:publicResult.items.some(r=>r.public_id===approved.item.public_id),
    application_id:created.item.id,public_id:approved.item.public_id};
  });
  assert.equal(registration.draft,"draft");assert.equal(registration.submitted,"submitted");
  assert.equal(registration.approved,"approved");assert.equal(registration.published,true);
  const flow=await page.evaluate(async(registration)=>{
   const api=async(path,body,csrf)=>{
    const r=await fetch(path,{method:body===undefined?"GET":"POST",headers:{
     "Content-Type":"application/json","X-HS2-CSRF":csrf||"","X-CSRF-Token":csrf||""},
     ...(body===undefined?{}:{body:JSON.stringify(body)})});
    const data=await r.json();if(!r.ok)throw Error(path+":"+r.status+":"+data.code);return data;
   };
   const meta=await api("/hs2/calendar/meta");
   const path="/hs2/calendar/applications/"+registration.application_id+"/prices";
   const state=(await api(path)).item;
   await api(path,{version:state.version,source_revision:state.source_revision,command:{
    start:"2027-01-01",end:"2027-01-11",inclusive:true,action:"nightly",
    values:Object.fromEntries(Array.from({length:7},(_,i)=>[String(i),80000]))}},meta.csrf);
   const selection={public_id:registration.public_id,check_in:"2027-01-01",check_out:"2027-01-03",guests:2};
   const q=(await api("/hs2/details/api/items/"+selection.public_id+
    "/quote?check_in="+selection.check_in+"&check_out="+selection.check_out+"&guests=2")).quote;
   const session=await api("/hs2/details/api/session");
   const receipt=(await api("/hs2/details/api/items/"+selection.public_id+"/confirm-quote",{
    check_in:selection.check_in,check_out:selection.check_out,guests:selection.guests,
    request_id:crypto.randomUUID(),acknowledged:true,expected_source_version:q.source_version},session.csrf_token)).receipt;
   const bookings=await api("/hs2/bookings/api/session");
   const booking=(await api("/hs2/bookings/api/request",{
    receipt_id:receipt.receipt_id,request_id:crypto.randomUUID(),acknowledged:true},bookings.consumer_csrf)).booking;
   const approved=(await api("/hs2/bookings/api/operator/"+booking.booking_id+"/action",{
    action:"approve",revision:booking.revision},bookings.operator_csrf)).booking;
   const finance=await api("/hs2/finance/api/session");
   const terms=(await api("/hs2/finance/api/quote/"+booking.booking_id)).quote;
   const contract=(await api("/hs2/finance/api/contracts",{booking_id:booking.booking_id,
    request_id:crypto.randomUUID(),acknowledged:true,expected_terms_sha256:terms.terms_sha256},finance.consumer_csrf)).contract;
   const captured=await api("/__development__/seongsu/payments/"+contract.contract_id+"/capture",
    {acknowledged:true},finance.consumer_csrf);
   return {booking_id:booking.booking_id,public_id:selection.public_id,total_krw:q.total_krw,
    before_payment:approved.status,payment_verified_before:approved.payment_verified,
    mock_payment_verified:captured.contract.payment_verified,actual_toss:"NOT_RUN"};
  },registration);
  assert.equal(flow.total_krw,160000);
  assert.equal(flow.payment_verified_before,false);assert.equal(flow.mock_payment_verified,true);
  await page.goto(origin+"/hs2/workspace/?booking_id="+flow.booking_id);
  await page.waitForFunction(()=>document.querySelector("#workspace-feedback")?.dataset.state==="ready");
  await page.locator(".entry-action").click();
  await page.waitForFunction(()=>document.querySelector("#workspace-feedback")?.textContent.includes("대화가 서버에서 확인"));
  const threads=await page.evaluate(async()=> (await(await fetch("/hs2/workspace/api/threads?view=consumer")).json()).items);
  const thread=threads.find(t=>t.booking_id===flow.booking_id);assert(thread);
  await page.locator(`[data-thread-id="${thread.thread_id}"]`).click();
  const message="[가상] 예약자 질문 "+Date.now(),reply="[가상] 임대인 답변 "+Date.now();
  await page.locator("#message-body").fill(message);await page.locator("#send-message").click();
  await page.waitForFunction(t=>document.querySelector("#messages-list")?.textContent.includes(t),message);
  await page.goto(origin+"/hs2/workspace/?view=operator&thread_id="+thread.thread_id);
  await page.waitForFunction(t=>document.querySelector("#messages-list")?.textContent.includes(t),message);
  await page.locator("#message-body").fill(reply);await page.locator("#send-message").click();
  await page.waitForFunction(t=>document.querySelector("#messages-list")?.textContent.includes(t),reply);
  await page.goto(origin+"/hs2/workspace/?view=consumer&thread_id="+thread.thread_id);
  await page.waitForFunction(t=>document.querySelector("#messages-list")?.textContent.includes(t),reply);
  await page.screenshot({path:out+"/chat-roundtrip-isolated-390.png",fullPage:true});
  flow.chat_roundtrip="PASS";
  await page.goto(origin+"/hs2/listings/admin");
  await page.waitForTimeout(300);
  await page.screenshot({path:out+"/registration-review-isolated.png",fullPage:true});
  await page.locator("#preview-admin-logout").click();
  await page.waitForURL("**/hs2/consumer");
  assert.equal(await page.evaluate(async()=> (await fetch("/hs2/admin/")).status),403);
  assert.equal(await page.locator('.header-action[href="/hs2/admin/"]').count(),0);
  assert.deepEqual(errors,[]);
  const report={status:"PASS",admin_password_auth:"owned_test_account_only",registration,flow,
   signed_in_admin_ui:"verified_in_owned_isolated_server",widths:[1440,390],actual_toss:"NOT_RUN",production_accounts_connected:false};
  fs.writeFileSync(out+"/auth-registration.json",JSON.stringify(report,null,2));console.log(JSON.stringify(report));
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
