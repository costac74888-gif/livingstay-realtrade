/* Real Chromium + owned synthetic HTTP. No operational app or external calls. */
const assert = require("node:assert/strict");
const {chromium} = require("playwright");
const {RegistrationController} = require("../hs2_registration/web/controller.js");
const origin = process.env.HS2_FIXTURE_ORIGIN;

async function controllers() {
  const pending = [], renders=[];
  const c=new RegistrationController((url,body)=>new Promise((resolve,reject)=>pending.push({url,body,resolve,reject})),
    (state,options)=>renders.push({state,options}));
  const old=c.start("old"), fresh=c.start("fresh");
  pending[1].resolve({workflow_id:"fresh",status:"ADDRESS_SELECTION_REQUIRED"});await fresh;
  pending[0].resolve({workflow_id:"old",status:"ADDRESS_SELECTION_REQUIRED"});await old;
  assert.equal(c.state.workflow_id,"fresh");
  const first=c.action("coordinates");
  await c.action("coordinates");assert.equal(pending.length,3);
  pending[2].resolve({workflow_id:"fresh",status:"READY_FOR_REFERENCE"});await first;
  const failure=c.action("confirm");
  pending[3].reject(Object.assign(Error("private raw upstream"),{code:"WORKFLOW_EXPIRED"}));await failure;
  assert.equal(c.state,null);assert.equal(renders.at(-1).options.error.code,"WORKFLOW_EXPIRED");
  assert(!JSON.stringify(renders).includes("private raw upstream"));
}

async function run() {
  assert(origin && /^http:\/\/127\.0\.0\.1:\d+$/.test(origin));
  assert.throws(()=>require("node:https").get("https://example.com"));
  await controllers();
  const browser=await chromium.launch({executablePath:process.env.HS2_CHROMIUM,
    args:["--no-sandbox","--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1"]});
  let assertions=8;
  try {
    for(const width of [1280,390]) {
      const page=await browser.newPage({viewport:{width,height:900},
        userAgent:"Mozilla/5.0 Chrome/138.0.0.0 Safari/537.36"});
      const errors=[],external=[];page.on("pageerror",e=>errors.push(e.message));
      await page.route("**/*",route=>{
        const url=new URL(route.request().url());
        if(url.origin!==origin){external.push(url.origin);return route.abort();}
        if(!url.pathname.startsWith("/hs2/registration/"))return route.abort();
        return route.continue();
      });
      await page.goto(origin+"/hs2/registration/");
      assert(await page.locator("#coordinatePreview").isHidden());
      assert(await page.locator("#confirmBtn").isDisabled());
      assert(await page.locator("#coordinateBtn").isDisabled());assertions+=3;
      async function start(q) {
        await page.locator("#addressQuery").fill(q);
        await page.locator("#searchBtn").click();
        await page.waitForFunction(()=>!document.querySelector("#searchBtn").disabled);
      }
      async function select() {
        await page.locator("[data-address-key]").first().click();
        await page.locator("[data-building-key]").first().waitFor();
        assert(await page.locator("#coordinateBtn").isDisabled());
        await page.locator("[data-building-key]").first().click();
        await page.waitForFunction(()=>!document.querySelector("#coordinateBtn").disabled);
        assert(await page.locator("#confirmBtn").isDisabled());assertions+=2;
      }
      await start("검증로");
      assert.equal(await page.locator("[data-address-key]").count(),1);
      assert.equal(await page.locator("[data-building-key]").count(),0);assertions+=2;
      await select();await page.locator("#coordinateBtn").click();
      await page.waitForFunction(()=>!document.querySelector("#confirmBtn").disabled);
      assert(await page.locator("#coordinatePreview").isVisible());
      assert((await page.locator("#coordinatePreview").textContent()).includes("37.5"));
      assert((await page.locator("#workflowStatus").textContent()).includes("정확히 연결"));
      await page.locator("#confirmBtn").click();
      await page.waitForFunction(()=>document.querySelector("#workflowStatus").textContent.includes("확인이 완료"));
      assert(await page.locator("#confirmBtn").isDisabled());assertions+=4;

      await start("모호");
      assert.equal(await page.locator("[data-address-key]").count(),2);
      assert.equal(await page.locator("[data-building-key]").count(),0);
      assert(await page.locator("#coordinatePreview").isHidden());assertions+=3;

      await start("여러동");
      await page.locator("[data-address-key]").first().click();
      await page.waitForFunction(()=>document.querySelectorAll("[data-building-key]").length===2);
      assert(await page.locator("#coordinateBtn").isDisabled());
      await page.locator("[data-building-key]").last().click();
      await page.waitForFunction(()=>!document.querySelector("#coordinateBtn").disabled);
      await page.locator("#coordinateBtn").click();
      await page.waitForFunction(()=>!document.querySelector("#confirmBtn").disabled);
      assert((await page.locator("#workflowStatus").textContent()).includes("별도 항목"));assertions+=2;

      for(const [q,message] of [["미검색","찾지 못"],["오류","실패"],["대장없음","근거가 없습니다"],
                                 ["좌표없음","확인된 좌표가 없습니다"],["좌표모호","여러 결과"]]) {
        await start(q);
        if(q==="대장없음"){
          await page.locator("[data-address-key]").first().click();
        }else if(q.startsWith("좌표")){
          await select();await page.locator("#coordinateBtn").click();
        }
        await page.waitForFunction(text=>document.querySelector("#workflowStatus").textContent.includes(text),message);
        assert(await page.locator("#confirmBtn").isDisabled());
        assert(await page.locator("#coordinatePreview").isHidden());assertions+=2;
      }
      await start("창고");await select();
      assert((await page.locator("#buildingChoices").textContent()).includes("창고"));assertions++;
      // Server string injection must render as text, never executable markup.
      await page.route("**/address",r=>r.fulfill({json:{workflow_id:"fixture",status:"BUILDING_SELECTION_REQUIRED",
        buildings:[{building_key:"one",name:"<img src=x onerror=window.__injected=1>",dong:"101동",building_use:"상가",road_address:"합성 주소"}]}}));
      await start("검증로");await page.locator("[data-address-key]").first().click();
      await page.waitForFunction(()=>document.querySelector("#buildingChoices").textContent.includes("<img"));
      assert.equal(await page.locator("#buildingChoices img").count(),0);
      assert.equal(await page.evaluate(()=>window.__injected),undefined);assertions+=2;
      assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1));
      assert.deepEqual(errors,[]);assert.deepEqual(external,[]);assertions+=3;
      await page.close();
    }
    console.log(`HS2_UI_PASS ${assertions} assertions; desktop/mobile real UI, stale response, explicit selection, errors, privacy, XSS, no external requests`);
  } finally {await browser.close();}
}
run().catch(e=>{console.error(e);process.exitCode=1;});
