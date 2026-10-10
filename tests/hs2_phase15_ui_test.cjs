const assert=require("node:assert/strict"),{chromium}=require("playwright");
const base=process.env.HS2_FIXTURE_ORIGIN;if(!base)throw Error("Owned fixture only");
let count=0;function ok(v,label){assert.ok(v,label);count++;}
async function main(){
 const browser=await chromium.launch({headless:true,executablePath:process.env.HS2_CHROMIUM,args:["--no-sandbox","--disable-gpu"]});
 try{for(const width of [1280,390]){
  const ctx=await browser.newContext({viewport:{width,height:1000},userAgent:"Mozilla/5.0 Chrome/128.0.0.0 Safari/537.36"});
  const page=await ctx.newPage(),errors=[];page.on("pageerror",e=>errors.push(e.message));
  await page.goto(base+"/hs2/help/");
  await page.evaluate(()=>fetch("/hs2/listings-fixture/identity",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({admin:true})}));
  await page.goto(base+"/hs2/admin/");
  const ready=()=>page.waitForFunction(()=>document.querySelector("#admin-feedback")?.dataset.state==="ready"&&!document.querySelector("#admin-record-form [type=submit]")?.disabled);
  await ready();
  ok((await page.locator("#admin-registrations").innerText()).length>100,"Real registrations and calendar price");
  ok((await page.locator("#admin-bookings").innerText()).includes("2027"),"Real booking records");
  ok((await page.locator("#admin-finances").innerText()).includes("KRW")||(await page.locator("#admin-finances").innerText()).includes("원"),"Actual immutable finance");
  ok(await page.locator('a[href="/admin"]').count()>0,"Old admin preserved");
  await page.locator("#admin-record-kind").selectOption("faq");
  const form=page.locator("#admin-record-form");
  await form.locator('[name="faq_id"]').selectOption("consumer-1");
  const title="실제 관리자 질문 "+width+"?";
  await form.locator('[name="question"]').fill(title);
  await form.locator('[name="answer"]').fill("<script>window.__unsafe=1</script> 실행되지 않는 관리자 답변");
  await page.route("**/hs2/admin/api/overview",async route=>{await new Promise(resolve=>setTimeout(resolve,700));await route.continue();});
  await form.locator('[type=submit]').click();
  await page.waitForFunction(()=>document.querySelector("#admin-feedback")?.dataset.state==="loading");
  ok(await page.locator("#admin-record-kind").isDisabled(),"Pending real write locks follow-up editing");
  await ready();
  await page.unroute("**/hs2/admin/api/overview");
  const record=page.locator("#admin-records article[data-record-id]").filter({hasText:title}).first();
  await record.waitFor();
  ok((await record.innerText()).includes("draft")||(await record.innerText()).includes("초안"),"Persisted draft DOM");
  const id=await record.getAttribute("data-record-id");
  await page.locator("#admin-review-note").fill("안내 검토 실제 승인");
  await record.locator('[data-action=approve]').click();await ready();
  const body=await page.evaluate(()=>fetch("/hs2/help/api/content").then(r=>r.json()));
  ok(body.faqs.find(f=>f.id==="consumer-1").question===title,"Approved content from real API");
  ok(await page.evaluate(()=>window.__unsafe===undefined),"No HTML execution");
  await page.reload();await ready();
  const persisted=page.locator(`#admin-records article[data-record-id="${id}"]`);
  ok((await persisted.innerText()).includes(title),"Reload persisted");
  await persisted.locator('[data-action=edit]').click();
  await form.locator('[name="question"]').fill(title+" 수정");
  await page.locator("#admin-review-note").fill("수정 근거");
  await form.locator('[type=submit]').click();await ready();
  ok((await page.locator(`#admin-records article[data-record-id="${id}"]`).innerText()).includes("수정"),"Actual revision edit");
  await page.locator("#admin-review-note").fill("보관 처리");
  await page.locator(`#admin-records article[data-record-id="${id}"] [data-action=archive]`).click();await ready();
  ok((await page.locator("#admin-audits").innerText()).length>50,"Actual append-only audits");
  await page.locator("#admin-record-kind").selectOption("policy");
  ok(await form.locator('[name=platform_bps]').inputValue()==="0","Fixed initial zero platform");
  const application=await page.evaluate(()=>fetch("/hs2/admin/api/overview").then(r=>r.json()).then(b=>b.registrations[0].application_id));
  for(const kind of ["policy","promotion","report","review"]){
   await page.locator("#admin-record-kind").selectOption(kind);
   const data=kind==="policy"?{title:"개발 정책 "+width,note:"격리 비용 확인",deposit_krw:"60000",pg_processing_krw:"3000",deposit_return_days:"7",settlement_days:"2"}
    :{application_id:application,title:kind+" 실제 기록 "+width,note:"실제 검토 메모",...(kind==="promotion"?{start:"2027-01-01",end:"2027-02-01",amount_krw:"10000"}:{})};
   for(const [key,value] of Object.entries(data)){
    const input=form.locator(`[name="${key}"]`);
    if(await input.evaluate(e=>e.tagName==="SELECT"))await input.selectOption(value);else await input.fill(value);
   }
   await form.locator('[type=submit]').click();await ready();
   const row=page.locator("#admin-records article[data-record-id]").filter({hasText:data.title}).first();
   await row.waitFor();await page.locator("#admin-review-note").fill("유형별 실제 승인");
   await row.locator('[data-action=approve]').click();await ready();
   ok((await row.innerText()).includes("승인"),"Actual "+kind+" form creates and approves");
  }
  if(width===1280)await page.screenshot({path:".local/hs2-harness/phase15-admin-rendered.jpg"});
  ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),"Desktop/mobile nooverflow");
  await page.evaluate(()=>fetch("/hs2/listings-fixture/identity",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({admin:false})}));
  await page.reload();
  ok(await page.locator("#admin-records").count()===0,"Revoked admin protected data cleared");
  ok(errors.length===0,"No browser JS error");
  await ctx.close();
 }}finally{await browser.close();}
 console.log(`HS2_UI_PASS phase15 ${count} assertions`);
}
main().catch(e=>{console.error(e);process.exit(1)});
