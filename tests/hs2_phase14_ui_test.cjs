const assert=require("node:assert/strict"),{chromium}=require("playwright");
const base=process.env.HS2_FIXTURE_ORIGIN;if(!base)throw Error("Owned fixture only");
let count=0;function ok(v,label){assert.ok(v,label);count++;}
async function main(){
 const browser=await chromium.launch({headless:true,executablePath:process.env.HS2_CHROMIUM,args:["--no-sandbox","--disable-gpu"]});
 try{for(const width of [1280,390]){
  const context=await browser.newContext({viewport:{width,height:1000},userAgent:"Mozilla/5.0 Chrome/128.0.0.0 Safari/537.36"});
  const page=await context.newPage(),errors=[];page.on("pageerror",e=>errors.push(e.message));
  await page.goto(base+"/hs2/help/");
  await page.waitForFunction(()=>document.querySelector("#help-feedback")?.dataset.state==="ready");
  ok(await page.locator("#faq-results [data-faq-id]").count()===59,"All first-party server FAQ DOM");
  ok((await page.locator("#help-guides").innerText()).includes("소비자 이용 순서"),"Real guides");
  ok((await page.locator("#help-policies").innerText()).includes("0%")||(await page.locator("#help-policies").innerText()).includes("0%."),"Exact initial zero fee");
  ok(await page.locator('#help-policies a[href="/terms"]').count()===1&&await page.locator('#help-policies a[href="/privacy"]').count()===1,"Existing legal docs preserved");
  await page.locator("#help-audience").selectOption("operator");
  await page.waitForFunction(()=>document.querySelectorAll("#faq-results [data-faq-id]").length===23);
  await page.locator("#help-search").fill("수수료");
  await page.locator("#help-search").press("Enter");
  await page.waitForFunction(()=>document.querySelectorAll("#faq-results [data-faq-id]").length===2);
  await page.locator("#faq-results details summary").first().click();
  ok(await page.locator("#faq-results details[open]").count()===1,"Accessible real answer opens");
  await page.locator("#help-search").fill("no-match-synthetic");
  await page.locator("#help-search").press("Enter");
  await page.waitForFunction(()=>document.querySelector("#help-feedback")?.dataset.state==="ready"&&document.querySelectorAll("#faq-results [data-faq-id]").length===0);
  ok((await page.locator("#faq-results").innerText()).length>5,"Actual empty not invented FAQ");
  await page.locator("#help-search").fill("");
  await page.locator("#help-audience").selectOption("special");
  await page.waitForFunction(()=>document.querySelectorAll("#faq-results [data-faq-id]").length===12);
  ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),"Mobile and desktop nooverflow");
  await page.route("**/hs2/help/api/content**",r=>r.fulfill({status:503,contentType:"application/json",body:JSON.stringify({ok:false,code:"TEST_ONLY_FAIL"})}));
  await page.locator("#help-search").fill("서버 오류");
  await page.locator("#help-search").press("Enter");
  await page.waitForFunction(()=>document.querySelector("#help-feedback")?.dataset.state==="error");
  ok(await page.locator("#faq-results [data-faq-id]").count()===0,"Server failure clears stale content");
  ok(await page.locator("#help-search").inputValue()==="서버 오류","Failure preserves input");
  ok(errors.length===0,"No JS error");
  await context.close();
 }}finally{await browser.close();}
 console.log(`HS2_UI_PASS phase14 ${count} assertions`);
}
main().catch(e=>{console.error(e);process.exit(1)});
