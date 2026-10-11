/* Owned fictional Preview only. No production origin, account, payment or delivery. */
const {chromium}=require("playwright");
const assert=require("node:assert/strict"),fs=require("node:fs");
const origin="https://"+process.env.REPLIT_DEV_DOMAIN, out="generated-artifacts/rate-ui";
const ui=require("./hs2_demo_assets/preview-rate-date.js");
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.HS2_CHROMIUM,args:["--no-sandbox"]});
 const context=await browser.newContext({userAgent:"Mozilla/5.0 Chrome/138.0.0.0 Safari/537.36"});
 const failures=[],errors=[],results=[];
 await context.route("**/*",route=>{
  const u=new URL(route.request().url());
  const hosts=["dapi.kakao.com","map.kakao.com","rv.map.kakao.com","fonts.googleapis.com","fonts.gstatic.com"];
  if(["data:","blob:"].includes(u.protocol)||u.origin===origin||hosts.includes(u.hostname)||
      /\.daumcdn\.net$|\.kakaocdn\.net$/.test(u.hostname))return route.continue();
  failures.push(u.origin);return route.abort();
 });
 const page=await context.newPage();
 page.on("pageerror",e=>errors.push(e.message));
 try{
  await page.goto(origin+"/__development__/seongsu/");
  const data=await page.evaluate(async()=>{
   const status=await(await fetch("/__development__/status")).json();
   const catalog=await(await fetch("/__development__/seongsu/catalog")).json();
   return{status,catalog};
  });
  assert.equal(data.catalog.synthetic,true);assert.equal(data.catalog.actual_toss,false);
  const start=data.catalog.default_check_in, seven=ui.addDays(start,7), ten=ui.addDays(start,10);
  const criteria=`layers=stay&q=성수&check_in=${start}&check_out=${seven}`;
  async function loaded(path,selector){
   await page.goto(origin+path);await page.waitForSelector(selector,{timeout:20000});
   await page.waitForFunction(()=>document.querySelector("#searchForm")?.getAttribute("aria-busy")!=="true",{timeout:20000});
  }
  for(const width of [1440,390]){
   await page.setViewportSize({width,height:width===390?844:980});
   await loaded("/hs2/search/?"+criteria,".listing-card");
   const cards=await page.locator(".listing-card").allTextContents();
   assert(cards.some(t=>t.includes("1박")&&t.includes("원")));
   assert(cards.some(t=>t.includes("1주")||t.includes("1개월")));
   assert(!cards.some(t=>/선택 \d+주/.test(t)));
   await page.getByRole("button",{name:"주·월형",exact:true}).click();
   assert.equal(await page.locator("#check_out").inputValue(),seven);
   await page.getByRole("button",{name:"1개월",exact:true}).click();
   await page.waitForFunction(()=>document.querySelector("#searchForm")?.getAttribute("aria-busy")!=="true");
   assert.equal(await page.locator("#check_out").inputValue(),ui.addMonthsClamped(start,1));
   assert(new URL(page.url()).searchParams.get("kind")==="non_lodging");
   await page.reload();
   await page.waitForSelector(".listing-card");
   await page.waitForFunction(()=>document.querySelector("#searchForm")?.getAttribute("aria-busy")!=="true");
   assert.equal(await page.locator("#check_out").inputValue(),ui.addMonthsClamped(start,1));
   assert.equal(await page.getByRole("button",{name:"주·월형",exact:true}).getAttribute("aria-pressed"),"true");
   await page.evaluate(()=>history.pushState({}, "", location.href));
   await page.getByRole("button",{name:"숙박형",exact:true}).click();
   await page.goBack();
   await page.waitForFunction(()=>document.querySelector("#kind").value==="non_lodging" &&
     document.querySelector("#searchForm").getAttribute("aria-busy")!=="true");
   assert.equal(await page.locator("#check_out").inputValue(),ui.addMonthsClamped(start,1));
   assert.equal(await page.getByRole("button",{name:"주·월형",exact:true}).getAttribute("aria-pressed"),"true");
   await page.screenshot({path:`${out}/map-${width}.png`});
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
   results.push({viewport:width,case:"map base, kind, calendar-month, URL, layout",pass:true});
   await loaded("/hs2/search/?"+criteria.replace(seven,ten)+"&kind=non_lodging",".preview-period-issue");
   const candidate=page.locator(".preview-candidate").first();
   const chosen=(await candidate.textContent()).match(/\d{4}-\d{2}-\d{2}/)[0];
   await candidate.click();
   await page.waitForFunction(()=>document.querySelector("#searchForm")?.getAttribute("aria-busy")!=="true");
   assert.equal(await page.locator("#check_out").inputValue(),chosen);
   await page.waitForSelector(".preview-quote",{timeout:15000});
   results.push({viewport:width,case:"10 day actual period failure and re-quoted candidate",pass:true});
   await loaded("/hs2/search/?"+criteria.replace(seven,ui.addDays(start,1)),".preview-week-toggle");
   assert.match(await page.locator(".preview-period-hidden").textContent(),/7일 이상/);
   await page.locator(".preview-week-toggle").click();
   await page.waitForFunction(()=>document.querySelector("#searchForm")?.getAttribute("aria-busy")!=="true");
   assert.equal(await page.locator("#check_out").inputValue(),seven);
   results.push({viewport:width,case:"minimum period count shortcut",pass:true});
   await loaded("/hs2/consumer?"+criteria+"&kind=non_lodging",".listing-card");
   assert.match(await page.locator("#listingList").textContent(),/1주|1개월/);
   await page.getByRole("button",{name:"3개월",exact:true}).click();
   assert.equal(await page.locator("#check_out").inputValue(),ui.addMonthsClamped(start,3));
   await page.waitForFunction(()=>document.querySelector("#searchForm")?.getAttribute("aria-busy")!=="true");
   await page.screenshot({path:`${out}/consumer-${width}.png`});
   results.push({viewport:width,case:"native consumer same rates and month helper",pass:true});
  }
  await page.setViewportSize({width:1440,height:980});
  await page.goto(origin+"/hs2/listings/");
  await page.waitForSelector("#workflowSelect option:nth-child(2)",{state:"attached"});
  await page.locator("#newApplication").click();
  await page.locator("#workflowSelect").selectOption({index:1});
  await page.locator("#stay_kind").selectOption("lodging");
  await page.locator("#nightly").fill("178000");
  assert.match(await page.locator("#previewRateSummary").textContent(),/1박 178,000원/);
  assert.equal(await page.locator("#weekly").isVisible(),false);
  await page.locator("#stay_kind").selectOption("non_lodging");
  assert.equal(await page.locator("#nightly").inputValue(),"");
  assert.equal(await page.locator("#nightly").isDisabled(),true);
  await page.locator("#weekly").fill("300000");await page.locator("#monthly").fill("1600000");
  assert.match(await page.locator("#previewRateSummary").textContent(),/5배/);
  await page.locator("#monthly").fill("600000");
  assert(!/배보다/.test(await page.locator("#previewRateSummary").textContent()));
  await page.screenshot({path:`${out}/registration-1440.png`,fullPage:true});
  for(const [id,value] of Object.entries({title:"[가상] 요금 입력 검사",space_label:"가상 검사 공간",
      rooms:"1",area_m2:"40",guests:"2",min_stay:"7"}))await page.locator("#"+id).fill(value);
  const posted=page.waitForRequest(req=>req.method()==="POST"&&req.url().endsWith("/applications"));
  const saved=page.waitForResponse(res=>res.request().method()==="POST"&&res.url().endsWith("/applications"));
  await page.locator("#saveButton").click();
  const payload=(await posted).postDataJSON().payload;
  assert(!Object.hasOwn(payload,"nightly"));assert.equal(payload.weekly,300000);
  const response=await saved;assert.equal(response.status(),201);
  await page.waitForFunction(()=>document.querySelector("#revision").textContent!=="아직 저장 전");
  await page.locator("#stay_kind").selectOption("lodging");
  assert.equal(await page.locator("#weekly").inputValue(),"");
  assert.equal(await page.locator("#monthly").inputValue(),"");
  assert.equal(await page.locator("#nightly").inputValue(),"");
  await page.locator("#stay_kind").selectOption("non_lodging");
  assert.equal(await page.locator("#weekly").inputValue(),"");
  await page.locator("#weekly").fill("1.5");await page.locator("#monthly").fill("600000");
  assert.match(await page.locator("#previewRateSummary").textContent(),/기준 요금 비공개/);
  const invalid=page.waitForResponse(res=>res.request().method()==="PUT"&&
      res.url().includes("/applications/"));
  await page.locator("#saveButton").click();
  const rejected = await invalid;
  assert.equal(rejected.status(),409); // existing registration ContractError contract
  assert.equal((await rejected.json()).code,"INVALID_NUMBER");
  await page.waitForFunction(()=>!document.querySelector("#saveButton").disabled);
  await page.locator("#weekly").fill("0");await page.locator("#monthly").fill("");
  assert.match(await page.locator("#previewRateSummary").textContent(),/1주 0원/);
  assert.match(await page.locator("#previewRateSummary").textContent(),/0원입니다/);
  assert.equal(await page.locator("#monthly").inputValue(),"");
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:`${out}/registration-390.png`,fullPage:true});
  results.push({case:"registration hidden fields omitted, real save, warnings, no resurrection",pass:true});
  assert.deepEqual(errors,[]);assert.deepEqual(failures,[]);
  fs.writeFileSync(out+"/browser-checks.json",JSON.stringify({ok:true,results,errors,failures},null,2));
  console.log("PASS",results.length,"browser scenarios, 1440/390; screenshot evidence saved");
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
